import datetime
import os.path
import shutil
import signal
import sys
from multiprocessing import Process, Queue

import akshare as ak
import pandas as pd
import requests


def get_us_tickers_sec():
    """从 SEC EDGAR 获取美股 ticker 列表（~4秒，比 akshare 快 ~69x）"""
    headers = {"User-Agent": "TradeStrategy contact@example.com"}
    r = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    tickers = [v["ticker"] for v in data.values()]
    return sorted(set(tickers))


def get_us_tickers_github():
    """从 GitHub 静态源获取美股 ticker 列表（~2秒，fallback 方案）"""
    url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers.txt"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    tickers = [t.strip() for t in r.text.strip().split("\n") if t.strip()]
    return sorted(set(tickers))


def get_us_tickers_fast():
    """快速获取美股 ticker 列表，SEC EDGAR 为主，GitHub 为 fallback，akshare 兜底"""
    try:
        print("Fetching tickers from SEC EDGAR...")
        tickers = get_us_tickers_sec()
        print(f"SEC EDGAR: got {len(tickers)} tickers")
        return tickers
    except Exception as e:
        print(f"SEC EDGAR failed: {e}, trying GitHub fallback...")
    try:
        tickers = get_us_tickers_github()
        print(f"GitHub fallback: got {len(tickers)} tickers")
        return tickers
    except Exception as e:
        print(f"GitHub fallback also failed: {e}, falling back to akshare...")
        df = ak.get_us_stock_name()
        tickers = df["symbol"].tolist()
        print(f"akshare fallback: got {len(tickers)} tickers")
        return tickers


def _fetch_us_daily_qfq(tic):
    """包装 akshare stock_us_daily，绕开上游 qfq 分支里的只读 bug。

    akshare/stock/stock_us_sina.py:167 有一行:
        new_range.index.values[0] = pd.to_datetime(str(data_df.index.date[0]))
    当 qfq_factor_df.index[0] == 1900-01-01（即无公司行为的占位因子）时，
    该行被触发，对 Index 底层 ndarray 做写入；某些 numpy/pandas 组合下
    `.index.values` 是只读的，直接抛 ValueError: assignment destination is
    read-only。AERO/AEHR/FB 这类无分红/拆股的 ticker 全部踩坑。

    Fix: 先用 adjust="qfq-factor" 嗅探因子表：
      - 若只有一行且 date == 1900-01-01 → 无需复权，直接调 adjust=""
        返回原始价格。qfq_factor=1、adjust=0 时 raw == qfq 恒等成立。
      - 否则（真实有因子的 ticker）→ akshare qfq 分支里 len(new_range) > 1，
        不会执行 line 167，安全调用 adjust="qfq"。
    """
    factor_df = ak.stock_us_daily(symbol=tic, adjust="qfq-factor")
    placeholder = (
        len(factor_df) == 1
        and pd.to_datetime(factor_df.iloc[0]["date"]) == pd.Timestamp("1900-01-01")
    )
    return ak.stock_us_daily(symbol=tic, adjust="" if placeholder else "qfq")


def download_stock(tic, path, days_from_now, file_format="pkl"):
    """全量下载股票数据，覆盖已存在文件。

    akshare 的 stock_us_daily 无法指定时间参数，每次调用都返回全部历史。
    前复权（adjust="qfq"）会回溯修改历史价格（分红/拆股调整），所以
    每次都用最新的全量数据覆盖旧文件，避免价格历史失真。

    同日内已下载过的文件（mtime == 今天）会被跳过：这支持"中断后
    重跑"的场景——已完成的股票不会被再次下载，只有剩下的和 mtime
    不是今天的才会触发真正的 akshare 调用。次日启动时所有文件
    mtime 都变成昨天，会被重新下载，符合预期。
    """
    if file_format not in ["csv", "pkl"]:
        raise ValueError("file_format must be either 'csv' or 'pkl'")

    # 同日内已下载过 → 跳过（支持中断后重跑不浪费已完成的工作）
    if os.path.exists(path):
        mtime_date = datetime.date.fromtimestamp(os.path.getmtime(path))
        if mtime_date == datetime.date.today():
            return

    start_date = datetime.datetime.now() - datetime.timedelta(days=days_from_now)
    end_date = datetime.datetime.now()

    # 通过 _fetch_us_daily_qfq 绕开 akshare qfq 分支在占位因子 ticker 上的
    # Index 写入 bug。拿到后再逐列 to_numpy().copy() 强制重建为可写数组，
    # 防止任何 inplace/列赋值触发 "assignment destination is read-only"。
    #
    # akshare 对特殊证券（优先股/权证/退市/OTC/粉单/SPAC warrant 等）
    # 返回格式不稳定，统一在这里静默吸收为"跳过该 ticker"：
    #   - IndexError: 上游 result[0] 越界（原在 worker L146 过滤）
    #   - KeyError 'date': 返回空/缺列 df，我们的 assign/iloc 取不到 date
    #   - SyntaxError: akshare 内部 eval sina 响应失败（服务端返回乱码）
    #   - KeyError(Timestamp): 返回 date 列混入离谱年份（如 2153-02-02）→
    #     set_index 后 index 非单调 → .loc 切片抛 KeyError
    # 这些都是上游数据异常，不是本地 bug，打印出来只会污染日志。
    try:
        raw = _fetch_us_daily_qfq(tic)
        df_new = pd.DataFrame(
            {col: raw[col].to_numpy().copy() for col in raw.columns}
        )
        df_new = (
            df_new
            .assign(date=lambda d: pd.to_datetime(d["date"]))
            .set_index("date")
            .loc[start_date:end_date]
        )
    except (IndexError, KeyError, SyntaxError):
        return

    if len(df_new) < 12 * 21:
        return

    df_new = df_new.ffill()  # Fill missing values forward
    if file_format == "csv":
        df_new.to_csv(path)
    else:
        df_new.to_pickle(path)
    print(f"Download {tic}")


def worker(task_queue, save_root, days_from_now, file_format):
    # Sentinel 模式：每个 worker 会在队列中拿到一个 None 作为结束信号。
    # 不使用 `while not task_queue.empty()` 因为 empty() 在 multiprocessing.Queue
    # 中不可靠，会导致多个 worker 同时通过检查后竞争最后一个元素，失败者永久
    # 阻塞在 get() 上，主进程 join() 也永远等不到它们退出。
    while True:
        tic = task_queue.get()
        if tic is None:
            return
        save_path = os.path.join(
            save_root, tic + (".csv" if file_format == "csv" else ".pkl")
        )
        try:
            download_stock(tic, save_path, days_from_now, file_format)
        except Exception as e:
            # download_stock 已吸收所有已知的 akshare 上游噪音；能走到这里
            # 的都是真正未预期的异常（磁盘满、权限错误等），保留打印便于排障。
            print(f"Error: {tic} {e}")


def multi_download_stock(
    tickers,
    save_root,
    days_from_now,
    clear,
    num_workers=os.cpu_count(),
    file_format="pkl",
):
    if clear:
        # 删除 save_root 下的所有文件
        if os.path.exists(save_root):
            shutil.rmtree(save_root)
            os.mkdir(save_root)
            print("Clear all files in", save_root)

    # Create a queue to manage tasks
    q = Queue()
    for tic in sorted(tickers):
        q.put(tic)
    # Sentinel：为每个 worker 放一个 None 作为结束信号，
    # 避免 worker 用 empty() 检查导致的竞态死锁
    for _ in range(num_workers):
        q.put(None)

    # Prepare input parameters for worker processes
    input_dict = dict(
        task_queue=q,
        save_root=save_root,
        days_from_now=days_from_now,
        file_format=file_format,
    )

    # Create worker processes
    processes = [Process(target=worker, kwargs=input_dict) for _ in range(num_workers)]
    for p in processes:
        p.start()

    # Wait for all worker processes to complete
    for p in processes:
        p.join()


if __name__ == "__main__":
    # CLI 场景下注册 signal handler：Ctrl-C / SIGTERM 时优雅退出。
    # 在 fork worker 子进程前注册，子进程会继承该 handler，收到 SIGINT
    # 也会走 sys.exit(0)，multiprocessing 的 atexit 清理会 terminate
    # 任何残留子进程。函数 multi_download_stock 本身不再触碰 signal 模块，
    # 以便 UI 等非主线程调用方可以安全复用它。
    def _cli_stop(signum, frame):
        print("Received signal, exiting...")
        sys.exit(0)

    signal.signal(signal.SIGINT, _cli_stop)
    signal.signal(signal.SIGTERM, _cli_stop)

    use_cache = True
    if os.path.exists("datasets/stock_list.pkl") and use_cache:
        print("load local stock list")
        # load the file to get all_tickers
        # with open('datasets/dbg_tickers.txt', 'r') as f:
        #     all_tickers = f.read().splitlines()
        all_tickers = pd.read_pickle("datasets/stock_list.pkl").tolist()
        print(len(all_tickers))

    else:
        print("load online stock list")
        all_tickers = get_us_tickers_fast()

    # Start downloading stock data for all tickers
    start_time = datetime.datetime.now()
    multi_download_stock(
        all_tickers,
        save_root="datasets/pkls",  # cur_pkls   pkls
        days_from_now=365 * 5,
        clear=False,
        num_workers=os.cpu_count(),
        # num_workers=1,
        file_format="pkl",  # Change to 'csv' or 'pkl'
    )
    # 统计并输出耗时，格式为几分几秒
    elapsed = datetime.datetime.now() - start_time
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    print(f"Total time: {int(minutes)} min {int(seconds)} sec")

    data_root = "datasets/pkls"
    # preprocessed_root = 'datasets/process_pkls'
    # preprocessor = StockPreprocessor(data_root, preprocessed_root,skip_neg_value=True)
    #
    # processed_files = preprocessor.preprocess_all()

import datetime
import os.path
import random
import shutil
import signal
import sys
import time
import multiprocessing
from multiprocessing import Process, Queue

import akshare as ak
import pandas as pd
import requests
import yfinance as yf
from curl_cffi import requests as cffi_requests
from yfinance.exceptions import YFRateLimitError

# 每个 worker 进程独立持有一个 curl_cffi session（惰性初始化，
# 避免 multiprocessing fork 时共享底层连接 fd 导致的竞态）。
# 浏览器指纹让 Yahoo 把请求当成 Chrome 而非脚本，绕过 anti-bot 延迟，
# 相较原生 requests 单请求快 ~1.7×。
_CFFI_SESSION = None
def _get_cffi_session():
    global _CFFI_SESSION
    if _CFFI_SESSION is None:
        # 代理绕开不在代码层处理——试过 trust_env / proxies / curl_options
        # NOPROXY / YfConfig monkey-patch 各种组合，PyCharm/多进程场景下都
        # 不稳定。最终方案：跑之前用 shell 前缀清 env，例如
        #   HTTPS_PROXY= HTTP_PROXY= uv run python scripts/data/data_download.py
        _CFFI_SESSION = cffi_requests.Session(impersonate="chrome")
    return _CFFI_SESSION


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


def _fetch_us_daily_qfq(tic, start_dt, end_dt):
    """用 yfinance 拉美股日线，auto_adjust=True 做完整前复权。

    历史上曾用 akshare 新浪源 stock_us_daily(adjust="qfq")，但对部分 ticker
    的 corporate action 复权是错的：DGNX 在 2025-09-09 有 1:8 合股，akshare
    因子表已含 8×，但 qfq 分支未把该因子应用到合股日之前的历史价，导致
    相邻日出现 6.79× 伪跳空；成交量也未做 ÷8 调整，跨 split 不可比。

    yfinance 对 DGNX 的三次 corporate action（2025-08-01 拆股 1/7、
    2025-09-09 合股 8×、2026-04-28 拆股 1/8）全部正确合并到历史价，
    端到端无跳空，且免费无 key。故切换。

    返回 DataFrame，列 = [date, open, high, low, close, volume]，
    与调用方（download_stock）历史契约兼容；tz 已剥离。
    """
    # Yahoo 免费源对同 IP 有限速（大约几十请求/分钟）。
    # 撞 429 时指数退避（含抖动）重试；超上限就把它转成 KeyError，
    # 让下游 download_stock 走静默跳过路径，不污染日志——次日 mtime
    # 变化后会被自动重下补齐。
    df = None
    for attempt in range(6):
        try:
            df = yf.Ticker(tic, session=_get_cffi_session()).history(
                start=start_dt.strftime("%Y-%m-%d"),
                end=(end_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=True,
                actions=False,
                raise_errors=True,
            )
            break
        except YFRateLimitError:
            if attempt == 5:
                raise KeyError("date")
            backoff = (2 ** attempt) * 5 + random.uniform(0, 3)
            time.sleep(backoff)
    if df is None or df.empty:
        # 复用调用方的静默吸收路径：退市/无数据 ticker 直接跳过
        raise KeyError("date")
    df.index = df.index.tz_localize(None)
    df = df.reset_index().rename(columns={
        "Date": "date",
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    # volume 保持 float，与旧 pkl 类型一致
    df["volume"] = df["volume"].astype(float)
    return df[["date", "open", "high", "low", "close", "volume"]]


def download_stock(tic, path, days_from_now, file_format="pkl", rm_invalid=False):
    """全量下载股票数据，覆盖已存在文件。

    yfinance 已支持 start/end 参数，但仍每次全量覆盖：auto_adjust=True 的
    前复权会随新的 corporate action 回溯修改历史价，用最新一次拉到的窗口
    重写文件才能避免历史失真。

    同日内已下载过的文件（mtime == 今天）会被跳过，支持"中断后重跑"的
    场景——已完成的股票不再重复请求。次日启动时所有 pkl mtime 都变成
    昨天，会被重新拉一遍，符合预期。
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

    # 上游任何数据异常（退市 ticker 空 df / 网络抖动导致 raise_errors 未拦到的
    # 结构异常 / 罕见的 date 列缺失）统一吸收为"跳过该 ticker"，不污染日志。
    try:
        raw = _fetch_us_daily_qfq(tic, start_date, end_date)
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
        # yfinance 拉不到（退市 / 404 / 罕见结构异常）→ rm_invalid=True 时
        # 删旧 pkl，避免"过期残留静默混入"（否则 UI 会读到旧数据、扫描仍
        # 命中已退市股，见 DTCK 案例）。
        if rm_invalid and os.path.exists(path):
            os.remove(path)
        return

    if len(df_new) < 12 * 21:
        # 新数据不足 252 行（历史太短、上市不久）→ 同上，rm_invalid=True
        # 时删旧 pkl 让数据集口径与"当前 yfinance 视角"一致。
        if rm_invalid and os.path.exists(path):
            os.remove(path)
        return

    df_new = df_new.ffill()  # Fill missing values forward
    if file_format == "csv":
        df_new.to_csv(path)
    else:
        df_new.to_pickle(path)
    print(f"Download {tic}")


def worker(task_queue, save_root, days_from_now, file_format, rm_invalid=False):
    # 子进程 stdout 在非 tty pipe 下（PyCharm run config / nohup / 重定向到
    # 文件等）默认全缓冲，Download/Error 行会攒到 4KB 才 flush，前 30 秒
    # 屏幕看起来像"啥都没干"，pkl 却已在悄悄落盘——排障成本很高。切成
    # 行缓冲后任何一行立即可见。
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
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
            download_stock(tic, save_path, days_from_now, file_format, rm_invalid=rm_invalid)
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
    rm_invalid=False,
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
        rm_invalid=rm_invalid,
    )

    # daemon=True：主进程退出时 kernel 会自动 terminate 所有 worker。
    # Ctrl-C 只按一次即可整组停——否则 workers 卡在 curl/libcurl 的 C 层
    # 阻塞里不响应 Python-level SIGINT，用户体感就是"按 10 次才停下"。
    processes = [Process(target=worker, kwargs=input_dict, daemon=True) for _ in range(num_workers)]
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
        # 主进程主动 SIGKILL 所有 daemon workers，否则 workers 卡在 libcurl
        # C 层不响应 Python 信号，主进程的 p.join() 要等每个 worker 慢慢
        # curl timeout 才返回，Ctrl-C 后 shell 感觉像"按了没反应"。
        for _p in multiprocessing.active_children():
            _p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, _cli_stop)
    signal.signal(signal.SIGTERM, _cli_stop)

    # 代理绕开不在代码层处理——跑脚本前用 shell 前缀清 env,
    # 例如：HTTPS_PROXY= HTTP_PROXY= uv run python scripts/data/data_download.py

    # datasets/pkls 是所有 worktree 共享的数据落盘目录，
    # 硬编码为主仓库绝对路径，确保任何 worktree 跑本脚本都写到同一位置。
    DATASETS_ROOT = "/home/yu/PycharmProjects/Trade_Strategy/datasets"

    # 下载行为开关（遵循 CLAUDE.md：入口脚本参数在起始位置声明）
    clear = True        # True: 先 rmtree 目录再全下（危险，会丢历史）
    rm_invalid = True    # True: yfinance 拉不到或数据不足 252 行时删旧 pkl，
                         #      避免"过期残留静默混入"（例如退市股 DTCK）

    use_cache = True
    stock_list_path = os.path.join(DATASETS_ROOT, "stock_list.pkl")
    if os.path.exists(stock_list_path) and use_cache:
        print("load local stock list")
        all_tickers = pd.read_pickle(stock_list_path).tolist()
        print(len(all_tickers))

    else:
        print("load online stock list")
        all_tickers = get_us_tickers_fast()

    # Start downloading stock data for all tickers
    start_time = datetime.datetime.now()
    multi_download_stock(
        all_tickers,
        save_root=os.path.join(DATASETS_ROOT, "pkls_test"),
        days_from_now=365 * 5,
        clear=clear,
        rm_invalid=rm_invalid,
        # curl_cffi 浏览器指纹 + workers=10 是实测拐点：
        # workers=10 峰值 ~11/s（native）或 ~15-20/s（curl_cffi），
        # workers=12 反降；累积到 IP 软阈值时退避机制兜底。
        num_workers=10,
        file_format="pkl",  # Change to 'csv' or 'pkl'
    )
    # 统计并输出耗时，格式为几分几秒
    elapsed = datetime.datetime.now() - start_time
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    print(f"Total time: {int(minutes)} min {int(seconds)} sec")

    data_root = os.path.join(DATASETS_ROOT, "pkls")
    # preprocessed_root = 'datasets/process_pkls'
    # preprocessor = StockPreprocessor(data_root, preprocessed_root,skip_neg_value=True)
    #
    # processed_files = preprocessor.preprocess_all()

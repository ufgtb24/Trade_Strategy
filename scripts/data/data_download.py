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


def download_stock(tic, path, days_from_now, append_data=False, file_format="pkl"):
    if file_format not in ["csv", "pkl"]:
        raise ValueError("file_format must be either 'csv' or 'pkl'")
    if os.path.exists(path):
        if append_data:
            # Read the existing data
            if file_format == "csv":
                df_old = pd.read_csv(path, parse_dates=True, index_col=0)
            else:
                df_old = pd.read_pickle(path)
            start_date = df_old.index[-1].date() + datetime.timedelta(days=1)
            end_date = datetime.date.today()
            # If the data is already up-to-date
            if start_date == end_date:
                print("Already latest")
            else:
                df_new = ak.stock_us_daily(symbol=tic, adjust="qfq")
                df_new["date"] = pd.to_datetime(df_new["date"])
                df_new.set_index("date", inplace=True)
                df_new = df_new.loc[start_date:end_date]

                df_new = pd.concat([df_old, df_new])
                df_new = df_new[~df_new.index.duplicated(keep="first")]
                df_new.ffill(inplace=True)  # Fill missing values forward
                df_new.index = pd.to_datetime(df_new.index)
                if file_format == "csv":
                    df_new.to_csv(path)
                else:
                    df_new.to_pickle(path)
                print(f"Append {tic}")
        else:
            print(f"{tic} already exists")
    else:
        # Download data from scratch
        start_date = datetime.datetime.now() - datetime.timedelta(days=days_from_now)
        end_date = datetime.datetime.now()

        df_new = ak.stock_us_daily(symbol=tic, adjust="qfq")
        df_new["date"] = pd.to_datetime(df_new["date"])
        df_new.set_index("date", inplace=True)
        df_new = df_new.loc[start_date:end_date]
        if len(df_new) < 12 * 21:
            # print(f'Warning: {tic} has less than  months of data, skipping.')
            return

        df_new.ffill(inplace=True)  # Fill missing values forward
        df_new.index = pd.to_datetime(df_new.index)
        if file_format == "csv":
            df_new.to_csv(path)
        else:
            df_new.to_pickle(path)
        print(f"Download {tic}")


def worker(task_queue, save_root, days_from_now, append_data, file_format):
    while not task_queue.empty():
        tic = task_queue.get()
        save_path = os.path.join(
            save_root, tic + (".csv" if file_format == "csv" else ".pkl")
        )
        try:
            download_stock(tic, save_path, days_from_now, append_data, file_format)
        except Exception as e:
            print(f"Error: {tic} {e}")


def multi_download_stock(
    tickers,
    save_root,
    days_from_now,
    append_data,
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

    # Prepare input parameters for worker processes
    input_dict = dict(
        task_queue=q,
        save_root=save_root,
        days_from_now=days_from_now,
        append_data=append_data,
        file_format=file_format,
    )

    # Create worker processes
    processes = [Process(target=worker, kwargs=input_dict) for _ in range(num_workers)]
    for p in processes:
        p.start()

    # Function to stop all processes gracefully
    def stop_processes(signal, frame):
        print("Received signal, stopping processes...")
        for p in processes:
            p.terminate()
            p.join()
        sys.exit(0)

    # Register signal handlers to stop processes on interrupt or termination
    signal.signal(signal.SIGINT, stop_processes)
    signal.signal(signal.SIGTERM, stop_processes)

    # Wait for all worker processes to complete
    for p in processes:
        p.join()


if __name__ == "__main__":
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
        days_from_now=365 * 5,  #
        append_data=False,  # use 7 minites for append, while 4 minites for download from scratch
        clear=True,
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

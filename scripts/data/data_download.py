import datetime
import os.path
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
from yfinance.exceptions import YFRateLimitError, YFPricesMissingError, YFTzMissingError
from curl_cffi.requests.exceptions import RequestException as _CurlRequestException

# Yahoo 拒绝我们时不一定回 429:实测(2026-09-06,单 IP 连下约 600 只后)它改成
# 直接把连接吊死,curl 报 (28) Operation timed out / 0 bytes received。这类异常
# 的类型名不全在 yfinance 的瞬时错误表里,耗尽它自己那层短重试后原样抛出,
# 于是绕过下面整套全局冷却,每只股票 10~30 秒失败一次、不重试——一轮下来会把
# 剩余几千只全部烧成永久跳过。故把传输层错误与 429 归到同一条冷却路径。
_THROTTLE_ERRORS = (YFRateLimitError, _CurlRequestException)


class _ThrottleExhausted(Exception):
    """限速重试耗尽：4 次退避后仍 429/timeout，当前出口节点已被 Yahoo 限速。

    区别于退市(404)/历史不足等正常跳过——用于触发节点轮换的失败计数切换。
    """

# 直连主 IP 绕行出口(2026-09-06 实测): 直连主 IP 连下约 600 只后会被 Yahoo
# 惩罚(429 / curl-28 吊连接, 实测持续 1.5h+ 未消)。串行低并发可避免触发,
# 但被罚期间得换出口。置 CLASH_PROXY 走 clash 代理出口绕开; 主 IP 恢复后置
# None 切回直连。显式 proxies 而非读 env——PyCharm 启动不带代理 env, 裸
# Session 会直连被罚的主 IP。
CLASH_PROXY = "http://127.0.0.1:7897"

# 节点轮换(2026-09-06): 直连主 IP 被 Yahoo 惩罚期间, 用多个 HK 机场节点轮换
# 分摊单 IP 限速——12 个 HK 节点实测各自独立出口 IP, 4 worker 并发零惩罚,
# 单节点 ~5.7/s。下载完成后复原到 ORIGINAL_NODE(用户当前 isp 配置)。
CLASH_SOCK = "/tmp/verge/verge-mihomo.sock"
CLASH_CFG = "/home/yu/.local/share/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml"
CLASH_GROUP = "🔰 节点选择"
ORIGINAL_NODE = "HTTP isp.decodo.com:10001"
# 真实出口节点的协议类型(排除 Selector/URLTest/Fallback/LoadBalance 等分组)
_REAL_PROXY_TYPES = ("Socks5", "Vmess", "Trojan", "HTTP", "Tuic", "Hysteria2",
                     "Shadowsocks", "Socks", "SSR", "WireGuard")
ROTATE_EVERY = 400  # 每个节点下约 400 只后切下一个(低于 585 触发线, 留安全边际)

def _clash_secret():
    try:
        with open(CLASH_CFG) as f:
            for line in f:
                s = line.strip()
                if s.startswith("secret:"):
                    return s.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""

def _switch_clash_node(name):
    """切「🔰 节点选择」到指定节点(经 clash unix socket API)。"""
    import subprocess, urllib.parse
    cmd = ["curl", "-s", "--unix-socket", CLASH_SOCK,
           "-H", "Authorization: Bearer " + _clash_secret(),
           "-X", "PUT", "-H", "Content-Type: application/json",
           "--data", '{"name":"%s"}' % name,
           "http://localhost/proxies/%s" % urllib.parse.quote(CLASH_GROUP)]
    subprocess.check_output(cmd, timeout=15)
    time.sleep(1.0)


def _probe_yahoo():
    """健康探针: 拉一只已知好股(MSFT)测当前出口节点对 Yahoo 是否通。

    节点轮换是盲切, 若切到坏节点(线路断了/被 Yahoo 针对)会让整段 rotate_every
    只股票陷进 4 次退避重试后静默跳过——浪费大量时间且丢数据。切节点后先探
    一次, 不通则主进程顺延到下一个节点, 坏节点只浪费一次探针(≤10s)而非整段。
    """
    from curl_cffi import requests as _cffi
    s = _cffi.Session(impersonate="chrome")
    if CLASH_PROXY:
        s.proxies = {"http": CLASH_PROXY, "https": CLASH_PROXY}
    try:
        r = s.get("https://query1.finance.yahoo.com/v8/finance/chart/MSFT",
                  params={"range": "5d", "interval": "1d"}, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def _get_hk_nodes():
    """动态读 clash 里所有 HK 真实出口节点(排除分组), 替代写死的 HK_NODES。

    机场订阅更新节点(改名/删改)后无需手动维护列表; 每次下载启动时从 clash
    API(GET /proxies)现读, 只取 name 以 "HK" 开头且 type 是真实协议的节点。
    读不到则抛 RuntimeError——clash 没开/API 变了时直接报错, 不静默降级。
    """
    import subprocess, json
    cmd = ["curl", "-s", "--unix-socket", CLASH_SOCK,
           "-H", "Authorization: Bearer " + _clash_secret(),
           "http://localhost/proxies"]
    out = subprocess.check_output(cmd, timeout=15).decode("utf-8", "replace")
    data = json.loads(out)
    proxies = data["proxies"]
    hk = sorted(
        name for name, p in proxies.items()
        if name.startswith("HK") and p.get("type") in _REAL_PROXY_TYPES
    )
    if not hk:
        raise RuntimeError("clash 里没有 HK 真实节点, 无法轮换下载")
    return hk

# 每个 worker 进程独立持有一个 curl_cffi session（惰性初始化，
# 避免 multiprocessing fork 时共享底层连接 fd 导致的竞态）。
# 浏览器指纹让 Yahoo 把请求当成 Chrome 而非脚本，绕过 anti-bot 延迟，
# 相较原生 requests 单请求快 ~1.7×。
_CFFI_SESSION = None
def _get_cffi_session():
    global _CFFI_SESSION
    if _CFFI_SESSION is None:
        _CFFI_SESSION = cffi_requests.Session(impersonate="chrome")
        # 早期「代码层设代理在 PyCharm/多进程下不稳定」是「高并发 + 代理」
        # 组合的问题; 改单 worker 串行后显式走代理已实测稳定(700 只零惩罚)。
        if CLASH_PROXY:
            _CFFI_SESSION.proxies = {"http": CLASH_PROXY, "https": CLASH_PROXY}
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


def _fetch_us_daily_qfq(tic, start_dt, end_dt, rate_gate=None):
    """用 yfinance 拉美股日线，auto_adjust=True 做完整前复权。

    历史上曾用 akshare 新浪源 stock_us_daily(adjust="qfq")，但对部分 ticker
    的 corporate action 复权是错的：DGNX 在 2025-09-09 有 1:8 合股，akshare
    因子表已含 8×，但 qfq 分支未把该因子应用到合股日之前的历史价，导致
    相邻日出现 6.79× 伪跳空；成交量也未做 ÷8 调整，跨 split 不可比。

    yfinance 对 DGNX 的三次 corporate action（2025-08-01 拆股 1/7、
    2025-09-09 合股 8×、2026-04-28 拆股 1/8）全部正确合并到历史价，
    端到端无跳空，且免费无 key。故切换。

    rate_gate: multiprocessing.Value('d') 共享的「限速截止时间戳」。
    429 是整个 IP 的全局状态而非单 ticker 错误——任一 worker 撞 429 后
    把截止时间写进 gate，所有 worker 在发请求前对齐冷却（实测 Yahoo
    限速窗口 ~1-2 分钟）。此前各 worker 独立短退避（5/10/20s）重试，
    反而持续刷新滑动限速窗口，表现为「目录被 clear 清空后零下载零提示」。

    返回 DataFrame，列 = [date, open, high, low, close, volume]，
    与调用方（download_stock）历史契约兼容；tz 已剥离。
    """
    # Yahoo 免费源对同 IP 有限速（大约几十请求/分钟）。
    # 撞 429 时全员冷却后重试（90s 起步指数增长，cap 300s，上限 4 次，
    # 总最坏 ~14.5 分钟；实测限速窗口 1-2 分钟，常态一两次冷却即恢复）；
    # 超上限就把它转成 KeyError，让下游 download_stock 走静默跳过路径，
    # 不污染日志——次日 mtime 变化后会被自动重下补齐。
    df = None
    for attempt in range(4):
        # 全局限速门：冷却期内所有 worker 对齐等待，不再各自戳 Yahoo
        if rate_gate is not None:
            with rate_gate.get_lock():
                wait = rate_gate.value - time.time()
            if wait > 0:
                time.sleep(wait)
        try:
            df = yf.Ticker(tic, session=_get_cffi_session()).history(
                start=start_dt.strftime("%Y-%m-%d"),
                end=(end_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=True,
                actions=False,
                raise_errors=True,
            )
            break
        except _THROTTLE_ERRORS:
            if attempt == 3:
                raise _ThrottleExhausted()
            backoff = min(90 * (2 ** attempt), 300)
            if rate_gate is not None:
                # 只在「非限速 → 限速」的状态转换时打印，避免 10 worker
                # × 每 ticker 刷屏；竞态下多打几行无害
                with rate_gate.get_lock():
                    prev = rate_gate.value
                    rate_gate.value = max(prev, time.time() + backoff)
                if prev <= time.time():
                    print(f"Yahoo rate limit hit, all workers cooling down {backoff}s (attempt {attempt + 1}/4)")
            else:
                # 无共享 gate（独立调用/单测）时退化为本地退避
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


def download_stock(tic, path, days_from_now, file_format="pkl", rm_invalid=False, rate_gate=None):
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
            return "skip"

    start_date = datetime.datetime.now() - datetime.timedelta(days=days_from_now)
    end_date = datetime.datetime.now()

    # 上游任何数据异常（退市 ticker 空 df / 网络抖动导致 raise_errors 未拦到的
    # 结构异常 / 罕见的 date 列缺失）统一吸收为"跳过该 ticker"，不污染日志。
    try:
        raw = _fetch_us_daily_qfq(tic, start_date, end_date, rate_gate=rate_gate)
        df_new = pd.DataFrame(
            {col: raw[col].to_numpy().copy() for col in raw.columns}
        )
        df_new = (
            df_new
            .assign(date=lambda d: pd.to_datetime(d["date"]))
            .set_index("date")
            .loc[start_date:end_date]
        )
    except _ThrottleExhausted:
        # 限速重试耗尽：当前出口节点被 Yahoo 限速。标记 throttle 供节点轮换
        # 失败计数切换用（区别于下面退市/无数据的正常跳过）。
        return "throttle"
    except (IndexError, KeyError, SyntaxError, YFPricesMissingError, YFTzMissingError):
        # YFPricesMissingError / YFTzMissingError：yfinance>=1.2 对退市/无数据
        # ticker 抛的专用异常（旧版走 KeyError 路径），归入同一静默吸收，
        # 避免全量跑时几千行 "possibly delisted" Error 刷屏。
        # yfinance 拉不到（退市 / 404 / 罕见结构异常）→ rm_invalid=True 时
        # 删旧 pkl，避免"过期残留静默混入"（否则 UI 会读到旧数据、扫描仍
        # 命中已退市股，见 DTCK 案例）。
        if rm_invalid and os.path.exists(path):
            os.remove(path)
        return "skip"

    if len(df_new) < 12 * 21:
        # 新数据不足 252 行（历史太短、上市不久）→ 同上，rm_invalid=True
        # 时删旧 pkl 让数据集口径与"当前 yfinance 视角"一致。
        if rm_invalid and os.path.exists(path):
            os.remove(path)
        return "skip"

    df_new = df_new.ffill()  # Fill missing values forward
    if file_format == "csv":
        df_new.to_csv(path)
    else:
        df_new.to_pickle(path)
    print(f"Download {tic}")
    return "downloaded"


def worker(task_queue, save_root, days_from_now, file_format, rm_invalid=False, rate_gate=None, counter=None, fail_counter=None):
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
        result = None
        try:
            result = download_stock(tic, save_path, days_from_now, file_format, rm_invalid=rm_invalid, rate_gate=rate_gate)
        except Exception as e:
            # download_stock 已吸收所有已知的 akshare 上游噪音；能走到这里
            # 的都是真正未预期的异常（磁盘满、权限错误等），保留打印便于排障。
            print(f"Error: {tic} {e}")
        finally:
            # 节点轮换用：每处理一只(含跳过/失败)计数一次, 主进程据此切节点
            if counter is not None:
                with counter.get_lock():
                    counter.value += 1
        # 失败计数切换：throttle 累加, downloaded 重置, skip 不变
        if fail_counter is not None:
            with fail_counter.get_lock():
                if result == "throttle":
                    fail_counter.value += 1
                elif result == "downloaded":
                    fail_counter.value = 0


def multi_download_stock(
    tickers,
    save_root,
    days_from_now,
    clear,
    num_workers=os.cpu_count(),
    file_format="pkl",
    rm_invalid=False,
    node_rotation=None,
    rotate_every=0,
):
    if clear and os.path.exists(save_root):
        shutil.rmtree(save_root)
        print("Clear all files in", save_root)
    # 目录必须无条件建:原先 mkdir 只写在「clear 且目录已存在」这一支里,于是
    # 首次运行(重装机器后整个 datasets/ 都不存在)时没人建目录,worker 每只股票
    # 抛 FileNotFoundError 被 worker 的兜底 except 吞成一行 Error,表现为整轮
    # 零落盘——与限速的表现难以区分。
    os.makedirs(save_root, exist_ok=True)

    # Create a queue to manage tasks
    q = Queue()
    for tic in sorted(tickers):
        q.put(tic)
    # Sentinel：为每个 worker 放一个 None 作为结束信号，
    # 避免 worker 用 empty() 检查导致的竞态死锁
    for _ in range(num_workers):
        q.put(None)

    # 跨进程共享的「限速截止时间戳」：任一 worker 撞 429 时写入，全体
    # worker 在 _fetch 里对齐冷却（见 _fetch_us_daily_qfq docstring）
    rate_gate = multiprocessing.Value("d", 0.0)
    counter = multiprocessing.Value("i", 0) if node_rotation else None
    fail_counter = multiprocessing.Value("i", 0) if node_rotation else None

    # Prepare input parameters for worker processes
    input_dict = dict(
        task_queue=q,
        save_root=save_root,
        days_from_now=days_from_now,
        file_format=file_format,
        rm_invalid=rm_invalid,
        rate_gate=rate_gate,
        counter=counter,
        fail_counter=fail_counter,
    )

    # daemon=True：主进程退出时 kernel 会自动 terminate 所有 worker。
    # Ctrl-C 只按一次即可整组停——否则 workers 卡在 curl/libcurl 的 C 层
    # 阻塞里不响应 Python-level SIGINT，用户体感就是"按 10 次才停下"。
    processes = [Process(target=worker, kwargs=input_dict, daemon=True) for _ in range(num_workers)]
    for p in processes:
        p.start()

    # Wait for all worker processes to complete；node_rotation 时轮询并每
    # rotate_every 只切下一个出口节点(切节点对 worker 透明, worker 走 7897
    # 代理, 由 clash 层完成路由切换)。
    if node_rotation and rotate_every:
        node_idx = -1
        fail_threshold = 3  # 连续 3 次 throttle 视为该节点已被限速, 立即切
        while any(p.is_alive() for p in processes):
            for p in processes:
                p.join(timeout=0.5)
            with counter.get_lock():
                done = counter.value
            with fail_counter.get_lock():
                fails = fail_counter.value
            # 失败计数切换: 某节点下载中途被 Yahoo 限速(连续 throttle), 立即切下一个
            if fails >= fail_threshold:
                node_idx = (node_idx + 1) % len(node_rotation)
                print(f"节点限速(连续{fails}次失败), 切换 -> {node_rotation[node_idx]}")
                _switch_clash_node(node_rotation[node_idx])
                with fail_counter.get_lock():
                    fail_counter.value = 0
                continue
            # 循环轮换: 每 rotate_every 只切下一个节点, 到末尾回到队首。
            # 每节点单轮最多 rotate_every 只, 之后休息 (len-1)*rotate_every 只的时间,
            # 避免单 IP 累计超阈值触发 Yahoo 惩罚。
            target = (done // rotate_every) % len(node_rotation)
            if target != node_idx:
                node_idx = target
                # 健康探针 + 顺延: 切到坏节点则顺延到下一个, 最多试一轮
                for _ in range(len(node_rotation)):
                    cand = node_rotation[node_idx]
                    _switch_clash_node(cand)
                    if _probe_yahoo():
                        print(f"切换节点 -> {cand}")
                        break
                    print(f"节点 {cand} 不健康, 顺延下一个")
                    node_idx = (node_idx + 1) % len(node_rotation)
    else:
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

    # 走不走代理由顶部 CLASH_PROXY 常量控制：现值 = 走 clash 出口绕开直连惩罚;
    # 直连主 IP 恢复后置 None 即切回直连。无需再 shell 清 env。

    # datasets/pkls 是所有 worktree 共享的数据落盘目录，
    # 硬编码为主仓库绝对路径，确保任何 worktree 跑本脚本都写到同一位置。
    DATASETS_ROOT = "/home/yu/PycharmProjects/Trade_Strategy/datasets"

    # 下载行为开关（遵循 CLAUDE.md：入口脚本参数在起始位置声明）
    clear = False       # True: 先 rmtree 目录再全下（危险，会丢历史）。
                        # pkls 已有 585 只(09:00 下的 A/B 段), False 靠
                        # mtime==today 跳过已下文件、只补缺口, 避免一跑又清空。
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
    try:
        multi_download_stock(
            all_tickers,
            save_root=os.path.join(DATASETS_ROOT, "pkls"),
            days_from_now=365 * 5,
            clear=clear,
            rm_invalid=rm_invalid,
            # worker=10 + 12 HK 节点轮换(2026-09-06): 每 400 只常规切节点 +
            # 连续 3 次 throttle 失败计数切换兜底(节点中途被限速立即切) + 健康探针。
            # 12 节点各自独立出口 IP 分摊单 IP 限速, 下载完复原到 isp。
            num_workers=10,
            file_format="pkl",  # Change to 'csv' or 'pkl'
            node_rotation=_get_hk_nodes(),
            rotate_every=ROTATE_EVERY,
        )
    finally:
        # 无论成功/失败/中断, 复原用户当前的 isp 节点配置
        _switch_clash_node(ORIGINAL_NODE)
        print(f"已复原节点 -> {ORIGINAL_NODE}")
    # 统计并输出耗时，格式为几分几秒
    elapsed = datetime.datetime.now() - start_time
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    print(f"Total time: {int(minutes)} min {int(seconds)} sec")

    data_root = os.path.join(DATASETS_ROOT, "pkls")
    # preprocessed_root = 'datasets/process_pkls'
    # preprocessor = StockPreprocessor(data_root, preprocessed_root,skip_neg_value=True)
    #
    # processed_files = preprocessor.preprocess_all()

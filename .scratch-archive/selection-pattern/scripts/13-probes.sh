#!/usr/bin/env bash
# 13 外部信息 · 连通性小量探测（2026-10-07 实跑一次，结果抄在 13-probes_out.txt；不要反复跑）。
# 每个下载件放进 scratchpad/13/dl-<名字>/ 新建空目录；全部走本机默认网络环境（未改任何代理设置），
# 只有 SEC 首次和 FRED 各多试了一次绕过代理直连（不改设置，只是那一次请求不走代理）。
S=/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/13
BUA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
SUA="TradeStrategy research ufgtb1-research@example.com"
probe(){ name=$1; url=$2; ua=$3; mkdir -p $S/dl-$name; curl -s -L -A "$ua" --max-time 25 --max-filesize 30000000 -o $S/dl-$name/body -w "$name %{http_code} %{size_download}B %{time_total}s\n" "$url" || echo "$name curl-exit $?"; sleep 1; }
# SEC 代码表（走代理与直连各一次）
curl -s -o $S/dl-sec-map/company_tickers_exchange.json -A "$SUA" --max-time 30 https://www.sec.gov/files/company_tickers_exchange.json
curl -s -o /dev/null --noproxy '*' -A "$SUA" --max-time 30 https://www.sec.gov/files/company_tickers_exchange.json
# SEC 申报索引页（核对接收时刻的时区）
#   https://www.sec.gov/Archives/edgar/data/1831651/000183165126000116/0001831651-26-000116-index.htm 等两页
# FINRA 每日场外卖空量：https://cdn.finra.org/equity/regsho/daily/CNMSshvol{20240102,20251231,20261002,20261005}.txt
# FINRA 空头持仓公开查询接口（免 key）：POST https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest
#   按结算日 2024-01-12 / 2026-09-15 分页拉全表；另探 2026-09-30（204 无数据）、2021-06-15、2019-12-31
probe nasdaq-earn 'https://api.nasdaq.com/api/calendar/earnings?date=2024-02-14' "$BUA"
probe gdelt 'https://api.gdeltproject.org/api/v2/doc/doc?query=%22Shoals%20Technologies%22&mode=artlist&format=json&maxrecords=5&startdatetime=20240101000000&enddatetime=20240301000000' "$BUA"
probe stocktwits 'https://api.stocktwits.com/api/2/streams/symbol/SHLS.json' "$BUA"
probe fred-vix 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS' "$BUA"
probe cboe-vix 'https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv' "$BUA"
probe stooq-iwm 'https://stooq.com/q/d/l/?s=iwm.us&i=d' "$BUA"
probe iborrow 'https://iborrowdesk.com/api/ticker/SHLS' "$BUA"
probe sec-ftd 'https://www.sec.gov/files/data/fails-deliver-data/cnsfails202401a.zip' "$SUA"
# SEC 内部人交易季度包（14MB，第一次 25 秒超时，第二次放宽到 180 秒）
#   https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2024q1_form345.zip
# Nasdaq 财报日历另 8 天：2024-11-07/08、2024-08-08/09、2025-05-08/09、2025-08-07/08；2026-08-12
# Nasdaq 接口 ETF 日线：https://api.nasdaq.com/api/quote/IWM/historical?assetclass=etf&fromdate=2021-10-01&todate=2026-10-06&limit=9999
# SEC 全文检索：8-K 含 "reverse stock split"，2024 年、2025 年各一次
# SEC 批量包大小（只取头信息）：daily-index/bulkdata/submissions.zip、daily-index/xbrl/companyfacts.zip

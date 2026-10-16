"""核对「只用价格与成交量定义」的美股横截面异象在各时段（尤其 2021 年后）是否还在。

数据（均为公开下载，路径作为参数传入，脚本本身不联网）:
  - JKP (Jensen-Kelly-Pedersen) 美国月度单因子收益: [usa]_[all_factors]_[monthly]_[{vw_cap,ew,vw}].zip
    + factor_details.xlsx（原论文引用与样本期）
  - Chen-Zimmermann (OpenAP 2025.10 版): cz_op.csv（原论文口径多空）、cz_deciles_vw.csv
    （十分位市值加权多空）、cz_signal_doc.csv。注意 OpenAP 包里叫 deciles_ew 的文件
    (PredictorAltPorts_Deciles) 实为「十分位 + 原论文加权」，并非等权，故不用。
  - Ken French: F-F_ST_Reversal_Factor_CSV.zip、F-F_Momentum_Factor_CSV.zip、F-F_LT_Reversal_Factor_CSV.zip

下载地址（复现用；CZ 三个大文件 >50MB，算完已删，需用 03-dl_cz.py 重下）:
  JKP: https://jkpfactors-data.s3.amazonaws.com/public/%5Busa%5D_%5Ball_factors%5D_%5Bmonthly%5D_%5B{w}%5D.zip
       https://github.com/bkelly-lab/jkp-data/raw/main/src/jkp/data/resources/factor_details.xlsx
  CZ : uv run --with openassetpricing python -I .scratch/selection-pattern/scripts/03-dl_cz.py <cz目录> signal_doc op deciles_vw
       （OpenAP release 2025.10，Google Drive 文件夹 1qQDuTsnyvWfEJR6nPBQZ8xxlq6bkLG_y）
  French: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{F-F_ST_Reversal_Factor,F-F_Momentum_Factor,
          F-F_LT_Reversal_Factor,F-F_Research_Data_Factors}_CSV.zip

用法（项目根目录）:
  uv run --with openpyxl python -I .scratch/selection-pattern/scripts/03-factor_recent.py \
      <jkp目录> <cz目录> <french目录> <输出csv>

口径:
  - 每条序列都是「按原论文预期方向」的多空月收益（%）。正数 = 仍按原方向赚钱。
    JKP / CZ 是否已翻号由脚本用相关性自检（与 French 因子比方向）后打印。
  - 时段: 全样本 / 2000 年前 / 2000-2010 / 2011-2020 / 2021-数据末尾 / 2021-2024（三源共同窗）/
    发表后（发表年份次年 1 月起）/ 原论文样本期内。
  - t 值 = 均值 / (标准差/√月数)，普通 t（未做 Newey-West）。
  - 2021+ 另给年化收益（均值×12）与年化夏普（均值/标准差×√12）。
"""
import re
import sys
import zipfile
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

# (中文名, JKP 代码列表, CZ 代码列表, French 列名)
SIGNALS = [
    ("短期反转(上月收益)", ["ret_1_0"], ["STreversal"], "ST_Rev"),
    ("动量 12-1", ["ret_12_1"], ["Mom12m"], "Mom"),
    ("动量 6-1", ["ret_6_1"], ["Mom6m"], None),
    ("动量 9-1", ["ret_9_1"], [], None),
    ("动量 3-1", ["ret_3_1"], [], None),
    ("中间段动量 12-7", ["ret_12_7"], ["IntMom"], None),
    ("残差动量 12-1(FF3)", ["resff3_12_1"], ["ResidualMomentum"], None),
    ("残差动量 6-1(FF3)", ["resff3_6_1"], [], None),
    ("离52周高点距离", ["prc_highprc_252d"], ["High52"], None),
    ("MAX(上月最大日收益)", ["rmax1_21d"], ["MaxRet"], None),
    ("MAX5(前5大日收益均值)", ["rmax5_21d"], [], None),
    ("MAX5/波动率", ["rmax5_rvol_21d"], [], None),
    ("特质波动 CAPM 21日", ["ivol_capm_21d"], [], None),
    ("特质波动 FF3 21日", ["ivol_ff3_21d"], ["IdioVol3F"], None),
    ("总波动 21日", ["rvol_21d"], ["RealizedVol"], None),
    ("日收益偏度 21日", ["rskew_21d"], ["ReturnSkew"], None),
    ("特质偏度 FF3 21日", ["iskew_ff3_21d"], ["ReturnSkew3F"], None),
    ("特质偏度 CAPM 21日", ["iskew_capm_21d"], [], None),
    ("协偏度", ["coskew_21d"], ["CoskewACX"], None),
    ("换手率", ["turnover_126d"], ["ShareVol", "VolMkt"], None),
    ("换手波动", ["turnover_var_126d"], ["std_turn"], None),
    ("成交额", ["dolvol_126d"], ["DolVol"], None),
    ("成交额波动", ["dolvol_var_126d"], ["VolSD"], None),
    ("零交易日 1月", ["zero_trades_21d"], ["zerotrade1M"], None),
    ("零交易日 6月", ["zero_trades_126d"], ["zerotrade6M"], None),
    ("零交易日 12月", ["zero_trades_252d"], ["zerotrade12M"], None),
    ("Amihud 非流动性", ["ami_126d"], ["Illiquidity"], None),
    ("高低价价差估计", ["bidaskhl_21d"], [], None),
    ("季节性 同月(去年)", ["seas_1_1an"], ["MomSeasonShort"], None),
    ("季节性 同月(2-5年前)", ["seas_2_5an"], ["MomSeason"], None),
    ("季节性 异月(2-5年前,反转)", ["seas_2_5na"], ["MomOffSeason"], None),
    ("长期反转 60-12", ["ret_60_12"], ["LRreversal"], "LT_Rev"),
    ("低beta (BAB beta)", ["betabab_1260d"], ["BetaFP"], None),
    ("低beta (60月)", ["beta_60m"], [], None),
    ("低下行beta", ["betadown_252d"], [], None),
    ("低beta (Dimson 21日)", ["beta_dimson_21d"], [], None),
    ("低价股", ["prc"], ["Price"], None),
    ("成交量趋势", [], ["VolumeTrend"], None),
    ("高成交量股的动量", [], ["MomVol"], None),
    ("趋势因子(均线组合)", [], ["TrendFactor"], None),
    ("价格滞后(R²)", [], ["PriceDelayRsq"], None),
]

# CZ 把 BetaFP 的原方向记为 +1（做多高 beta），与 JKP / BAB 论文的「做多低 beta」相反；
# 为与同组其他行可比，这里乘 -1 统一成「做多低 beta」。
CZ_FLIP = {"BetaFP"}

PERIODS = [
    ("全样本", None, None),
    ("2000前", None, "1999-12-31"),
    ("2000-2010", "2000-01-01", "2010-12-31"),
    ("2011-2020", "2011-01-01", "2020-12-31"),
    ("2021-末", "2021-01-01", None),
    ("2021-2024", "2021-01-01", "2024-12-31"),
]


MKT = None  # French Mkt-RF（%），main 里赋值


def capm_alpha(s: pd.Series) -> tuple[float, float]:
    """对 French 市场超额收益回归，返回 (alpha%/月, 普通 OLS t)。"""
    a = pd.concat([s, MKT], axis=1).dropna()
    if len(a) < 12:
        return np.nan, np.nan
    y, x = a.iloc[:, 0].values, a.iloc[:, 1].values
    X = np.column_stack([np.ones_like(x), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    s2 = resid @ resid / (len(y) - 2)
    se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[0, 0])
    return beta[0], beta[0] / se


def stats(s: pd.Series) -> dict:
    s = s.dropna()
    n = len(s)
    if n < 3:
        return dict(mean=np.nan, t=np.nan, n=n, alpha=np.nan, alpha_t=np.nan)
    m, sd = s.mean(), s.std(ddof=1)
    al, alt = capm_alpha(s)
    return dict(mean=m, t=m / (sd / np.sqrt(n)), n=n, ann=m * 12, sharpe=m / sd * np.sqrt(12),
                alpha=al, alpha_t=alt)


def load_jkp(d: Path) -> tuple[dict, pd.DataFrame]:
    """返回 {weight: DataFrame(date x factor, 单位%)} 与 direction 表。"""
    out, direc = {}, None
    for w in ["vw_cap", "ew", "vw"]:
        z = d / f"usa_all_factors_monthly_{w}.zip"
        with zipfile.ZipFile(z) as zf:
            name = zf.namelist()[0]
            df = pd.read_csv(zf.open(name), parse_dates=["date"])
        out[w] = df.pivot(index="date", columns="name", values="ret") * 100
        if direc is None:
            direc = df.groupby("name")["direction"].first()
    return out, direc


def load_jkp_details(d: Path) -> pd.DataFrame:
    x = pd.read_excel(d / "factor_details.xlsx")
    x = x.dropna(subset=["abr_jkp"]).drop_duplicates("abr_jkp").set_index("abr_jkp")
    x["pub_year"] = x["cite"].astype(str).str.extract(r"\((\d{4})\)")[0].astype(float)
    per = x["in-sample period"].astype(str).str.extract(r"(\d{4})\s*-\s*(\d{4})")
    x["is_start"], x["is_end"] = per[0].astype(float), per[1].astype(float)
    return x[["cite", "pub_year", "is_start", "is_end", "direction"]]


def load_cz(d: Path) -> tuple[dict, pd.DataFrame]:
    out = {}
    for tag, fn in [("op", "cz_op.csv"), ("vw", "cz_deciles_vw.csv")]:
        p = d / fn
        if not p.exists():
            continue
        df = pd.read_csv(p, usecols=["signalname", "port", "date", "ret"], dtype={"port": str})
        df = df[df["port"] == "LS"]
        df["date"] = pd.to_datetime(df["date"]) + pd.offsets.MonthEnd(0)
        piv = df.pivot(index="date", columns="signalname", values="ret")
        for c in CZ_FLIP & set(piv.columns):
            piv[c] = -piv[c]
        out[tag] = piv
    doc = pd.read_csv(d / "cz_signal_doc.csv").set_index("Acronym")
    return out, doc


def load_french(d: Path) -> pd.DataFrame:
    cols = {}
    for fn in ["F-F_ST_Reversal_Factor_CSV.zip", "F-F_Momentum_Factor_CSV.zip", "F-F_LT_Reversal_Factor_CSV.zip",
               "F-F_Research_Data_Factors_CSV.zip"]:
        with zipfile.ZipFile(d / fn) as zf:
            txt = zf.open(zf.namelist()[0]).read().decode("latin-1")
        lines = txt.splitlines()
        i0 = next(i for i, l in enumerate(lines) if l.startswith(","))
        block = [lines[i0]]
        for l in lines[i0 + 1:]:
            if not re.match(r"^\s*\d{6}\s*,", l):
                break
            block.append(l)
        df = pd.read_csv(StringIO("\n".join(block)))
        df.columns = ["ym"] + [c.strip() for c in df.columns[1:]]
        df["date"] = pd.to_datetime(df["ym"].astype(str), format="%Y%m") + pd.offsets.MonthEnd(0)
        df = df.set_index("date").drop(columns="ym").replace([-99.99, -999], np.nan)
        keep = ["Mkt-RF"] if "Mkt-RF" in df else [df.columns[0]]
        for c in keep:
            cols[c] = df[c]
    return pd.DataFrame(cols)


def sign_check(jkp, cz, ff):
    print("== 方向自检（与 French 因子的相关系数；French ST_Rev=做多输家、LT_Rev=做多长期输家）==")
    pairs = [("ret_1_0", "STreversal", "ST_Rev"), ("ret_12_1", "Mom12m", "Mom"), ("ret_60_12", "LRreversal", "LT_Rev")]
    for jc, cc, fc in pairs:
        for w in ["vw_cap", "ew"]:
            a = pd.concat([jkp[w][jc], ff[fc]], axis=1).dropna()
            print(f"  JKP {w:6s} {jc:10s} vs French {fc:6s}: corr={a.corr().iloc[0, 1]:+.2f} (n={len(a)})")
        for tag in cz:
            if cc in cz[tag]:
                a = pd.concat([cz[tag][cc], ff[fc]], axis=1).dropna()
                print(f"  CZ  {tag:6s} {cc:10s} vs French {fc:6s}: corr={a.corr().iloc[0, 1]:+.2f} (n={len(a)})")
    # CZ 十分位多空与原论文多空是否同向（对 Sign=-1 的信号尤其要看）
    print("== CZ 十分位多空 vs 原论文多空 同向性（Sign=-1 的信号）==")
    for _, jc, ccs, _ in [(None, s[1], s[2], None) for s in SIGNALS]:
        for cc in ccs:
            for tag in ["vw"]:
                if tag in cz and cc in cz[tag] and cc in cz["op"]:
                    a = pd.concat([cz[tag][cc], cz["op"][cc]], axis=1).dropna()
                    c = a.corr().iloc[0, 1]
                    if c < 0.3:
                        print(f"  !! CZ {tag} {cc}: corr with op = {c:+.2f}")


def summarize(series: pd.Series, pub_year=None, is_start=None, is_end=None) -> dict:
    row = {}
    s = series.dropna()
    row["起"] = s.index.min().strftime("%Y-%m") if len(s) else ""
    row["止"] = s.index.max().strftime("%Y-%m") if len(s) else ""
    for lab, a, b in PERIODS:
        x = s
        if a:
            x = x[x.index >= a]
        if b:
            x = x[x.index <= b]
        st = stats(x)
        row[f"{lab}_均值%"] = st["mean"]
        row[f"{lab}_t"] = st["t"]
        row[f"{lab}_月数"] = st["n"]
        row[f"{lab}_CAPMα%"] = st["alpha"]
        row[f"{lab}_αt"] = st["alpha_t"]
        if lab == "2021-末":
            row["2021-末_年化%"] = st.get("ann", np.nan)
            row["2021-末_夏普"] = st.get("sharpe", np.nan)
    # 稳健性: 2021 起但剔除 2022 年（2022 年投机股集体崩，近年很多结果靠它撑着）
    st = stats(s[(s.index >= "2021-01-01") & (s.index.year != 2022)])
    row["2021-末去2022_均值%"], row["2021-末去2022_t"], row["2021-末去2022_月数"] = st["mean"], st["t"], st["n"]
    row["发表年"] = pub_year
    if pub_year and not np.isnan(pub_year):
        st = stats(s[s.index.year > pub_year])
        row["发表后_均值%"], row["发表后_t"], row["发表后_月数"] = st["mean"], st["t"], st["n"]
    if is_start and is_end and not (np.isnan(is_start) or np.isnan(is_end)):
        x = s[(s.index.year >= is_start) & (s.index.year <= is_end)]
        st = stats(x)
        row["原样本期"] = f"{int(is_start)}-{int(is_end)}"
        row["原样本期_均值%"], row["原样本期_t"] = st["mean"], st["t"]
    return row


def main():
    jkp_dir, cz_dir, ff_dir, out_csv = map(Path, sys.argv[1:5])
    jkp, jdir = load_jkp(jkp_dir)
    jdet = load_jkp_details(jkp_dir)
    cz, czdoc = load_cz(cz_dir)
    ff = load_french(ff_dir)
    global MKT
    MKT = ff["Mkt-RF"]
    print("JKP 截止:", {w: str(v.index.max().date()) for w, v in jkp.items()})
    print("CZ  截止:", {t: str(v.index.max().date()) for t, v in cz.items()})
    print("French 截止:", str(ff.dropna(how="all").index.max().date()))
    sign_check(jkp, cz, ff)

    rows = []
    for zh, jcodes, ccodes, fcol in SIGNALS:
        for jc in jcodes:
            det = jdet.loc[jc] if jc in jdet.index else None
            py = det["pub_year"] if det is not None else np.nan
            for w in ["vw_cap", "ew", "vw"]:
                if jc not in jkp[w]:
                    print("缺 JKP", jc, w)
                    continue
                r = summarize(jkp[w][jc], py, det["is_start"] if det is not None else None,
                              det["is_end"] if det is not None else None)
                rows.append(dict(信号=zh, 来源="JKP", 代码=jc, 加权=w, 原方向=int(jdir[jc]),
                                 引用=det["cite"] if det is not None else "", **r))
        for cc in ccodes:
            d = czdoc.loc[cc] if cc in czdoc.index else None
            for tag in ["op", "vw"]:
                if tag not in cz or cc not in cz[tag]:
                    print("缺 CZ", cc, tag)
                    continue
                r = summarize(cz[tag][cc], d["Year"] if d is not None else np.nan,
                              d["SampleStartYear"] if d is not None else None,
                              d["SampleEndYear"] if d is not None else None)
                wlab = {"op": f"原论文口径({d['Stock Weight'] if d is not None else '?'})",
                        "vw": "十分位市值"}[tag]
                if cc in CZ_FLIP:
                    wlab += "[已翻号=做多低beta]"
                rows.append(dict(信号=zh, 来源="CZ", 代码=cc, 加权=wlab,
                                 原方向=(-d["Sign"] if cc in CZ_FLIP else d["Sign"]) if d is not None else np.nan,
                                 引用=f"{d['Authors']} ({d['Year']})" if d is not None else "", **r))
        if fcol:
            rows.append(dict(信号=zh, 来源="French", 代码=fcol, 加权="2x3 市值加权", **summarize(ff[fcol])))

    res = pd.DataFrame(rows)
    # 2019 年起逐年均值（%/月），看近年结果是否只靠某一年撑着
    yrows = []
    for zh, jcodes, ccodes, fcol in SIGNALS:
        srcs = [(f"JKP {w}", jc, jkp[w][jc]) for jc in jcodes for w in ["vw_cap", "ew"] if jc in jkp[w]]
        srcs += [(f"CZ {t}", cc, cz[t][cc]) for cc in ccodes for t in ["op", "vw"] if t in cz and cc in cz[t]]
        if fcol:
            srcs.append(("French", fcol, ff[fcol]))
        for src, code, ser in srcs:
            x = ser.dropna()
            x = x[x.index.year >= 2019]
            yrows.append(dict(信号=zh, 源=src, 代码=code, **{str(y): g.mean() for y, g in x.groupby(x.index.year)}))
    ydf = pd.DataFrame(yrows)
    ydf.to_csv(out_csv.with_name(out_csv.stem + "_yearly.csv"), index=False, float_format="%.3f", encoding="utf-8-sig")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(out_csv, index=False, float_format="%.4f", encoding="utf-8-sig")
    print("写出", out_csv, res.shape)

    pd.set_option("display.width", 300)
    pd.set_option("display.max_rows", 500)
    show = ["信号", "来源", "代码", "加权"]
    for lab, _, _ in PERIODS:
        if lab == "2021-2024":
            continue
        show += [f"{lab}_均值%", f"{lab}_t"]
    show += ["2021-末_月数", "2021-末_夏普", "发表后_均值%", "发表后_t"]
    print(res[show].round(2).to_string())
    # 紧凑版: 每格「均值/t」
    def cell(r, lab):
        m, t = r.get(f"{lab}_均值%"), r.get(f"{lab}_t")
        return "" if pd.isna(m) else f"{m:+.2f}({t:+.1f})"
    labs = ["全样本", "2000前", "2000-2010", "2011-2020", "2021-末", "2021-末去2022", "发表后"]
    comp = res.apply(lambda r: pd.Series({"信号": r["信号"], "源": r["来源"], "代码": r["代码"], "加权": r["加权"],
                                          **{l: cell(r, l) for l in labs},
                                          "21+夏普": f"{r['2021-末_夏普']:+.2f}",
                                          "全样本α": f"{r['全样本_CAPMα%']:+.2f}({r['全样本_αt']:+.1f})",
                                          "21+α": f"{r['2021-末_CAPMα%']:+.2f}({r['2021-末_αt']:+.1f})"}), axis=1)
    comp.to_csv(out_csv.with_name(out_csv.stem + "_compact.csv"), index=False, encoding="utf-8-sig")
    print(comp.to_string())


if __name__ == "__main__":
    main()

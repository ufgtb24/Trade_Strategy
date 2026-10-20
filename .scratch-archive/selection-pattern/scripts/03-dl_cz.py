"""下载 Chen-Zimmermann Open Source Asset Pricing 的组合收益与信号说明，存成 CSV。

用法（项目根目录）:
    uv run --with openassetpricing python -I .scratch/selection-pattern/scripts/03-dl_cz.py <输出目录> [数据名 ...]
数据名默认: signal_doc op ；可加 deciles_ew deciles_vw 等（见 OpenAP.list_port）。
"""
import sys
from pathlib import Path

from openassetpricing import OpenAP


def main():
    out = Path(sys.argv[1])
    names = sys.argv[2:] or ["signal_doc", "op"]
    out.mkdir(parents=True, exist_ok=True)
    ap = OpenAP()
    for name in names:
        if name == "list":
            ap.list_port()
            continue
        if name == "signal_doc":
            df = ap.dl_signal_doc("pandas")
        else:
            df = ap.dl_port(name, "pandas")
        p = out / f"cz_{name}.csv"
        df.to_csv(p, index=False)
        print(name, df.shape, "->", p)


if __name__ == "__main__":
    main()

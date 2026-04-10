"""实盘 UI 启动入口。

用法: uv run python -m BreakoutStrategy.live
"""

import sys
import tkinter as tk

from BreakoutStrategy.live.app import LiveApp
from BreakoutStrategy.live.config import LiveConfig
from BreakoutStrategy.UI.styles import configure_global_styles


def main() -> None:
    try:
        config = LiveConfig.load()
    except FileNotFoundError as e:
        print(f"配置文件缺失: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"配置加载失败: {e}", file=sys.stderr)
        sys.exit(1)

    filter_yaml = config.trial_dir / "filter.yaml"
    if not filter_yaml.exists():
        print(f"Trial 目录缺失 filter.yaml: {filter_yaml}", file=sys.stderr)
        sys.exit(1)

    root = tk.Tk()
    root.title("Breakout Live")
    root.geometry("1400x800")
    configure_global_styles(root)

    app = LiveApp(root, config)
    root.mainloop()


if __name__ == "__main__":
    main()

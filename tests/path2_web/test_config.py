from path2_web.config import load_config, save_config, DEFAULT_CONFIG


def test_load_missing_returns_default(tmp_path):
    cfg = load_config(tmp_path / "nope.yaml")
    assert cfg["dataset_dir"] == DEFAULT_CONFIG["dataset_dir"]
    assert cfg["scan"]["workers"] == DEFAULT_CONFIG["scan"]["workers"]


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "path2_web.yaml"
    cfg = load_config(path)
    cfg["scan"]["workers"] = 4
    cfg["last_selected_pattern"] = "bottom_burst"
    save_config(cfg, path)
    again = load_config(path)
    assert again["scan"]["workers"] == 4
    assert again["last_selected_pattern"] == "bottom_burst"


def test_load_merges_partial_over_default(tmp_path):
    path = tmp_path / "partial.yaml"
    path.write_text("scan:\n  workers: 16\n")
    cfg = load_config(path)
    assert cfg["scan"]["workers"] == 16                       # 文件覆盖
    assert cfg["scan"]["start_date"] == DEFAULT_CONFIG["scan"]["start_date"]  # 缺项补默认
    assert cfg["dataset_dir"] == DEFAULT_CONFIG["dataset_dir"]


def test_label_horizon_default_and_merge(tmp_path):
    """新键 label_horizon:缺文件回默认 20;旧 yaml 缺项被 scan 子树 merge 兜底。"""
    from path2_web.config import load_config
    p = tmp_path / "cfg.yaml"
    assert load_config(p)["scan"]["label_horizon"] == 20          # 缺文件 → 默认
    p.write_text("scan:\n  start_date: '2024-01-01'\n")
    cfg = load_config(p)
    assert cfg["scan"]["label_horizon"] == 20                     # 旧文件缺项 → 兜底
    assert cfg["scan"]["start_date"] == "2024-01-01"              # 既有项不被覆盖

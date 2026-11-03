from pathlib import Path

import pytest

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


def test_default_web_data_dir_is_train_snapshot():
    """网页读行情的目录默认是截到训练段末日的那份副本。"""
    assert DEFAULT_CONFIG["view_dataset_dir"] == "datasets/pkls_until_20251231"


def test_annotation_dir_and_machine_defaults(tmp_path):
    """配置缺省:标注目录是 repo root 下的 annotations/,机器名是本机主机名。"""
    import socket
    from path2_web.config import annotation_dir, machine_name
    repo = Path(__file__).resolve().parents[2]
    cfg = load_config(tmp_path / "nope.yaml")
    assert annotation_dir(cfg) == repo / "annotations"
    assert machine_name(cfg) == socket.gethostname()
    p = tmp_path / "old.yaml"                                    # 旧配置文件没有这两项 → 同样回落默认
    p.write_text("scan:\n  workers: 2\n")
    assert annotation_dir(load_config(p)) == repo / "annotations"
    assert machine_name(load_config(p)) == socket.gethostname()


def test_annotation_dir_and_machine_overrides(tmp_path):
    """配置里改了,读到的是改后的值;相对路径按 repo root 解析。"""
    from path2_web.config import annotation_dir, machine_name
    repo = Path(__file__).resolve().parents[2]
    p = tmp_path / "cfg.yaml"
    p.write_text(f"annotation_dir: {tmp_path / 'ann'}\nmachine: upc\n")
    cfg = load_config(p)
    assert annotation_dir(cfg) == tmp_path / "ann"
    assert machine_name(cfg) == "upc"
    p.write_text("annotation_dir: sub/ann\n")
    assert annotation_dir(load_config(p)) == repo / "sub" / "ann"


def test_machine_name_rejects_path_like(tmp_path):
    from path2_web.config import machine_name
    for bad in ("../x", "a/b", "a b", ".hidden", "yu-pc", "pc.lan"):
        with pytest.raises(ValueError):
            machine_name({"machine": bad})


def test_save_keeps_machine_unresolved(tmp_path):
    """网页改配置会整份写回进 git 的 yaml:写回的仍是 null 和相对路径,不写成本机主机名、绝对路径。"""
    import yaml
    p = tmp_path / "cfg.yaml"
    cfg = load_config(p)
    cfg["last_selected_pattern"] = "bb_v1"
    save_config(cfg, p)
    saved = yaml.safe_load(p.read_text())
    assert saved["machine"] is None
    assert saved["annotation_dir"] == "annotations"

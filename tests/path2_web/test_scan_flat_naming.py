"""scan.py 扁平结果文件的命名/列表/改名单元测试(Task 1)。"""
import json
import pytest
from path2_web.scan import (write_result_file_flat, list_scans_flat,
                            load_scan_flat, delete_scan_flat, rename_scan_flat)


def _result(scan_ts: str, name: str) -> dict:
    return {"pattern_ids": ["bo_only"], "per_pattern": {},
            "scan": {"scan_ts": scan_ts, "name": name, "hits": 0, "errors": 0,
                     "scanned": 1, "start_date": "2024-01-01", "end_date": "2024-06-30",
                     "workers": 1, "dataset_dir": "", "note": name,
                     "win_start": "", "win_end": "", "label_horizon": 20, "partial": False},
            "results": []}


def test_write_uses_name_as_filename(tmp_path):
    p = write_result_file_flat(_result("20260729T100000", "tb深度28-38"),
                               "tb深度28-38", str(tmp_path))
    assert p.name == "tb深度28-38.json"
    assert json.loads(p.read_text())["scan"]["name"] == "tb深度28-38"


def test_list_returns_name_and_sorts_by_internal_scan_ts(tmp_path):
    write_result_file_flat(_result("20260729T100000", "early"), "early", str(tmp_path))
    write_result_file_flat(_result("20260729T200000", "late"), "late", str(tmp_path))
    rows = list_scans_flat(str(tmp_path))
    assert [r["name"] for r in rows] == ["late", "early"]   # 按文件内 scan_ts 倒序,非 stem 字典序
    assert rows[0]["scan_ts"] == "20260729T200000"


def test_list_falls_back_to_stem_when_internal_scan_ts_missing(tmp_path):
    (tmp_path / "scans").mkdir()
    (tmp_path / "scans" / "20260101T000000.json").write_text(
        json.dumps({"pattern_ids": [], "scan": {"hits": 0}}))
    rows = list_scans_flat(str(tmp_path))
    assert rows[0]["name"] == "20260101T000000"
    assert rows[0]["scan_ts"] == "20260101T000000"   # 回退 stem,排序仍可用


def test_load_and_delete_by_name(tmp_path):
    write_result_file_flat(_result("20260729T100000", "myexp"), "myexp", str(tmp_path))
    assert load_scan_flat("myexp", str(tmp_path))["scan"]["name"] == "myexp"
    delete_scan_flat("myexp", str(tmp_path))
    assert not (tmp_path / "scans" / "myexp.json").exists()


def test_rename_moves_file_and_syncs_note_and_name(tmp_path):
    write_result_file_flat(_result("20260729T100000", "old"), "old", str(tmp_path))
    rename_scan_flat("old", "new", str(tmp_path))
    assert not (tmp_path / "scans" / "old.json").exists()
    blob = json.loads((tmp_path / "scans" / "new.json").read_text())
    assert blob["scan"]["note"] == "new"
    assert blob["scan"]["name"] == "new"


def test_rename_missing_raises_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError):
        rename_scan_flat("nope", "new", str(tmp_path))


def test_rename_collision_raises_fileexists(tmp_path):
    write_result_file_flat(_result("20260729T100000", "a"), "a", str(tmp_path))
    write_result_file_flat(_result("20260729T200000", "b"), "b", str(tmp_path))
    with pytest.raises(FileExistsError):
        rename_scan_flat("a", "b", str(tmp_path))

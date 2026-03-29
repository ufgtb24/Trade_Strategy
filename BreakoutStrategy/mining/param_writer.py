"""
参数文件生成器

读取 threshold_optimizer 优化后的阈值（factor_filter.yaml），
将其写入 all_factor_mined.yaml：复制 all_factor.yaml 的完整结构，
替换 quality_scorer 中各因子的 thresholds 为单一二值阈值，
values 由 mode 方向决定：gte→[1.2](奖励)，lte→[0.8](惩罚)。

未参与优化的因子（不在 FACTOR_REGISTRY 中）保持原值。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from BreakoutStrategy.factor_registry import get_active_factors, get_factor


def build_mined_params(base_yaml_path: str, filter_yaml_path: str) -> tuple[dict, list[str]]:
    """
    合并 all_factor.yaml 的完整结构与 factor_filter.yaml 的优化阈值。

    Args:
        base_yaml_path: all_factor.yaml 路径（完整结构模板）
        filter_yaml_path: factor_filter.yaml 路径（含优化阈值）

    Returns:
        (合并后的完整 YAML dict, 已应用优化的因子 key 列表)
    """
    with open(base_yaml_path) as f:
        base = yaml.safe_load(f)

    with open(filter_yaml_path) as f:
        filter_data = yaml.safe_load(f)

    # 从 factor_filter.yaml 的 _meta.optimization.thresholds 读取优化阈值
    optimization = filter_data.get('_meta', {}).get('optimization', {})
    mined_thresholds = optimization.get('thresholds', {})

    if not mined_thresholds:
        raise ValueError(
            f"No optimization thresholds found in {filter_yaml_path}. "
            "Run threshold_optimizer first."
        )

    # 构建 key → yaml_key 映射
    key_to_yaml_key = {f.key: f.yaml_key for f in get_active_factors()}

    # 替换 quality_scorer 中已优化因子的 thresholds 和 values
    qs = base.get('quality_scorer', {})
    applied = []

    for key, threshold in mined_thresholds.items():
        yaml_key = key_to_yaml_key.get(key)
        if not yaml_key:
            continue

        # 为 REGISTRY 中有但 all_factor.yaml 中无的因子合成默认条目
        if yaml_key not in qs:
            fi = get_factor(key)
            qs[yaml_key] = {
                'enabled': True,
                'thresholds': list(fi.default_thresholds),
                'values': list(fi.default_values),
                **{sp.yaml_name: sp.default for sp in fi.sub_params},
            }

        entry = qs[yaml_key]
        entry['thresholds'] = [round(float(threshold), 4)]
        # mode 优先级：FactorInfo.mining_mode > YAML mode > 默认 'gte'
        fi = get_factor(key)
        mode = fi.mining_mode if fi.mining_mode is not None else entry.get('mode', 'gte')
        entry['mode'] = mode
        entry['values'] = [0.8] if mode == 'lte' else [1.2]
        applied.append(key)

    return base, applied


def write_mined_yaml(data: dict, output_path: str | Path, applied: list[str]):
    """写入 all_factor_mined.yaml"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = (
        "# configs/params/all_factor_mined.yaml\n"
        "# 由 BreakoutStrategy.mining.param_writer 自动生成\n"
        f"# 已优化因子: {', '.join(applied)}\n"
        "# thresholds = 挖掘阈值, values: gte→1.2(奖励) lte→0.8(惩罚)\n\n"
    )

    with open(output_path, 'w') as f:
        f.write(header)
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def main(base_yaml, filter_yaml, output_yaml):
    print(f"Base config:  {base_yaml}")
    print(f"Filter file:  {filter_yaml}")

    data, applied = build_mined_params(base_yaml, filter_yaml)

    print(f"\n  Applied mined thresholds to {len(applied)} factors: {applied}")

    # 显示替换结果
    qs = data.get('quality_scorer', {})
    key_to_yaml_key = {f.key: f.yaml_key for f in get_active_factors()}
    for key in applied:
        yaml_key = key_to_yaml_key.get(key)
        if yaml_key:
            entry = qs[yaml_key]
            print(f"    {key:<10s}: mode={entry['mode']}  "
                  f"thresholds={entry['thresholds']}  values={entry['values']}")

    write_mined_yaml(data, output_yaml, applied)
    print(f"\n  Output: {output_yaml}")


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    main(
        base_yaml=str(PROJECT_ROOT / "configs/params/all_factor.yaml"),
        filter_yaml=str(PROJECT_ROOT / "configs/params/factor_filter.yaml"),
        output_yaml=str(PROJECT_ROOT / "configs/params/all_factor_mined.yaml"),
    )

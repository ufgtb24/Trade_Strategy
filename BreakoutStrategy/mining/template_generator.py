"""
模板枚举 + YAML 输出工具

从 factor_analysis_data 枚举所有 factor 组合（二值化触发），
计算 count/median/q25 统计量，筛选 n >= min_count 的组合，
按 median 降序输出到 factor_filter.yaml。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from BreakoutStrategy.factor_registry import get_level_cols, get_factor_display, LABEL_COL


# ---------------------------------------------------------------------------
# 自定义 YAML Dumper: 纯字符串短列表使用行内格式
# ---------------------------------------------------------------------------

class InlineListDumper(yaml.SafeDumper):
    """factors 列表使用 flow style: [age, volume, height]"""
    pass


def _str_list_representer(dumper, data):
    """短字符串列表 → flow style"""
    if all(isinstance(item, str) for item in data) and len(data) <= 15:
        return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data)


InlineListDumper.add_representer(list, _str_list_representer)


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------

def generate_templates(df: pd.DataFrame, min_count: int) -> list[dict]:
    """
    二值化 → 组合枚举 → 统计 → 筛选排序 → 返回模板列表

    Args:
        df: 包含 level_cols 和 LABEL_COL 的 DataFrame
        min_count: 组合最少出现次数

    Returns:
        按 median 降序排列的模板列表，每个模板包含 name/factors/count/median/q25
    """
    level_cols = get_level_cols()
    factor_display = get_factor_display()

    triggered = pd.DataFrame()
    for col in level_cols:
        triggered[col] = (df[col] > 0).astype(int)

    short_names = [factor_display.get(c, c) for c in level_cols]

    def make_combo_name(row):
        parts = []
        for i, col in enumerate(level_cols):
            if row[col] == 1:
                parts.append(short_names[i])
        return '+'.join(parts) if parts else 'None'

    combo_labels = triggered.apply(make_combo_name, axis=1)

    analysis_df = pd.DataFrame({
        'combination': combo_labels,
        LABEL_COL: df[LABEL_COL].values,
    })

    combo_stats = analysis_df.groupby('combination').agg(
        count=(LABEL_COL, 'count'),
        median=(LABEL_COL, 'median'),
        q25=(LABEL_COL, lambda x: x.quantile(0.25)),
    ).reset_index()

    combo_stats = combo_stats[combo_stats['combination'] != 'None']
    combo_stats = combo_stats[combo_stats['count'] >= min_count]
    combo_stats = combo_stats.sort_values('median', ascending=False).reset_index(drop=True)

    templates = []
    for _, row in combo_stats.iterrows():
        name = row['combination']
        factors = name.split('+')
        templates.append({
            'name': name,
            'factors': factors,
            'count': int(row['count']),
            'median': round(float(row['median']), 4),
            'q25': round(float(row['q25']), 4),
        })

    return templates


def build_yaml_output(templates: list[dict], df: pd.DataFrame,
                      input_csv: str, min_count: int,
                      generator: str = 'BreakoutStrategy.mining.template_generator') -> dict:
    """
    构建含 _meta 的完整 YAML dict

    Args:
        templates: generate_templates() 的输出
        df: 原始 DataFrame（用于计算 baseline）
        input_csv: 输入文件路径（记录到 _meta）
        min_count: 最小样本量（记录到 _meta）
        generator: 生成器标识

    Returns:
        完整的 YAML 字典，含 _meta 和 templates
    """
    baseline_median = round(float(df[LABEL_COL].median()), 4)

    return {
        '_meta': {
            'version': 3,
            'generated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'data_source': str(input_csv),
            'sample_size': int(len(df)),
            'baseline_median': baseline_median,
            'min_count': min_count,
            'generator': generator,
            'total_templates': len(templates),
        },
        'templates': templates,
    }


def print_summary(yaml_data: dict):
    """打印摘要: 模板数 / baseline / Top 10 / Bottom 5"""
    meta = yaml_data['_meta']
    templates = yaml_data['templates']

    print(f"\n{'=' * 60}")
    print(f"Factor Filter Summary")
    print(f"{'=' * 60}")
    print(f"  Sample size:     {meta['sample_size']}")
    print(f"  Baseline median: {meta['baseline_median']}")
    print(f"  Total templates: {meta['total_templates']}")
    print(f"  Min count:       {meta['min_count']}")

    if templates:
        above = sum(1 for t in templates if t['median'] >= meta['baseline_median'])
        below = len(templates) - above
        print(f"  Above baseline:  {above}")
        print(f"  Below baseline:  {below}")

        print(f"\n--- Top 10 ---")
        for i, t in enumerate(templates[:10]):
            print(f"  {i+1:2d}. {t['name']:<50s} count={t['count']:4d}  median={t['median']:.4f}  q25={t['q25']:.4f}")

        print(f"\n--- Bottom 5 ---")
        for t in templates[-5:]:
            print(f"      {t['name']:<50s} count={t['count']:4d}  median={t['median']:.4f}  q25={t['q25']:.4f}")

    print(f"{'=' * 60}\n")


def write_yaml(yaml_data: dict, output_path: str | Path,
               header_comment: str = "# 由 BreakoutStrategy.mining 自动生成\n"):
    """将 yaml_data 写入文件"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(header_comment)
        yaml.dump(yaml_data, f, Dumper=InlineListDumper,
                  default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(input_csv, output_yaml, min_count):
    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    print(f"  Rows: {len(df)}")

    level_cols = get_level_cols()
    missing = [c for c in level_cols + [LABEL_COL] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    before = len(df)
    df = df.dropna(subset=[LABEL_COL])
    if len(df) < before:
        print(f"  Dropped {before - len(df)} rows with NaN label")

    templates = generate_templates(df, min_count)
    print(f"  Generated {len(templates)} templates (min_count={min_count})")

    yaml_data = build_yaml_output(templates, df, input_csv, min_count)
    write_yaml(yaml_data, output_yaml,
               header_comment="# configs/params/factor_filter.yaml\n"
                              "# 由 BreakoutStrategy.mining.template_generator 自动生成\n\n")
    print(f"  Output: {output_yaml}")
    print_summary(yaml_data)


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    main(
        input_csv=str(PROJECT_ROOT / "outputs/analysis/factor_analysis_data.csv"),
        output_yaml=str(PROJECT_ROOT / "configs/params/factor_filter.yaml"),
        min_count=10,
    )

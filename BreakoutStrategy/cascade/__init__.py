"""
级联验证模块

桥接 mining（模板验证）和 news_sentiment（情感分析），
对 top-K 模板命中的突破样本追加情感过滤，
产出级联统计报告评估联合筛选的增量价值。

核心组件:
- models: 数据类 (BreakoutSample, CascadeResult, CascadeReport)
- filter: 情感筛选逻辑（阈值判定 + 分类标记）
- batch_analyzer: 核心编排（提取样本 → 批量情感分析 → 合并结果）
- reporter: Markdown 级联报告生成

使用方式:
    from BreakoutStrategy.cascade.batch_analyzer import run_cascade
    report = run_cascade(df_test, keys_test, top_k_keys, top_k_names)

命令行入口:
    uv run -m BreakoutStrategy.cascade
"""

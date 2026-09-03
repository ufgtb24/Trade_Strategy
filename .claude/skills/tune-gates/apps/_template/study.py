# -*- coding: utf-8 -*-
"""tune-gates · study 声明模板。复制为 apps/<app>/study.py 后填全部 8 项。

本文件是换 app 时**唯一**要写的东西;分类(W/F/D/E)、长表列名、谓词轴、end_node、bound 节点
等一切能从 spec 推出来的内容都不在这里——由 app_setup.py 生成 classification.json。
只放「推不出来」的:底座在哪、搜什么档、参照点在哪、哪些格子机制上恒真。

键写法:SCAN_GRID / WHERE_LEVELS / TIGHT_WHERES 用 (section, field) 元组键(与 Params 的
yaml section 对齐);REF_POINT 与 FLAG_RULES 里的 cell 用 "section.field" 点号键。
"""

APP_MODULE = "path2_apps.<app>.dag_spec"       # 提供 Params / build_pattern / eval_meta 的模块
BASE_YAML = "params.yaml"                      # 相对 app 包目录;底座 = 搜索空间之外的一切参数取值

# 宽进覆盖:把 where 类参数放到机制下限、把过滤型闸关掉,让完整取值空间进池
WIDE_OVERRIDES = {
    # "<section>": {"<where_field>": <机制下限>, "<gate_field>": None},
}

# D/F 维档位(真扫维与过滤型维;F 维由探针判定、不进检测笛卡尔积)。4 档左右;先查列分布再定档
SCAN_GRID = {
    # ("<section>", "<param>"): [v1, v2, v3, v4],
}

# W 维档位(纯 where 阈值)。放 F 维会被 classify() 拒绝——分类以探针为准,不凭参数名猜
WHERE_LEVELS = {
    # ("<section>", "<where_param>"): [v_loose, v_mid, v_tight],
}

# 参照格:必须恰好覆盖全部 D 维(app_setup 校验);通常取生产参数在网格上的落点
REF_POINT = {
    # "<section>.<param>": <生产值>,
}

# 对拍用的收紧 where 套:app 的候选生产点;键 ⊆ SCAN_GRID ∪ WHERE_LEVELS,可含 F 维
TIGHT_WHERES = {
    # "<name>": {("<section>", "<where_param>"): <收紧值>, ...},
}

# 格级机制标记:cell(点号键 dict)→ 标记文本或 None。用于 cells.csv 的 flags 列
# cell 是 region_core.cell_coords() 的输出,两套键名不同、别按直觉都写参数名:
#   - combo 轴(来自 SCAN_GRID 的 D 维)用参数名 "<section>.<param>"(与 SCAN_GRID 键一致)
#   - pred 轴(F/W 维)用长表列名 "<node_id>.<field>"(classify() 探出来的 detector 字段名,
#     node_id 是 dag 里的节点名、field 是该 node 上的属性名——通常不等于参数名)
# 写错会在 cells.csv 阶段裸 KeyError;实例见 apps/<app>/notes.md
FLAG_RULES = [
    # lambda c: "<说明>" if c["<a>"] >= c["<b>"] > 0 else None,
]

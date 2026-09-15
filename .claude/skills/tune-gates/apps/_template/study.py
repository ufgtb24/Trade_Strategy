# -*- coding: utf-8 -*-
"""tune-gates · 研究声明模板。复制为 apps/<app>/windows/<window>/study.py 后填全部 7 项(DESIGN 可选)。

本文件是换 app / 开新窗口时**唯一**要写的东西;分类(W/F/D/E)、长表列名、谓词轴、end_node、bound 节点
等一切能从 spec 推出来的内容都不在这里——由 tune.setup 生成同目录的 classification.json。
只放「推不出来」的:底座在哪、搜什么档、工作点在哪、按什么设计展开检测组合。
通常不手写,由 tune.install 渲染生成(工作点自动推出)。

键写法:SCAN_GRID / WHERE_LEVELS / TIGHT_WHERES 用 (section, field) 元组键(与 Params 的
yaml section 对齐);REF_POINT 用 "section.field" 点号键。
"""

APP_MODULE = "path2_apps.<app>.dag_spec"       # 提供 Params / build_pattern / eval_meta 的模块
BASE_YAML = "params.yaml"                      # 相对 app 包目录;底座 = 搜索空间之外的一切参数取值

# 宽进覆盖:把 where 类参数放到机制下限、把过滤型闸关掉,让完整取值空间进池
WIDE_OVERRIDES = {
    # "<section>": {"<where_field>": <机制下限>, "<gate_field>": None},
}

# D/F 维档位(真扫维与过滤型维;F 维由探针判定、不进检测组合)。先查列分布再定档
SCAN_GRID = {
    # ("<section>", "<param>"): [v1, v2, v3],
}

# W 维档位(纯 where 阈值)。放 F 维会被 classify() 拒绝——分类以探针为准,不凭参数名猜
WHERE_LEVELS = {
    # ("<section>", "<where_param>"): [v_loose, v_mid, v_tight],
}

# 工作点:正式参数(params.yaml,未套宽进覆盖)在全部轴(SCAN_GRID ∪ WHERE_LEVELS)档位上的落点,
# 取值必须精确在档位表里(tune.setup 校验)
REF_POINT = {
    # "<section>.<param>": <正式值>,
}

# 一致性验证用的收紧 where 套:app 的候选生产点;键 ⊆ SCAN_GRID ∪ WHERE_LEVELS,可含 F 维
TIGHT_WHERES = {
    # "<name>": {("<section>", "<where_param>"): <收紧值>, ...},
}

# 研究设计(可选,缺省 "grid"):"grid" = 检测参数全部笛卡尔积;
# "screen" = 工作点 + 每个检测参数单独翻到其他档 + 任意两个一起翻
DESIGN = "grid"

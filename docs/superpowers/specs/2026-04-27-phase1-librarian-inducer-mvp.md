# Feature Mining Phase 1 — Librarian + Inducer MVP

**日期**：2026-04-27
**关联主 spec**：`docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md` §5.4 Phase 1 行
**前置 Phase 0**：`docs/superpowers/plans/2026-04-27-phase0-data-baseline.md`（已完成，35 测试 PASS，端到端 vertical slice 跑通）
**目标读者**：实施者（subagent-driven 模式）+ 后续 Phase 1.5 / 2 / 3 设计者

---

## §0 目标与范围

### 0.1 Phase 1 目标

**验证"Inducer batch 多图对比 + Librarian Beta-Binomial 累积"能否产出有用的 candidate features**。

实施完成后能回答的问题：
- 给 GLM-4V-Flash 5 张同一 ticker 的 K 线图，它能不能找到跨样本共性？
- Librarian 的 (α, β) 累积 + L0 cosine 合并能不能形成不重复的 features 库？
- 库的 P5 信号是否有判别力（能不能区分 strong vs weak feature）？

### 0.2 范围边界

**包含**（按主 spec §5.4 Phase 1 + brainstorming 决策）：
- Inducer 多图 batch 模式（GLM-4V-Flash 单次最多 5 张）
- Librarian 核心：upsert_candidate / update / recompute / lookup_by_cosine
- features yaml schema（按主 spec §4.2 完整字段，含 Phase 1.5+ 字段置 null）
- ObservationLog 按 (sample, feature) 粒度
- Beta-Binomial update + 派生 P5
- L0 fastembed cosine（复用 news_sentiment.embedding，薄封装）
- Phase 1 入口脚本 `scripts/feature_mining_phase1.py`

**不包含**（推迟到对应 Phase）：
- DeepSeek L1 verify（Phase 1.5）
- merge-policy 三选项 / Replay 队列 / epoch_tag 实际使用（Phase 1.5）
- Path V incremental 模式（Phase 2）
- CLI 命令套件 `feature-mine *`（Phase 2）
- Critic 角色（Phase 3）
- Reshuffle / archetype hint（Phase 4+）

### 0.3 关键约束（来自 brainstorming + Phase 0 实施经验）

1. **Inducer 是 Python module，不是 Claude subagent**：Phase 1 入口是 Python 进程，subagent 在运行时不可用。Inducer 实质是 Python 函数封装 GLM-4V-Flash API 调用。spec §1.1 的"Inducer = Opus subagent"是架构愿景占位，本期不实施 subagent 语义（详见 §12 实施期决策附录）。

2. **GLM-4V-Flash 单次最多 5 张图**：实验证实服务端硬限（错误码 1210）。Phase 1 默认 batch_size=5；Phase 1.5+ 若需要 ≥6 可分块多次调用 + Librarian L0 dedup 聚合。

3. **OHLCV 列名为 lowercase**：Phase 0 修复了列名 case 不一致 bug（PKL 文件用 lowercase，feature_library 与之一致）。Phase 1 所有新模块沿用 lowercase。

4. **入口脚本不用 argparse**：参数声明在 main() 起始位置（CLAUDE.md 规范，与 Phase 0 一致）。

5. **注释中文，print 文案中文，界面英文**（CLAUDE.md）。

---

## §1 架构

### 1.1 模块依赖图

```
                     scripts/feature_mining_phase1.py (entry)
                                    │
                                    ▼
                           ┌────────────────┐
                           │   Librarian    │ ◄─── Phase 0 复用
                           │  (核心 API)    │     paths / sample_id /
                           └───┬───────┬────┘     sample_meta /
                               │       │          consolidation_fields
                ┌──────────────┘       └─────────────┐
                ▼                                    ▼
       ┌────────────────┐                  ┌──────────────────┐
       │   Inducer      │                  │  ObservationLog  │
       │ (batch 调用)   │                  │  (按 sample 粒度) │
       └───┬───────┬────┘                  └─────────┬────────┘
           │       │                                 │
           ▼       ▼                                 ▼
   ┌────────────┐  ┌─────────────────┐    ┌──────────────────┐
   │ Inducer    │  │ GLM4VBackend    │    │  FeatureStore    │
   │ Prompts    │  │ (扩展 +batch_   │    │ (features yaml   │
   │            │  │  describe)      │    │  CRUD)           │
   └────────────┘  └─────────────────┘    └──────────────────┘
                                                    │
                                                    ▼
                                          ┌──────────────────┐
                                          │ Embedding L0     │
                                          │ (fastembed       │
                                          │  cosine)         │
                                          └──────────────────┘
```

依赖方向严格向下。无循环依赖。Phase 0 模块不被本 Phase 修改（除 GLM4VBackend 扩展一个新方法）。

### 1.2 数据流（entry script perspective）

```
1. ENSURE_SAMPLES（复用 Phase 0）
   user 指定 ticker + sample_count
   → 检查 feature_library/samples/<id>/ 是否存在（chart.png + meta.yaml + nl_description.md）
   → 缺失的样本调用 preprocess_sample（Phase 0）补齐
   → 返回 list[sample_id]

2. INDUCE（Phase 1 新增）
   Inducer.batch_induce(sample_ids[:5])
   → 读 5 张 chart.png + 5 份 meta.yaml + 5 份 nl_description.md
   → 调 GLM4VBackend.batch_describe（多图单次调用）
   → 解析 LLM 输出为 list[Candidate]
   每个 Candidate: {text, supporting_sample_ids, K, N, raw_response_excerpt}

3. UPSERT（Phase 1 新增）
   for candidate in candidates:
       Librarian.upsert_candidate(
           candidate=candidate,
           batch_sample_ids=sample_ids[:5],  # 用于 N=batch 大小推断
           source="ai_induction",
       )
       # 内部：embed candidate.text → L0 cosine 查库 → 命中合并 / miss 新建
       # 按每个 sample 写 ObservationLog 条目
       # 重算 (α, β) + signal P5

4. SUMMARY
   FeatureStore.list_all() → 打印每条 feature:
     id / text 摘要 / α / β / P5 / status_band / observed_samples 数
```

### 1.3 与主 spec §2.1 数据流的关系

主 spec §2.1 显示完整数据流（CLI Scheduler / Inducer / Librarian / P5 派生状态带）。Phase 1 实施其中的 **CLI 部分以下**（即 Inducer 之后的所有），CLI Scheduler 由 Phase 1 entry script 替代（一次性 Python 函数，无 mode 解析、无 chunked batch、无被动提醒）。

---

## §2 文件结构（新建 / 修改）

### 2.1 新建文件

| 路径 | 职责 | LOC 估算 |
|---|---|---|
| `BreakoutStrategy/feature_library/inducer.py` | `batch_induce(sample_ids) -> list[Candidate]` 接口；负责加载 chart/meta/nl，调 GLM4VBackend.batch_describe，解析输出 | ~120 |
| `BreakoutStrategy/feature_library/inducer_prompts.py` | `INDUCER_SYSTEM_PROMPT` + `build_batch_user_message(samples_meta) -> str` | ~80 |
| `BreakoutStrategy/feature_library/embedding_l0.py` | `embed_text(text) -> np.ndarray` + `cosine_similarity(a, b) -> float`（薄封装 news_sentiment.embedding，避免 cross-package 直依赖）| ~40 |
| `BreakoutStrategy/feature_library/feature_store.py` | features/<id>.yaml CRUD：`load(id) / save(feature) / list_all() / next_id() / exists(id)` | ~120 |
| `BreakoutStrategy/feature_library/observation_log.py` | `ObservationLogEntry` dataclass + `append(feature_id, entry) / recompute(feature_id) -> (α, β)`；按 (sample, feature) 粒度 | ~100 |
| `BreakoutStrategy/feature_library/librarian.py` | `upsert_candidate(candidate, batch_sample_ids, source)`、`lookup_by_cosine(text, threshold) -> list[Feature]`、`update(feature_id, event)`、`recompute(feature_id)` | ~180 |
| `BreakoutStrategy/feature_library/feature_models.py` | `Candidate` dataclass / `Feature` dataclass / `Event` dataclass / `StatusBand` enum | ~80 |
| 测试文件（每个新模块对应一个）| - | ~600 总和 |
| `scripts/feature_mining_phase1.py` | entry script | ~100 |

### 2.2 修改文件（仅一处扩展）

| 路径 | 修改 |
|---|---|
| `BreakoutStrategy/feature_library/glm4v_backend.py` | 新增方法 `batch_describe(chart_paths: list[Path], user_message: str) -> str`，单次 API 调用塞多张 image_url（≤5 张，否则 raise ValueError）|

不修改既有 Phase 0 接口（`describe_chart` 保留）。

### 2.3 Runtime 数据结构（feature_library/ 目录）

```
feature_library/                          # 已在 .gitignore（Phase 0）
├── samples/                              # Phase 0 已建
│   └── BO_AAPL_20210617/
│       ├── chart.png
│       ├── meta.yaml
│       └── nl_description.md
├── features/                             # Phase 1 新增
│   ├── F-001-tight-rectangle-breakout.yaml
│   ├── F-002-volume-contraction.yaml
│   └── ...
├── INDEX.md                              # Phase 1 选做（main spec §4.1）
└── history/                              # 暂留，Phase 2 才写
```

`features/<id>.yaml` 命名规则：`F-NNN-<text-slug>.yaml`，NNN 是 3 位 0-padded 序号（F-001, F-002, ...），slug 是 text 的 kebab-case 化前 30 字符。

---

## §3 Inducer 设计

### 3.1 接口契约

```python
# BreakoutStrategy/feature_library/inducer.py

@dataclass
class Candidate:
    text: str                              # 自然语言描述
    supporting_sample_ids: list[str]       # 支持该规律的 sample_ids
    K: int                                 # = len(supporting_sample_ids)
    N: int                                 # batch 总数（= len(batch_sample_ids)）
    raw_response_excerpt: str              # GLM 原始回复片段（前 500 字，便于 debug）


def batch_induce(
    sample_ids: list[str],
    backend: GLM4VBackend,
    *,
    max_batch_size: int = 5,
) -> list[Candidate]:
    """对一组样本做 Inducer batch 归纳。

    Args:
        sample_ids: 样本 ID 列表（必须每个对应 samples/<id>/ 三件套已存在）
        backend: GLM4VBackend 实例
        max_batch_size: 单次 GLM 调用塞图上限（GLM-4V-Flash 服务端硬限 5）

    Returns:
        candidates 列表（可能为空，若 LLM 没找到共性）

    Raises:
        ValueError: sample_ids 数量超过 max_batch_size
        FileNotFoundError: 某个 sample 的 chart.png / meta.yaml 缺失
    """
```

### 3.2 LLM Prompt 协议

**INDUCER_SYSTEM_PROMPT**（中文系统提示）：

```
你是 K 线形态归纳专家。我会给你一批同一个研究主题的 K 线图（每张图含突破日标注），
还有每张图的关键数值上下文。你的任务是找出这批图共有的、有判别意义的形态规律。

输出严格遵守以下 YAML 格式（不含 markdown 代码块）：

candidates:
  - text: "<规律的自然语言描述，30-100 字>"
    supporting_sample_ids: [<支持该规律的 sample_id 列表，至少 2 个>]
  - text: "..."
    supporting_sample_ids: [...]

约束：
- 至少需要 2 张图同时呈现某规律才能列为 candidate（K ≥ 2）
- 如果你认为没有跨图共性，输出 `candidates: []`
- 不要输出 batch 总样本数 N，由调用方推断
- 不要使用 markdown 代码块、列表标题、解释段落
- 单条 candidate 的 text 应可独立理解（不要"如上所述"之类的引用）
```

**build_batch_user_message(samples_meta: list[dict]) -> str**：

```
我给你 N 张 K 线图，按顺序对应以下 sample_ids：

[1] sample_id: BO_AAPL_20210617
    ticker: AAPL
    bo_date: 2021-06-17
    consolidation: length=30 bars / height=5.2% / volume_ratio=0.55 / tightness=1.8
    breakout_day: open=130.0 high=135.0 low=129.0 close=134.0 volume=100M

[2] sample_id: BO_MSFT_...
    ...

请按 SYSTEM_PROMPT 要求归纳这批样本的共性规律。
```

### 3.3 解析 LLM 输出

LLM 输出应是 YAML 文本。解析步骤：
1. `yaml.safe_load(response)` → dict
2. 取 `result.get("candidates", [])` → list[dict]
3. 对每条：
   - 校验有 `text` (str) 和 `supporting_sample_ids` (list)
   - 过滤 supporting_sample_ids 不在 batch 内的（防 LLM 幻觉）
   - K = len(supporting_sample_ids)
   - 若 K < 2 跳过（违反 SYSTEM_PROMPT 约束）
   - N = len(batch_sample_ids)
   - 构造 Candidate

**容错**：若 yaml.safe_load 抛 YAMLError，记 log + 返回空列表（不抛异常，避免单次 LLM 失败阻断整个流程）。

### 3.4 错误处理

| 场景 | 行为 |
|---|---|
| sample_ids 超过 max_batch_size | 立即 raise ValueError |
| 某 sample 三件套缺失 | raise FileNotFoundError，提示 sample_id |
| GLM4VBackend.batch_describe 返回空字符串 | log warning + 返回空 list（GLM 失败不阻塞）|
| LLM 输出非 YAML 或 schema 错 | log warning + 返回空 list + 保留 raw_response 到 log 文件供事后分析 |
| 某 candidate 的 supporting_sample_ids 全部不在 batch 内 | 跳过该 candidate（log warning）|

---

## §4 Librarian 设计

### 4.1 接口契约

```python
# BreakoutStrategy/feature_library/librarian.py

class Librarian:
    """Beta-Binomial 累积器 + L0 merge + features 库管理。"""

    def __init__(self, store: FeatureStore, embedder: EmbeddingL0):
        ...

    def upsert_candidate(
        self,
        candidate: Candidate,
        *,
        batch_sample_ids: list[str],
        source: str = "ai_induction",
    ) -> Feature:
        """处理一个 Inducer candidate：合并到老 feature 或新建。

        步骤：
        1. embed candidate.text → embedding
        2. lookup_by_cosine(embedding, threshold=L0_MERGE_THRESHOLD)
        3a. 若命中（取最高 cosine 的 match）：target = match
            for sample_id in candidate.supporting_sample_ids:
                update(target.id, Event(sample_id=..., K=1, N=1, C=0, source))
            for sample_id in (batch_sample_ids - supporting_sample_ids):
                update(target.id, Event(sample_id=..., K=0, N=1, C=0, source))
        3b. 若未命中：create_new_feature(candidate.text, embedding) → 同上 update
        4. recompute(target.id) 重算 (α, β) + signal
        5. 返回 target Feature
        """

    def lookup_by_cosine(
        self, embedding: np.ndarray, threshold: float = L0_MERGE_THRESHOLD,
    ) -> list[Feature]:
        """L0 筛选：返回 cosine ≥ threshold 的 features，按 cosine 降序"""

    def update(self, feature_id: str, event: Event) -> None:
        """单条 ObservationLog 事件入库（不重算 (α, β)，由 recompute 统一做）"""

    def recompute(self, feature_id: str) -> Feature:
        """从 ObservationLog 重放计算 (α, β)，更新 features yaml + 派生 signal"""
```

### 4.2 关键常量

| 常量 | 值 | 含义 |
|---|---|---|
| `L0_MERGE_THRESHOLD` | 0.85 | candidate 与老 feature L0 cosine ≥ 此值视为同一规律，触发合并 |
| `ALPHA_PRIOR` | 0.5 | Beta(0.5, 0.5) Jeffreys prior（主 spec §3.1）|
| `BETA_PRIOR` | 0.5 | 同上 |
| `LAMBDA_DECAY` | 1.0 | Phase 1 不启用时间衰减（设为 1.0 = 无衰减），Phase 1.5+ 改 0.995 |
| `GAMMA` | 1.0 | Phase 1 无 counter（C=0），γ 不参与计算，置 1 占位；Phase 1.5+ 改 3 |
| `STATUS_BANDS` | dict | 主 spec §3.4 派生：forgotten<0.05 / candidate[0.05,0.20) / supported[0.20,0.40) / consolidated[0.40,0.60) / strong[0.60,1.0] |

### 4.3 Beta-Binomial update 公式（Phase 1 简化版）

```python
# 不含时间衰减（LAMBDA=1.0）+ 不含 counter（C=0）
def recompute(feature_id: str) -> tuple[float, float]:
    obs_entries = ObservationLog.load(feature_id)
    # 跳过 superseded_by 不为 null 的（Phase 1 不会出现，但代码已 future-proof）
    active = [o for o in obs_entries if o.superseded_by is None]
    
    alpha = ALPHA_PRIOR + sum(o.K for o in active)
    beta = BETA_PRIOR + sum(o.N - o.K - o.C for o in active) + GAMMA * sum(o.C for o in active)
    return (alpha, beta)
```

派生 signal：
```python
signal = scipy.stats.beta.ppf(0.05, alpha, beta)  # P5
status_band = derive_band(signal)
```

### 4.4 Edge cases

| 场景 | 行为 |
|---|---|
| candidate 命中多个老 feature（cosine ≥ threshold）| 选 cosine 最高的；若并列取 id 最小的（确定性）|
| ObservationLog 中已有 (sample, feature) 条目（重复入库）| Phase 1 简化：直接 append（按 (sample,feature,source,epoch_tag=null) 视为相同事件→ 仅 append 一次的去重逻辑也可推迟到 Phase 1.5；本期暂允许重复以加速 MVP）|
| recompute 时 obs 为空 | 返回 (ALPHA_PRIOR, BETA_PRIOR) |

---

## §5 ObservationLog 设计

### 5.1 ObservationLogEntry 字段

```python
@dataclass
class ObservationLogEntry:
    id: str                                # 唯一条目 ID（uuid4 短形式）
    ts: datetime                           # 写入时间
    source: str                            # ai_induction / user_pick / deepseek_l1 / replay-* / shuffle-* / reinduction-*
    epoch_tag: str | None = None           # Phase 1 默认 null，Phase 1.5+ 启用
    sample_id: str                         # 单条目级 sample 引用
    K: int                                 # 该 sample 在该事件下贡献的 K (0 或 1)
    N: int                                 # 该 sample 在该事件下贡献的 N (始终 1)
    C: int = 0                             # counter (Phase 1 不用，置 0)
    alpha_after: float                     # update 后快照
    beta_after: float
    signal_after: float                    # P5 update 后
    superseded_by: str | None = None       # Phase 1 不写，Phase 1.5+ 启用
    notes: str = ""                        # batch_id / supporting_sample_ids 索引等
```

### 5.2 ObservationLog 与 features yaml 的关系

ObservationLog 嵌套在 features/<id>.yaml 的 `observations` 数组中（主 spec §4.2）。**不**单独存一个文件。

每次 update 都 append 一条 entry → save features yaml。

### 5.3 IO

```python
# observation_log.py
def append_entry(feature_id: str, entry: ObservationLogEntry) -> None:
    """加载 features yaml → append observations → 保存"""

def get_active_entries(feature_id: str) -> list[ObservationLogEntry]:
    """加载 features yaml → 过滤 superseded_by is None"""
```

---

## §6 features/<id>.yaml schema（按主 spec §4.2 完整字段）

```yaml
id: F-001
text: "盘整期间量能相比盘整前明显收缩"
embedding: [0.123, -0.456, ...]              # fastembed 输出，384 维
alpha: 7.5
beta: 3.5
last_update_ts: 2026-04-27T14:30:00
provenance: ai_induction                     # Phase 1 默认 source；Phase 4+ shuffle-* 锁
observed_samples: [BO_AAPL_20210617, ...]    # set 形式（yaml list 去重）
total_K: 7                                   # 累计支持
total_N: 10                                  # 累计样本
total_C_weighted: 0                          # Phase 1 始终 0
observations:
  - id: obs-a1b2c3
    ts: 2026-04-27T14:30:00
    source: ai_induction
    epoch_tag: null                          # Phase 1 默认 null
    sample_id: BO_AAPL_20210617
    K: 1
    N: 1
    C: 0
    alpha_after: 1.5
    beta_after: 0.5
    signal_after: 0.07
    superseded_by: null                      # Phase 1 不写
    notes: "batch_id=B-001"
  # 单 batch 多样本 → 拆为多条 obs 条目
research_status: active                      # Phase 1 默认 active
factor_overlap_declared: null                # Phase 4+ 启用
```

### 6.1 派生字段（不存）

- `signal = beta.ppf(0.05, α, β)` — P5
- `status_band = derive(signal, provenance)` — forgotten/candidate/.../strong

### 6.2 Schema validation

实施时用 dataclass + yaml.safe_load 反序列化，类型检查靠 dataclass `__post_init__`。

---

## §7 Phase 1 entry script

### 7.1 接口

```python
# scripts/feature_mining_phase1.py

def main() -> None:
    # ---------------- 参数声明区 ----------------
    ticker: str = "AAPL"                        # 目标股票
    sample_count: int = 5                       # 处理几个 breakout（受 max_batch_size 限制）
    skip_preprocess: bool = False               # True 时跳过 Phase 0 preprocess（假定 samples 已存在）
    inducer_max_batch: int = 5                  # GLM-4V-Flash 单次上限
    breakout_detector_params: dict = {}         # 复用 Phase 0 BreakoutDetector 默认值
    # -------------------------------------------
    
    # 1. 加载 / 预处理样本
    sample_ids = ensure_samples(
        ticker=ticker, count=sample_count,
        skip_preprocess=skip_preprocess,
        breakout_detector_params=breakout_detector_params,
    )
    
    # 2. Inducer 多图归纳
    backend = GLM4VBackend(api_key=load_zhipuai_key())
    candidates = inducer.batch_induce(
        sample_ids=sample_ids[:inducer_max_batch],
        backend=backend,
    )
    
    # 3. Librarian 累积
    store = FeatureStore()
    embedder = EmbeddingL0()
    lib = Librarian(store=store, embedder=embedder)
    
    affected_features: list[Feature] = []
    for cand in candidates:
        feature = lib.upsert_candidate(
            candidate=cand,
            batch_sample_ids=sample_ids[:inducer_max_batch],
            source="ai_induction",
        )
        affected_features.append(feature)
    
    # 4. 打印 features 库摘要
    print_library_summary(store=store, recently_affected=affected_features)
```

### 7.2 ensure_samples 行为

- 对 ticker 找 datasets/pkls/<ticker>.pkl
- BreakoutDetector.batch_add_bars(df) → list[BreakoutInfo]（复用 Phase 0 entry script 已确认的接口）
- 取前 sample_count 个 breakout
- 对每个：检查 samples/<id>/ 是否完整；缺失则调 `preprocess_sample`（Phase 0）补齐
- 返回 sample_ids 列表

### 7.3 print_library_summary

```
[Phase 1] features 库当前状态：3 features
  F-001 [supported  ] α=4.5 β=1.5 P5=0.41 obs=5  text="盘整后量能..."
  F-002 [candidate  ] α=2.5 β=2.5 P5=0.13 obs=4  text="突破日大量..."
  F-003 [forgotten  ] α=0.5 β=4.5 P5=0.01 obs=4  text="..."
[Phase 1] 本轮新增 / 强化 features：F-001, F-002（共 2 条）
[Phase 1] 三件套位置：feature_library/features/
```

---

## §8 测试策略

### 8.1 单元测试覆盖

| 模块 | 关键测试场景 |
|---|---|
| `embedding_l0` | embed_text 返回 384 维 / cosine 自反射性 / 完全一致文本 cosine=1.0 |
| `feature_store` | save → load 同字段 / next_id 递增 / list_all 返回所有 |
| `observation_log` | append_entry 后 get_active_entries 含新条目 / 跳过 superseded_by 非 null |
| `inducer_prompts` | SYSTEM_PROMPT 含约束关键词 / build_batch_user_message 含所有 sample 上下文 |
| `inducer.batch_induce` | mock backend.batch_describe 返回有效 YAML → 解析正确 / 返回 invalid YAML → 空 list / supporting_ids 不在 batch → 过滤 / K<2 → 跳过 |
| `librarian.upsert_candidate` | mock embedder + store → 命中合并 / 未命中新建 / observation 按 sample 拆条 |
| `librarian.recompute` | (α, β) 公式正确 / signal 派生正确 / status_band 边界值 |
| `glm4v_backend.batch_describe` | mock zhipuai client → 多 image_url + 1 text 块构造正确 / >5 张抛 ValueError |

预算 30~40 个新测试。叠加 Phase 0 35 个，总计 65~75 PASS。

### 8.2 端到端 smoke test

`scripts/feature_mining_phase1.py` 跑 ticker=AAPL, sample_count=5：
- 5 张样本喂给 GLM-4V-Flash
- 至少产出 1 个 candidate（不强求多）
- features 库写入对应 yaml 文件
- 打印 summary 显示新 features

**通过判据**：
- 进程正常退出（exit 0）
- features/F-*.yaml 至少 1 个
- 每个 yaml 含完整 schema 字段
- ObservationLog 条目数 = candidates 总数 × batch 大小

---

## §9 验收标准

| AC | 判据 | 验证方式 |
|---|---|---|
| **AC1** Phase 1 包结构完整 | 7 个新 Python 模块 + 测试文件 + 1 个修改 | `ls BreakoutStrategy/feature_library/` |
| **AC2** 全套测试 PASS | Phase 0 35 + Phase 1 30~40 = 65~75 | `uv run pytest BreakoutStrategy/feature_library/tests/ -v` |
| **AC3** 端到端 entry script 跑通 | scripts/feature_mining_phase1.py 不报错完成 | 真实运行 |
| **AC4** GLM-4V-Flash 多图调通 | batch_describe 返回非空，含 candidates YAML | 看 entry script 输出 |
| **AC5** features 库非空 | feature_library/features/F-*.yaml 至少 1 个 | `ls feature_library/features/` |
| **AC6** features yaml schema 完整 | 含主 spec §4.2 所有字段（含 epoch_tag/superseded_by/provenance） | yaml.safe_load + dataclass 反序列化无异常 |
| **AC7** ObservationLog 按 sample 粒度 | 每条 obs 含 sample_id；同 batch 多条 | 检查 yaml |
| **AC8** Beta-Binomial 公式正确 | recompute 单元测试覆盖典型 case | pytest |
| **AC9** L0 merge 工作 | 两个相似 candidate text → 合并到同 feature | pytest |
| **AC10** runtime 不进 git | features/ 也在 .gitignore | `git status` |

---

## §10 Phase 1.5 / 2 / 3 衔接预留

### 10.1 Phase 1.5（需求清单）

- 启用 epoch_tag（Phase 1 已 schema 占位）
- 实施 merge-policy 三选项（修改 Librarian.upsert_candidate 加 `merge_policy` 参数）
- 实施 superseded_by 机制（修改 ObservationLog.recompute 跳过逻辑已就位）
- 加 DeepSeek L1 backend（mirror 现有 deepseek_backend.py）
- 加 Path V verify_yes_no 接口（Librarian 已留接口）
- pending_replays.yaml 队列

### 10.2 Phase 2（需求清单）

- `feature-mine` CLI 命令套件（替代 scripts/feature_mining_phase*.py）
- chunked batch（用户输入 30 张 → 拆 6 个 batch_size=5）
- 被动提醒（孤儿样本 / health check / pending replays）
- dev UI P/N 键 hook
- INDEX.md 自动生成

### 10.3 Phase 3（需求清单）

- Critic 角色（subprocess.run("claude -p ...")  调用 Claude Code subagent，避免 Python 入口下 subagent 不可用问题）
- vocabulary 归档 + hold-out + permutation 三条硬防御

---

## §11 实施期决策附录（与主 spec 偏差记录）

### 11.1 Inducer 不是 subagent，是 Python module

主 spec §1.1：`Inducer = Claude Opus 短 subagent`

Phase 1 实施：`Inducer = Python module，调 GLM-4V-Flash API`

理由：
- 框架入口是 Python 脚本，不在 Claude Code session 内
- subagent 是 Claude Code 运行时机制，Python 进程无法 spawn
- subagent 的 4 项收益（隔离 / 短生命周期 / Opus 多模态 / agentic loop）中，前 2 项 Python 函数天然支持，第 3 项靠 backend 选择，第 4 项 Phase 1 不需要

未来路径：
- 用 Anthropic API 替代 GLM 时，仍是 Python module 调 API（主 spec §1.1 的"subagent"概念在 Python 入口下永远不会落地）
- 真要 subagent 语义（如 Critic 在 Phase 3），用 `subprocess.run(["claude", "-p", ...])` 调 Claude Code 子进程实现

### 11.2 GLM-4V-Flash 替代 Opus 的 batch 上限

主 spec 假设 batch_size=8~12（cold-start batch）。

Phase 1 实测 GLM-4V-Flash 服务端硬限 5 张。

未来路径：
- Phase 2 chunked batch 可恢复 ≥6 张（拆 batch_size=5 多次调用 + Librarian L0 dedup 聚合）
- 切换到 Anthropic Opus API 后可恢复 spec 原 batch_size

### 11.3 Phase 1 简化

- 不实施 epoch_tag / superseded_by 实际逻辑（schema 占位但默认 null）
- 不实施时间衰减（LAMBDA=1.0）
- 不实施 counter γ 加权（C=0 始终）
- 不防 ObservationLog 重复 entry（暂允许，Phase 1.5 加去重）

这些简化在 Phase 1.5+ 逐步补齐，Phase 1 schema 已完全 future-proof。

### 11.4 features/<id>.yaml 命名 slug

主 spec §4.1 给的例子是 `F-001-tight-rectangle-basing.yaml`。

Phase 1 命名规则：`F-NNN-<text-slug>.yaml`，slug = text.lower().replace(non-alnum, "-")[:30]。Unicode 字符（中文）保留以 fasttext 转拼音或丢弃？**决策：丢弃中文，仅保留英文 + 数字 + 连字符**（避免文件名兼容性问题）。

如 text 是纯中文 → slug = "" → 文件名退化为 `F-NNN.yaml`。

---

## §12 不变量 / 硬约束

1. **盲跑约束（主 spec §4.3）**：Inducer prompt 不得包含库内现有 features 的文本（Phase 1 entry script 不做查重提示，符合）。
2. **Critic 不动 (α, β)（主 spec §4.5/§4.7）**：Phase 1 没有 Critic，N/A。
3. **Critic 不改 Inducer prompt（主 spec §4.5）**：同上。
4. **CLI 不持 features 内容（主 spec §4.6）**：Phase 1 entry script 只暴露 sample_ids 给 Inducer prompt（不暴露 features 文本），符合。
5. **runtime 数据不进 git**：feature_library/ 在 .gitignore（Phase 0 已加）。

---

**Spec 结束。** 实施请按此 spec 由 writing-plans 生成详细计划。

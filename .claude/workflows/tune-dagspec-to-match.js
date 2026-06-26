export const meta = {
  name: 'tune-dagspec-to-match',
  description: '迭代调参 dag_spec 使指定 (ticker,窗口) 匹配:诊断→调参收敛→健全性/全宇宙影响复核',
  phases: [
    { title: 'Diagnose', detail: '目标票逐 gate 漏斗' },
    { title: 'Tune', detail: '迭代收敛到最小变更集' },
    { title: 'Verify', detail: '健全性 + 全宇宙影响 + 最小性对抗' },
    { title: 'Synthesize', detail: '产出可应用配置' },
  ],
}

const T = args || { ticker: 'NCL', start: '2025-01-01', end: '2025-05-12' }

const CTX = `
# 任务:迭代调参 dag_spec 让目标票匹配
项目 /home/yu/PycharmProjects/Trade_Strategy（uv 管理，\`uv run python <脚本>\`，cd 到该目录或绝对路径）。
目标票：ticker=${T.ticker}，窗口 [${T.start}, ${T.end}]（slice_window 双端含端点）。
要求：调 dag_spec（= Params 参数 + build_pattern 的 edges）使该票 analyze 命中 ≥1。

# pattern 结构（path2_apps/bottom_breakout_burst/dag_spec.py）
链 down→side→burst→tb。节点 bo(孤立流源)/down(trend regime==down ∧ drawdown≥pred4_min_drawdown)/
side(trend regime==sideways)/burst(BurstDetector consumes bo，复合宽事件，where first_drought≥THR_DROUGHT ∧
distinct_pk≥THR_PK ∧ max_vol_ratio≥THR_VOL，count≥MIN_BOS)/tb(ThrowbackDetector consumes bo)。
边：TemporalEdge(down→side,[1,pred4_lookback_bars]) / ContainmentEdge(side, Child(burst,"first_bo")) /
TemporalEdge(burst→tb,[1,1])。
Params.default(): MIN_BOS=3 pred4_min_drawdown=0.5 THR_DROUGHT=40 THR_PK=3 THR_VOL=3.0
burst_max_span=20 pred4_lookback_bars=120 trend_hysteresis_bars=3 trend_ma_period=20 trend_sideways_eps=0.0005
bo_min_relative_height=0.05 throwback_N=10。（dd=0.5 是用户有意值，committed 基线 0.25）

# 主会话已内联确诊的 ${T.ticker} 现状（默认参数）
trend 分段：sideways[0,21] down[22,69](dd=0.359) up[70,88]。bo at [53,74,75,76,77,88]。
burst[74,88] count=5 first_drought=21 distinct_pk=6 max_vol=18.28 members=[74,75,76,77,88] first_bo=74。
根因（3 重）：
 (1) 用户视觉"横盘"(低位整理)被并进 down[22,69]，突破后无独立 sideways 段；first_bo=74 落在 up 段。
     → 提高 trend_sideways_eps 0.0005→0.002 后分段变 sideways[0,21] down[22,59](dd=0.34) side[60,75] up[76,88]，
       first_bo[74] 落进 side[60,75]✓，down→side gap=60-59=1✓。
 (2) down dd=0.34<0.5（需 pred4_min_drawdown≤0.34，如 0.25）；first_drought=21<40（需 THR_DROUGHT≤21，如 20）。
 (3) 回踩：末 bo[88] 在窗末+弱、无 confirmed tb；带回踩的是 first_bo[74](confirmed tb@76)。
     当前 burst→tb gap[1,1] 锚 burst.end(=last_bo)→断。改 TemporalEdge(Child(burst,"first_bo"),"tb",[1,K]) 锚 first_bo→通。

# 主会话已内联验证的候选配置（你需独立复核 + 最小化 + 健全性 + 全宇宙影响）
trend_sideways_eps=0.002, pred4_min_drawdown=0.25, THR_DROUGHT=20, 回踩边锚 first_bo(max_gap=30)：
  ${T.ticker} matches=1 (down=trend0_22_59 side=trend1_60_75 burst=burst_74_88 tb=tb_75_76)；ACRS=0；CAAS=2。

# build_spec 助手（你的 probe 脚本里直接用这段构造候选 spec）
\`\`\`python
import sys; sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy')
from dataclasses import replace
import pandas as pd
from path2_apps.bottom_breakout_burst.params import Params
from path2_apps.bottom_breakout_burst.dag_spec import build_pattern
from path2_web.data import slice_window
from path2.dag.spec import PatternSpec
from path2.dag.edges import TemporalEdge, ContainmentEdge, Child
from path2.dag.engine import analyze as engine_analyze

def build_spec(p, tb_anchor="first_bo", tb_max_gap=30, downside_max_gap=None):
    base = build_pattern(p)
    dmax = downside_max_gap if downside_max_gap is not None else p.pred4_lookback_bars
    tb_edge = (TemporalEdge(Child("burst","first_bo"),"tb",min_gap=1,max_gap=tb_max_gap)
               if tb_anchor=="first_bo" else TemporalEdge("burst","tb",min_gap=1,max_gap=1))
    edges = (TemporalEdge("down","side",min_gap=1,max_gap=dmax),
             ContainmentEdge("side", Child("burst","first_bo")), tb_edge)
    return PatternSpec(pattern_id=base.pattern_id, display_name=base.display_name,
                       nodes=base.nodes, edges=edges, root=base.root)

def match_count(ticker, start, end, p, **kw):
    win = slice_window(pd.read_pickle(f'/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/{ticker}.pkl'), start, end)
    return len(engine_analyze(build_spec(p, **kw), win, p).matches)
# 例：p=replace(Params.default(), trend_sideways_eps=0.002, pred4_min_drawdown=0.25, THR_DROUGHT=20)
#     match_count("${T.ticker}", "${T.start}", "${T.end}", p, tb_anchor="first_bo", tb_max_gap=30)
\`\`\`

# 纪律
- 临时脚本写在项目根、文件名带唯一标签、跑完 \`rm\`。全宇宙跑用 ProcessPoolExecutor(max_workers=6)。
- ★绝不改任何 repo 源文件、绝不动 git（不 commit/add/reset/checkout/stash）。本 workflow 只产出"应主会话应用的配置"，由主会话应用。
- 结论用数字说话；区分必要 knob 与冗余 knob。
`

phase('Diagnose')
const DIAG = {
  type: 'object', additionalProperties: false,
  properties: {
    funnel: { type: 'string', description: '逐 gate 通过/失败表（含实测值）' },
    blockers: { type: 'array', items: { type: 'string' } },
    confirmed: { type: 'boolean', description: '是否复核确认默认参数下目标票确不匹配' },
  }, required: ['funnel', 'blockers', 'confirmed'],
}
const diag = await agent(`${CTX}

## 子任务 [diagnose]
独立复核：在【默认 Params】下把目标票 ${T.ticker} 走当前 dag_spec，写 probe 逐 gate 输出实测值（down 段 regime/dd、有无 down 后的 sideways 段、first_bo 落点段、down→side gap、burst count/first_drought/distinct_pk/max_vol、末 bo 有无 confirmed tb），列出全部 blocker。确认默认下确不匹配。`,
  { label: 'diagnose', phase: 'Diagnose', agentType: 'general-purpose', schema: DIAG })

phase('Tune')
const TUNE = {
  type: 'object', additionalProperties: false,
  properties: {
    config: { type: 'string', description: '收敛到的最小配置（param 覆盖 + 边改动，精确值）' },
    param_overrides: { type: 'object', additionalProperties: true },
    tb_anchor: { type: 'string' },
    tb_max_gap: { type: 'number' },
    downside_max_gap: { type: 'number', description: '建议的 down→side max_gap（用户嫌 120 过松，取能保目标命中的较小值）' },
    target_matches: { type: 'boolean' },
    iteration_trace: { type: 'array', items: { type: 'string' }, description: '每步改了什么 knob、为何、改后目标是否命中' },
    ablation: { type: 'array', items: { type: 'string' }, description: '逐 knob 消融：去掉它目标是否仍命中（判必要性）' },
  }, required: ['config', 'param_overrides', 'tb_anchor', 'target_matches', 'iteration_trace', 'ablation'],
}
const tune = await agent(`${CTX}

## 诊断结果\n${diag.funnel}\nblockers: ${(diag.blockers||[]).join(' | ')}\n
## 子任务 [tune]
迭代收敛到让 ${T.ticker} 命中的【最小变更集】。写 probe：从默认参数出发，逐个清除 top blocker（每步用 build_spec/match_count 在内存测目标），记录 iteration_trace。收敛后做【消融】：逐一撤掉每个 knob（eps/dd/DROUGHT/回踩锚点/tb_max_gap），看目标是否仍命中——剔除冗余 knob，得最小必要集。
另外按用户诉求给出 down→side 的 max_gap 建议：用户嫌默认 120 过松（${T.ticker} 实际 down→side 紧邻 gap=1）；在保目标命中前提下给一个更紧的值（如能保命中的较小 max_gap），并说明权衡。
返回最小配置（精确 param 值 + 回踩边写法 + downside_max_gap）。`,
  { label: 'tune', phase: 'Tune', agentType: 'general-purpose', schema: TUNE })

phase('Verify')
const VER = {
  type: 'object', additionalProperties: false,
  properties: {
    aspect: { type: 'string' },
    pass: { type: 'boolean' },
    findings: { type: 'array', items: { type: 'string' } },
    numbers: { type: 'string' },
  }, required: ['aspect', 'pass', 'findings'],
}
const cfgStr = `param_overrides=${JSON.stringify(tune.param_overrides)} tb_anchor=${tune.tb_anchor} tb_max_gap=${tune.tb_max_gap} downside_max_gap=${tune.downside_max_gap}`
const ver = await parallel([
  () => agent(`${CTX}

## 待验证的收敛配置\n${tune.config}\n(${cfgStr})\n
## 子任务 [verify-impact] —— 全宇宙影响 + 边健全性
1. 把收敛配置在内存应用（build_spec + 该 param 覆盖），对【2024 窗口全宇宙 6048 票】(START=2024-01-01 END=2025-01-01，与生产扫描脚本一致) 跑 match 计数（ProcessPoolExecutor max_workers=6）。报：命中股数、是否数量级合理（不是 0、也不是爆炸到几千）、与默认 dd=0.25 旧拓扑相比的变化。同时确认目标票 ${T.ticker} 在其自身窗口仍命中。
2. 新边 TemporalEdge(Child(burst,"first_bo"),"tb",...) 含 src_selector，是较少走的路径：在一个 30~60 票小样本上做【暴力枚举 vs 引擎】对照（绕开剪枝，对 down×side×burst×tb 四元组逐边 satisfies 穷举完整链，与 engine_analyze 命中数逐票比对），确认引擎对 src_selector 出边的 C1 剪枝【不漏匹配、不产假阳】。报 divergences 数。`,
    { label: 'verify-impact', phase: 'Verify', agentType: 'general-purpose', schema: VER }),

  () => agent(`${CTX}

## 待验证的收敛配置\n${tune.config}\n(${cfgStr})\n消融:\n- ${(tune.ablation||[]).join('\n- ')}\n
## 子任务 [verify-minimality] —— 对抗式最小性 + 副作用
对抗复核 tune 的"最小必要集"主张：
- 每个 knob 真的必要吗？尤其 trend_sideways_eps=0.002 是全局改动，影响所有票分段——它是不是唯一让 sideways 段出现的途径？有没有更局部、副作用更小的替代（如只调 hysteresis、或换 edge 表达让 first_bo 可落 down→up 边界而不强求 sideways 段）？实测对比。
- 回踩锚 first_bo（src_selector 边）是否引入语义/健全性隐患？相比"锚任意 member bo"哪个更稳？
- 找出该配置任何明显副作用（如把某些明显不该命中的走势也放进来）。
独立写 probe 实测，给数字。pass=true 表示 tune 的最小集站得住，false 表示你找到更小/更优集或真隐患（在 findings 里给替代）。`,
    { label: 'verify-minimality', phase: 'Verify', agentType: 'general-purpose', schema: VER }),
])

phase('Synthesize')
const REPORT = {
  type: 'object', additionalProperties: false,
  properties: {
    apply_instructions: { type: 'string', description: '主会话应用步骤：params.py 改哪几个字段成什么值、dag_spec.py 的 burst→tb 边改成什么、down→side max_gap 改成什么' },
    target_matches: { type: 'boolean' },
    universe_count: { type: 'string' },
    soundness: { type: 'string' },
    caveats: { type: 'array', items: { type: 'string' } },
    report_markdown: { type: 'string' },
  }, required: ['apply_instructions', 'target_matches', 'report_markdown'],
}
const verDigest = ver.filter(Boolean).map(v => `### ${v.aspect} (pass=${v.pass})\n${(v.findings||[]).join('\n')}\nnumbers: ${v.numbers||''}`).join('\n\n')
const report = await agent(`${CTX}

## 诊断\n${diag.funnel}\n## 收敛配置\n${tune.config}\niteration:\n- ${(tune.iteration_trace||[]).join('\n- ')}\n消融:\n- ${(tune.ablation||[]).join('\n- ')}\n## 验证\n${verDigest}\n
## 子任务 [synthesize]
产出**可直接应用的配置 + 报告**（中文）。给出 apply_instructions：params.py 改哪几个字段（精确值）、dag_spec.py 的 burst→tb 边精确改成什么、down→side max_gap 改成什么。报告含：${T.ticker} 是否命中、全宇宙影响（命中数量级）、新边健全性结论、各 knob 必要性、对抗复核中任何未消解的隐患/替代方案。若 verify 发现更优/更小配置或健全性隐患，据此修正最终建议。`,
  { label: 'synthesize', phase: 'Synthesize', agentType: 'general-purpose', schema: REPORT })

return { diag, tune, verify: ver, report }

# 事件标识重设计:instance_id 取代 event_id

> 2026-08-13 讨论结论。**状态:设计方向定稿,未实施**——当前代码仍是 event_id 时代(marker 实例绑定实施在「身份键 + NodeRef 双轨」形态上,2026-08-13 完成,8 commits)。本文记录的是「若重新设计、不背历史包袱」的收敛结论。

## 背景

marker 实例绑定实施完成后,对「身份 vs 实例」的分层做了一轮第一性反思。现状的标识体系:

- `event_id`(身份键)= class + span 的混合体(如 `tb_v1_293`、`burst_282_289`)
- `instance_key`(组内流序)= 同身份组内按物化流序从 0 编号(如 `#0`/`#1`)
- 引用协议双轨:身份级引用(children、child_refs、anchor)走 event_id,实例级引用(match 的 node_index)走 `{event_id, idx}` 对象
- 前端交互键 `event_key` = `event_id + '#' + idx`(拼接复合键)

核心追问:event_id 这个中间层(既不是 node、又不是 class、也不是实例)是不是历史包袱,能否彻底消灭。

## 论证链(每轮收敛的关键点)

1. **「instance_key 合并进 event_id 作后缀」不可行**:event_id 是身份级引用和跨物化对齐的键,合并会污染身份语义;且 idx 是流内序,不稳定。但「合并作为交互键」已经做了(event_key)。
2. **「event_id#idx 完全取代 event_id」分场景成立**:物化后的引用可以全面实例化(引用对象列表是已知事实);声明层(spec 的边/where/anchor)引用 class 级,先于物化存在,与 event_id 无关。
3. **用户裁决一:无跨窗口应用场景,也不打算做** → 「跨窗口稳定锚点」这条支持 event_id 的论证撤回。
4. **「身份聚合」盘点后可以完全不要**:
   - 侧栏 trace 行:显示实例列表反而更精确,不需要聚合成一个身份行
   - matchedIds 的身份展开:是身份级引用的反推补丁,引用实例化后整个消失
   - marker/点击/tooltip/焦点:marker 实例绑定实施后已全部实例级
   - 拓扑 panel、band 分层:按 node(class)组织,是类型不是身份
   - 结论:身份是「唯一性需求出现前」(实例流之前)的历史设计,唯一性被多实例打破后只剩惯性
5. **用户纠正:三层而非两层**——node / class / instance,前两者多对多、不能互相替代:
   - 单 node 对多 class 是**单选**关系:一个 node 绑定一个 detector,一次物化内只产出一种 class
   - 单 class 对多 node:一个 class 可担任多个 node(down/side 共用 TrendSegmentDetector 是真实案例)
   - dag 内 node_id 唯一
6. **键成分定稿:(node_id, span, 流序) 足够**——node 单选 class,node 维度蕴含 class 维度;键用 node 而非 class,还**顺带根除 event_id 重复 bug 的成因**(当年 down/side 共用 class、同 span 各产一事件,class+span 全同撞号,靠 source_tag 打补丁;换 node 维度后天然不撞)。
7. **诊断参数澄清**:现状诊断热加载最新 yaml(api.py `build_pattern(load_params())`),与 scan 产物可能有意不同步——这是特性不是缺陷(诊断参考系 = 当前参数,漏检排查/右键调试要的就是「当前参数下为什么断」)。「扫描参数快照」方案对用户场景答非所问,撤回。
8. **source_tag 三职责盘点后随 event_id 一起退场**:
   - 现状三职责:① event_id 前缀消歧(`assign_auto_source_tags` 给同 class 多 detector 填 trend0/trend1,trend.py 用 source_tag 当类名前缀构造 event_id——「使 event_id 前缀不撞」的真实机制)② band 分层渲染键(`deriveTagMap`/`bandKeyOf`,前端分轨体系的根基)③ node↔事件归属反查(serialize 按 event_id 最长前缀反推 + `_assert_injective_source_tags` 单射校验 + 侧栏按 tag 过滤)
   - 去向:① 根除(病因 = 键用 class 维度,换 node 维度后天然不撞)② 职责保留、键换成 node_id(deriveTagMap 改按 node 分组)③ instance_id 前缀直取
   - 结论:source_tag 是「键用 class 维度」时代的第三个补丁,与 instance_key、身份展开一起退场
9. **class_id 字符串一并消灭(用户裁决,2026-08-13 确认)**:class 有两副面孔——Python 类(语言层事实:事件构造、C3 isinstance 核对、event_cls,不可消灭)与 class_id 字符串(契约层镜像:注册表、序列化字段、按类聚合,可消灭)。逐职责裁决:注册表/冲突检测删(调试用 `__name__`);事件行 class 字段删(渲染形态由 span/is_point 推出);样式改按 node 配;统计改按 node;错误消息用 `__name__`。语义代价两条:「同 class 多 node 结构同型」失去显式表达(样式共享变 app 层显式各配一份)、调试信息从全局唯一注册名降为 `__name__`(实际可忽略)。层次最终收敛:node/instance 两层 + Python 类型系统(语言层,无字符串镜像)。

## 最终设计定稿

- **instance_id = (node_id, span, 流序) 的编码**,作为物化实例的全局唯一索引键:
  - node_id:声明层锚,dag 内唯一
  - span:物化坐标(start_idx;区间事件可含 end_idx)
  - 流序:组内物化顺序号,组 = (node_id, span) 桶,从 0 起;无重叠(同桶单实例)时可省略
- **class_id 字符串消灭**(用户确认):类型以 Python 类表达(event_cls / isinstance / `__name__` / is_point),不进契约——注册表、序列化 class 字段、按类聚合全部删除;样式/统计改按 node;「同 class 多 node」的结构同型由 app 配置层显式表达(样式各配一份)
- **event_id 消灭**,随之消灭:身份展开、身份并集、身份聚合、`#` 拼接与解析、NodeRef 对象,以及 source_tag 补丁一族——`assign_auto_source_tags` 自动派生、serialize 的 event_id 最长前缀反推与 tag 单射校验、trend.py 的 source_tag 参数、前端 deriveTagMap 的 tag 体系
- **band 分层渲染保留,键从 source_tag 换成 node_id**:deriveTagMap 改按 node 分组,bandKeyOf 取 instance_id 首部;分层渲染语义不变,只是分组键换掉
- **引用协议**:物化后的引用(children、child_refs、anchor、match 的 node_index)一律走 instance_id 字符串,引用就是事实,零反推
- **声明层走 node**,与 instance_id 的首部天然衔接(声明说「tb node」,物化键以 tb 开头)
- **真共享语义**不变:同 instance_id 被 ≥2 个 match 引用 → pendingDisambig,反而更直白

## 决策前提(用户裁决,记录在案)

- 不做跨窗口应用场景——instance_id 的稳定性只承诺单次物化内
- 诊断用最新参数文件(参考系 = 当前参数;与 scan 有意不同步是特性)
- 单 node 单选 class、dag 内 node_id 唯一(键成分论证的根基)

## 边界与遗留

- idx 无实体含义(纯物化序);单次物化内的稳定性依赖同参数同数据下物化确定性
- 单 node 多流(一个 node 消费多个不同上游流):真实 app 中单 node 单流;若将来出现,组定义需扩展,届时再议
- 多 node 共享 detector 对象(单流多 node,当前休眠):事件对象的归属 node 有歧义,band 粒度与 instance_id 的归属维度需回到「物化流标识」粒度——与「单 node 多流」对称的边界,届时再议
- 诊断链路 UI 联动(侧栏 attr 行 ↔ K 线 marker):参数未变时自然一致,参数变了时 miss 可接受
- 数据文件漂移(pkl 被更新)属数据集管理假设,不在本设计范围
- 显示层需要「身份」描述(如「293 这根 bar 上的 tb 事件」)时,按 (class_id, span) 现算分组——一次性派生视图,不进协议

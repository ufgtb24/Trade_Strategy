# Glossary Map

本仓库有两个上下文：事件表达框架本身，和它的调试可视化工具。两者说的不是一门语言，所以分开。

## Contexts

- [path2](./path2/GLOSSARY.md)：事件表达框架与走势词汇——把股票走势建模成多级不可变事件，再用 DAG 约束求解出命中。覆盖 `path2/` 与 `path2_apps/`。
- [path2_web](./path2_web/GLOSSARY.md)：调试可视化工具的词汇——事件在图上怎么摆、显示到哪一档、参数怎么试。覆盖 `path2_web/`（FastAPI 后端）与 `path2_web_ui/`（Vue3 前端）。

## Relationships

- **path2 → path2_web**：path2_web 是 path2 的纯投影层，它渲染的对象就是 path2 里的 event / node / match。读 web 词条时如果碰到核心词，以 `path2/GLOSSARY.md` 那份为准。
- **path2_web 不含走势语义**：界面不知道 bo 和 burst 各是什么，只按 node 分轨、按 where 分列。

## 命名规则

给新东西起名、写词条、写界面固定文字和数据字段时照此执行。

1. **英文名为规范名**，中文作别名跟在词头后面。词性分工固定：名词指东西（pattern、sample、hit、event），动词指动作（annotate、map、recognize、match），过去分词 / 形容词指状态和修饰（annotated、mapped、matched、qualified、positive）。
2. **一个名字只占一格，一格只用一个名字。** 格由维度交叉而成，主表是「谁的、定义还是实物 × 概念层级」：

   | | pattern | feature |
   |---|---|---|
   | 概念（不加修饰） | pattern | feature |
   | 用户的实物（annotate） | sample = annotated pattern | box = annotated feature |
   | app 的定义（map） | dag = mapped pattern | node / where = mapped feature |
   | app 的实物（recognize） | hit = recognized pattern | event = recognized feature |

3. **组合名 = 修饰词 + 概念。** 阶段修饰词取那一行动作的过去分词；其余修饰词只能取这一格允许的状态词（在该格词条里列出，如 sample 允许 positive / negative、matched / unmatched，event 允许 detected / qualified）。个数不限，顺序固定：越是东西自身、越早定下的属性越靠近名词，即「比较结果 + 判断 + 阶段 + 概念」，如 unmatched positive annotated pattern。短词算作已展开的组合：positive sample = positive annotated pattern。
4. **短词**：要进界面固定文字、数据字段，或在讨论中反复使用的组合，起短词；短词和组合名并存（node / where 与 mapped feature 指同一格）。讨论中遇到还没命名的格子，可直接用组合名，用到第二次就起短词、进词表。
5. **词条定义**：第一行写组合名，再写一句英文定语从句，写明动作的主体和条件（如 unmatched sample = unmatched annotated pattern; a sample that no hit matches）；之后用中文补充条件、容差和容易误读的地方。

## 不在本 map 内

`BreakoutStrategy/` 是 path2 的前身突破选股流水线、日常不动，它的词汇（factor / trial / 模板组合）不属于以上任何上下文；代码地图见 `.claude/breakout_strategy_map.md`。

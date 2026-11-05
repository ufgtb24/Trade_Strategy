# 票 01 独立审查：需求（Spec）

审查对象：`impl/01-framework-python-api`，`git diff 1359914...690f1d7`；对照票 01、拆分总览（改名对照、允许保留的用法、各票共用的执行边界）与 spec。由 code-review skill 派出的子代理完成，看不到执行过程。原文如下。

**票 01 规格审查结论：没有阻断问题。**

**(a) 缺失或只做了一部分**

1. **测试基线的记录还没有。** 验收要求「测试全套…的失败清单与基线相同」，执行边界第 4 条要求「具体命令写进完成记录」。现在 `evidence/01` 里没有测试记录，票上的完成记录也还没写。
   - 我跑了 Python 全套（tests/path2、tests/path2_apps、tests/path2_web、tests/scripts），失败 6 条，在基线 1359914 上同样失败：`test_throwback_v4` 4 条、`test_self_contained`（`path2/GLOSSARY.md` 含 BreakoutStrategy）、`test_serialize_tbseg`。其中前 5 条不在拆分总览列出的已知基线失败里，要补进基线清单。
   - tune-gates、tune-gates-v3、feature-study、diagnose-event 的 skill 测试全部通过。前端测试我没跑；本票没动前端，也没改 JSON 键。
2. `.scratch/annotation-path2/scripts/01-dump-proto-data.py:49` 还留着 `res.matches`，字面上不满足「全仓 Python 里不再出现 `.matches` 属性访问」。总览允许「拿不准…在完成记录里单列，不硬改」，所以可以留，但完成记录里必须单列。

**(b) 超出范围的改动：没有。** 调用方区域里改的注释只换了已删除的标识符（`res.matches`、`PatternMatch`、`match_forward_*`），旁边的 match 说明文字原样留着。这是满足「全仓 Python 里不再出现 `PatternMatch`、`match_forward_returns`…」的必要动作，残留检查不区分注释。`test_eval_runner` 里那条指向改名测试文件的引用改到新文件，属于第 9 条「改掉所有指向它的链接和引用」。

**(c) 做了但值得留意**

1. **中文「匹配」有约 8 处改成了「求解」而不是「命中」**，分布在 `path2/dag/__init__.py`、`_solve.py`、`nodes.py`、`result.py`、`stdlib/app.py` 和各 app 的 docstring。第 12 条原文是「指 app 产出的『匹配』一并改成『命中』」。这几处说的是引擎的求解过程，「求解」本身是词表里的词（`path2/GLOSSARY.md:92`），我认为合理。但它偏离了原文，应按「改了在完成记录里写旧名、新名和理由」记下来。
2. **有一处运行时文案变了。** `path2/dag/result.py:131` 的 `NodeDiagnostics.note` 从「完整匹配」改成「完整命中」，会通过 `path2_web/diagnose.py:58` 进入诊断接口的 HTTP 返回。键没变，前端也不显示这段话，不坏测试。`path2_web_ui/tests/fixtures.ts:96` 里还是旧文案，留给 03 同步。
3. **残留检查与行为对照都成立。**
   - 我直接 grep 本票区域，剩下 46 行，逐行看都是泛指用法，脚本的分类没有错放。几个宽的放行规则（`\w+_matched\w*`、`unmatched`）在 02～05 的区域里目前也不会掩盖旧义。
   - `serialize` 仍写 `"matches"`、`"match_id"`，符合「`serialize` 照旧写」。
   - before.json 与 after.json 逐字节相同：4 个现役 app 各 3 只股票，经 `read_bars` 读训练段副本。`try_conplex_where` 改名前后报同一个错，本来就跑不起来。
4. **验收里的 `tests/path2*` 有歧义。** 字面上会把 tests/path2_web 也包进来，执行者按总览把它归给 02，我认为解读正确。

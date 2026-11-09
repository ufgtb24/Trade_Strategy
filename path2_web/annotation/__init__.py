"""标注:用户在主视图 annotate 模式里画的框、放的样本、起的词,以及读写它们的纯 Python 代码。

- store:标注存储。每次保存只新增一个批次文件,读的时候把全部机器的全部批次文件按固定顺序重放出当前状态;
  保存时校验因果(成员框不晚于样本日),读的时候报出两台机器的冲突与数据指纹不符。
  会话读标注、后端路由读写标注都只经它,它不依赖 FastAPI。
- membership:框套框归属、成员框推断、骨架、dup、成员链空槽的参照实现(纯计算)。任何另写的实现都要逐例通过
  同一组带答案的例子 tests/path2_web/fixtures/membership_examples.json;GAP、NEAR 的默认值只在这里设定。
- match:sample 与 hit 比较(match)的容差,只在这里设定;界面经 GET /annotations 读同一对值。
- changes:一个 pattern 的样本、成员框、定义在两份重放状态之间改了什么(会话求差与 GET /annotations/changes 共用)。
- revision:会话侧每轮的定格(start_round)与改版报告(revision_report),会话用 uv run python -c 调;
  一轮的顺序与禁忌写在它的模块说明里。
"""

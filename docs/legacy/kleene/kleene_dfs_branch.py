"""Archived: _any_dfs 内的 Kleene 分支(2026-06 归档,供算法参考)。

来源:原 path2/dag/_solve.py 的 _any_dfs 内 if node.kleene is not None: 分支。
依赖 kleene_bind / _kleene_indeg_ok / negation_clear / _any_dfs(递归)等。
归档代码不可独立运行。
"""
from path2.core import Event   # 仅允许的 import


def _kleene_dfs_branch(wp, k, assign, chosen_idx, streams, memo, out, c1_off, ctx,
                       lst, ps, v, sig, collapse, memo_mode):
    """提取自原 _any_dfs:Kleene 整段绑定 + 对称 emit。"""
    # ════ Kleene 区间绑定(对称 _lef_dfs;emit 后继续回溯)════
    any_completion = False
    for seq, last_i in kleene_bind(node, lst, lo, hi, ctx, assign):
        if not _kleene_indeg_ok(ps, assign, seq):
            continue
        assign[v] = seq; chosen_idx[v] = last_i
        if wp.neg.get(v) and not negation_clear(wp.neg[v], v, assign, streams):
            del assign[v]; del chosen_idx[v]
            continue
        sub = _any_dfs(wp, k + 1, assign, chosen_idx, streams, memo, out, c1_off, ctx,
                       collapse=collapse, memo_mode=memo_mode)
        any_completion = any_completion or sub
        del assign[v]; del chosen_idx[v]
    if memo_mode == "naive":
        memo[v].add(sig)
    elif memo_mode == "charitable":
        if not any_completion:
            memo[v].add(sig)
    return any_completion

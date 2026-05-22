from __future__ import annotations

from typing import Callable

from path2.core import Event


class Pattern:
    """Pattern 组合子的命名空间。Path 2 目前唯一组合子是 all(AND)。"""

    @staticmethod
    def all(
        *predicates: Callable[[Event], bool]
    ) -> Callable[[Event], bool]:
        """返回组合 predicate:候选需满足全部 predicates(AND,短路)。"""

        def combined(event: Event) -> bool:
            return all(p(event) for p in predicates)

        return combined

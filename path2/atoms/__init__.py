"""path2.atoms: 走势-无关的 L1 Detector 库。

每个 atom 一个文件,产 frozen Event,可被任意走势的 path2_apps 消费。

## 设计约定

- **走势-无关**:命名不绑定特定形态;若需带形状偏见(RoundedBottom 等),放 path2_apps/。
- **状态**:Detector 内部状态用 `self._*` 占位 + `detect()` 入口重置
  (per spec §1.2.4:状态不跨 detect 调用)。
- **frozen Event**:所有 Event 子类必须 `@dataclass(frozen=True)`;
  容器字段(broken_peak_ids / children 等)用 tuple 而非 list,避免 in-place mutate 突破 frozen 语义。

## BarwiseDetector 扩展模式(L1 常见)

`path2.atoms.breakout.BODetector` / `path2.atoms.distribution.DistributionDetector`
都遵循:子类重写 `detect(df)` 先预计算公共序列(vol_ratio_series 等),
再 `yield from super().detect(df)` 走 BarwiseDetector 主循环调 emit。

## L2+ Detector

L2+ 吃多源(stream + df)的 Detector(如 ThrowbackDetector)**不继承**
BarwiseDetector(它绑定单 df 主循环);直接实现 `detect(*sources)` 即可,
由 `path2.run(detector, *source)` 的变参驱动。
"""

# throwback 可买入区间事件(2026-06 重构)
from path2.atoms.throwback import (
    ThrowbackResult,
    evaluate_throwback,
    ThrowbackDetector,
    ThrowbackEvent,
)
from path2.atoms.breakout import BOEvent, BurstEvent, BurstDetector

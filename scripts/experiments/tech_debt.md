# _summarize 聚合公式技术债

> 记录于 2026-03-26，校准 Step 4 完成后
> 更新于 2026-03-27，采用解耦架构后

---

## 债务 1：完美冲突偏向 negative（严重程度：低）

**问题**：ID 22（5P+5N all medium）被 `_LA=1.26` 推向 negative（rho 越过 DELTA=0.07），但 baseline 标注为 neutral。

**当前行为**：公式输出 sentiment=negative，score 较小。在选股阈值中落入 neutral 区间（[-0.15, +0.30]），实际交易决策不受影响。

**影响**：方向标签在统计上贡献 1 个不匹配，但对选股逻辑无害。

**修复方向**：
- 方案 A：增大 `_DELTA`（但会让真正偏 negative 的弱信号也进入 neutral 死区）
- 方案 B：引入"对称冲突检测"——当 |w_p - w_n| / (w_p + w_n) < 阈值时强制 neutral（增加复杂度）
- 方案 C：不修复（选股层无害，方向标签的 1 个不匹配可接受）

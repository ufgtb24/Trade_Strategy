# Final Position by Skeptic

**立场翻转**：R2 主张"简化 C 砍 K 线门" 基于 3-OR / 5-OR 全池实证，稀释后 K 线门确无 gating。fusion C' 提出**稀缺池**（lower_shadow + doji），补测证明有真 gating 力，改采 fusion C'（微调 W_K=2）。

## 1. 测得数字（5 股 AAPL/ABBV/AAL/ACRS/MBI，n=3840 aggregate）

在几何门通过的 bar 子集上：

| 判据 | 全期 | 止跌邻域 |
|---|---|---|
| P(geo pass) | 30.2% | 16.8% |
| P(lower_shadow \| geo) W_K=1 | 14.9% | 13.2% |
| P(doji \| geo) W_K=1 | 13.4% | 12.9% |
| **P(sparse2 \| geo) W_K=1** | **21.4%** | **21.4%** |
| **P(sparse2 \| geo) W_K=2**（当根或前一根）| **37.1%** | **37.3%** |
| P(sparse2 \| geo) W_K=3 | 52.1% | 51.5% |
| P(sparse4 \| geo) W_K=1（+hammer/marubozu）| 36.0% | 32.5% |
| P(sparse4 \| geo) W_K=3 | 78.1% | 76.3% |

其中 `sparse2 = lower_shadow ∨ doji`；`sparse4 = sparse2 ∨ hammer ∨ marubozu`。

## 2. 裁决

按 lead 决策规则：
- **sparse2 W_K=1 = 21.4% < 50%** → K 线稀缺必要门有 gating（几何门通过后仅 21% 也过 K 线，5× 收紧）
- **sparse4 W_K=3 = 78.1% 接近 80%** → 池扩到 4 元或窗宽到 3 后，gating 显著弱化，得不偿失
- **sparse2 W_K=2 = 37.1%** → 与现行"i∨i-1"时序设计一致的中等 gating

**采 fusion C'，微调 W_K=2**（不 W_K=1 是给"止跌信号常出在前一根"留缓冲；不 W_K=3 是防 gating 稀释）。

## 3. 最终推荐判据

```
FLOOR(i, M_floor=2)     ⟺ low[i]   ≥ min(low over [i-M_floor+1, i-1])
                            ∧ low[i-1] ≥ min(low over [i-M_floor,   i-2])
SPARSE_KLINE(i, W_K=2)  ⟺ ∃ j ∈ [i-W_K+1, i]:  lower_shadow(j) ∨ doji(j)
DEPTH(trough, k=1.0)    ⟺ peak_high(bo..trough) − low[trough] ≥ k × atr

止跌确认(i) ⟺ FLOOR(i) ∧ SPARSE_KLINE(i) ∧ DEPTH(trough_idx)
```

深度门 `pullback_min_atr` **不建议改**（现行 1.0；实证未测幅度门下的假阳漂移，改动缺证据）。

## 4. 推荐 `ThrowbackDetector.__init__` 参数默认值

**进 YAML 可调**（可解释、真 gating）：
- `stop_floor_window: int = 2`（几何底窗宽）
- `pullback_min_atr: float = 1.0`（现行不动）
- `max_start_gap: int = 5`、`max_window: int = 5`（现行不动）
- `atr_window: int = 14`、`big_rise_k: float = 1.5`（现行不动）
- `anchor_measure / support_measure`（现行不动）

**detector 内 constants**（避免过拟合调优面）：
- `_SPARSE_KLINE_POOL = ('lower_shadow', 'doji')` — 池成员硬编码
- `_STOP_KLINE_WINDOW = 2` — W_K 硬编码（若真想扩到 hammer/marubozu，重新走 spec 评审，不 YAML 调）

## 5. 承认的代价

1. **未直接兑现用户"任一信号即可"字面诉求**：用户举的 bullish / close_up 是高触发率信号（49%/50%），入池会稀释 gating；采纳"任一即可"必须收窄到稀缺池（lower_shadow + doji），是**方向修正而非否决**——用户核心不满（几何 AND 阻断纯 K 线证据）通过弱化几何门（S34→FLOOR M_floor=2）已回应。
2. **不含 bullish/close_up 的漏检风险**：下跌尾根强反（如"深探强吞没阳"）在几何底成立时会被 SPARSE_KLINE 门否，需要**用户提供 2-3 个具体漏检 ticker+日期**做 replay 验证——若确证漏，池再上开一层。
3. **W_K=2 是折中未严证**：W_K=1 太严、W_K=3 太松，W_K=2 未跑 A/B 与真实 tb 案例对拍。
4. **稀缺池排除 hammer/marubozu**：sparse4 W_K=3 = 78% 通过接近失效，加进池 gating 就崩；作为附录 A 的 UI label 用不入判据是对的。
5. **深度门未同步收紧**：R2 里我担忧"形态门放松、深度门要承接"，本轮实证显示形态门（FLOOR + SPARSE_KLINE）联合触发率 ≈ 11.2%（30.2% × 37.1%），比现行 17.9% 更严，反而不需要收紧深度门——但若后续加信号进池，需重新评估。

---

## 附实证脚本

数据源与脚本口径：`/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls_live/{AAPL,ABBV,AAL,ACRS,MBI}.pkl`；scratchpad 脚本已用完删除。

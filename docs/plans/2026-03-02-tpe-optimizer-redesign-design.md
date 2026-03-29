# TPE Optimizer Redesign — 方案 A

## 变更清单

| 参数 | 当前值 | 新值 |
|------|--------|------|
| n_startup_trials | 10 (默认) | 500 |
| n_trials | 3000 | 100000 |
| shrinkage_n0 | 50 | 20 |
| shrinkage_k (top_k) | 5 | 1 |
| trigger_rate 约束 | 硬约束 [3%,50%] | 移除 |
| Optuna 持久化 | 无 | JournalStorage 支持中断续跑 |

## 修改范围

仅 `BreakoutStrategy/mining/threshold_optimizer.py`：
1. `stage3b_optuna_search()` — 移除 trigger rate、加 storage、调 sampler
2. `main()` — 更新默认参数、添加 storage 路径管理

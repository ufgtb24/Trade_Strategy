# Scan Output Worktree Isolation

## 背景

`worktrees/master` 中执行扫描时，结果 JSON 落到了主仓库 `/home/yu/PycharmProjects/Trade_Strategy/outputs/scan_results/`，而非本 worktree 自己的 `outputs/`。Load Scan Results 对话框因 worktree 内 `outputs/` 不存在，回退到了 CWD。

## 根因

`configs/user_scan_config.yaml`（gitignored 的用户级 override）`output.output_dir` 写成了指向主仓库的绝对路径。`UIScanConfigLoader.get_output_dir()` 对绝对路径直接照用，绕过了 `_project_root` 拼接逻辑。

## 原则

输入数据共享、代码/配置/输出独立。即：

- 大体积、与代码无关的输入（`datasets/pkls/`）→ 跨 worktree 共享，避免重复拷贝
- 依赖代码与参数版本的产物（`outputs/scan_results/`、`outputs/analysis/`）→ 每个 worktree 独立
- 用户级配置（`user_*.yaml`）→ 每个 worktree 独立

## 改动

仅本 worktree，单点修改：

`configs/user_scan_config.yaml`：

```yaml
output:
  output_dir: outputs/scan_results   # 改前为绝对路径 /home/yu/.../Trade_Strategy/outputs/scan_results
```

相对路径会被 `UIScanConfigLoader.get_output_dir()` 拼到 `_project_root`（即本 worktree 根）。

## 不做

- 不动 `data_dir`（输入数据，共享是正确行为）
- 不动 `ui_config.yaml` 的 `stock_data.search_paths`（同上）
- 不动 `configs/scan_config.yaml`（git tracked 的基线默认值，不属于本 worktree 局部修改）
- 不预创建 `outputs/scan_results/` 目录（scanner 自动创建；如验证发现不会，再补 mkdir）

## 验证

1. 改后启动 dev UI，跑一次小规模扫描（少量股票、短日期）
2. 检查结果 JSON 实际落点：应在 `/home/yu/PycharmProjects/worktrees/master/outputs/scan_results/`
3. 主仓库 `/home/yu/PycharmProjects/Trade_Strategy/outputs/scan_results/` 不应出现新文件
4. 点击 Load Scan Results，对话框初始目录应是 worktree 内的 `outputs/scan_results/`

## 最有效的管理 Git 分支和工作树的方法：
git merge --squash feature-branch

## interactive rebase 方式整理提交记录
git rebase -i HEAD~n  # n 是要整理的提交数量
或使用 
git rebase -i <commit-hash>  # 使用特定的提交哈希

pick B ...       ← 保持 pick（作为合并目标）
squash C ...     ← 合并到 B
squash D ...     ← 合并到 B
squash E ...     ← 合并到 B

## 创建 Git worktree 并管理多个工作树
- 1. 创建并切换到新的 worktree
git worktree add -b feature ../worktrees/feature
git commit -m "Add new feature"

- 2. 回到 main worktree
git checkout main

- 3. 合并 feature 分支
git merge --squash feature

- 4. 推送合并后的 main
git push

- 5. 清理不需要的 worktree
git worktree remove ../worktrees/feature
如果有未提交的更改，可以使用强制删除：
git worktree remove -f ../worktrees/feature

- 6. 删除已合并的分支(可选)
git branch -d feature

## 强制推送和重置 Git 分支的方法：
本地进度覆盖远程进度
git push --force-with-lease

## 远程进度覆盖本地进度

- 1. 获取远程最新状态
git fetch origin

- 2. 将本地 master 分支强制重置为远程 origin/master 的状态
git reset --hard origin/master

## 设置默认编辑器
echo "export EDITOR='/snap/bin/pycharm-community --wait'" >> ~/.bashrc
source ~/.bashrc

echo 'export EDITOR="/home/yu/apps/pycharm-community-2024.3.5/bin/pycharm.sh --wait"' >> ~/.bashrc
source ~/.bashrc

取消(恢复 vscode)：
sed -i '/pycharm-community --wait/d' ~/.bashrc
source ~/.bashrc

## 条件断点
self.symbol == 'AAPL' and str(self.dates[peak_global_idx]) == '2023-01-01'

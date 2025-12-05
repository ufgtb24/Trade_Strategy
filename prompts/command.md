## 最有效的管理 Git 分支和工作树的方法：
git merge --squash feature-branch

## 创建 Git worktree 并管理多个工作树
- 1. 创建并切换到新的 worktree
git worktree add -b feature /home/yu/PycharmProjects/worktrees/feature
git commit -m "Add new feature"

- 2. 回到 main worktree
git checkout main

- 3. 合并 feature 分支
git merge feature

- 4. 推送合并后的 main
git push

- 5. 清理不需要的 worktree
git worktree remove /home/yu/PycharmProjects/worktrees/feature

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


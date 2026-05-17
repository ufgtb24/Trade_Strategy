claude -r --dangerously-skip-permissions
## 使用 ralph-loop 进行迭代改进
/ralph-loop:ralph-loop "根据新的人类模拟基准数据和分析报告对公式进行迭代改进，直到公式结果接近模拟结果" --completion-promise "Satisfied human cognition" --max-iterations 10
/ralph-loop:cancel-ralph

## 有 worktree 的时候， 如何 resume cc session in main branch
拿最新一条 session 的 uuid
ls -t ~/.claude/projects/-home-*PycharmProjects-Trade_Strategy/*.jsonl 2>/dev/null \
  | head -1 | xargs -n1 basename | sed 's/.jsonl$//'

然后:
claude --resume <uuid>

## 工作数双向同步法
  # B 上：压缩 + rebase
  git reset --soft $(git merge-base B A)                                                                                                
  git commit -m "feature B"
  git rebase A                                                                                                                          
                                                                  
  # A 上：fast-forward 合并                                                                                                             
  git merge B          # 直接 ff，无需任何参数       

## 最有效的管理 Git 分支和工作树的方法：
git merge --squash feature-branch

## 恢复提交但保留更改
git reset --soft HEAD~1  # 恢复上一个提交但保留更改   
git reset --soft commit-hash  # 恢复到特定提交但保留更改
git push --force-with-lease  # 强制推送更改到远程仓库

## interactive rebase 方式整理提交记录
git rebase -i HEAD~n  # n 是要整理的提交数量
或使用 
git rebase -i <commit-hash>  # 使用特定的提交哈希

pick B ...       ← 保持 pick（作为合并目标,第一个必须为 pick）
squash C ...     ← 合并到 B
squash D ...     ← 合并到 B
squash E ...     ← 合并到 B

## 将沿途分支 head 置于某个 commit 上
git branch -f simple-pool D'的新hash


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

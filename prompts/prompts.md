UI:
附图中 marker 和主图的对齐，悬停在副图 marker 上，产生向上延伸的变色区域

tooltip：
副图：事件类型
主图：内容分类(属性/where)

全局统一索引(idx 或 日期)

保持缩放：切换临时计算，level,拓扑图开关/role 都会刷新，已刷新缩放就变了，唯一改变缩放的刷新就是切换股票

成交量向下延伸 Bug

拓扑图隐藏，默认打开，可通过配置文件设置默认
下方定位图默认隐藏
在顶部设立3个复选框来决定是否显示/隐藏，或者每个图设置一个最小化/展开按钮，你来决定


sidebar 默认隐藏,为K线图留更大空间。我其实搞不懂 sidebar 有啥用，我从来不用。
不要角色漏斗层级，简化层级，将命中匹配和角色放到同一层级
- side 的顶级目录就是各种角色(包括匹配)
- 角色的下一级是角色的各个命中，可以在上一级内展开，例如突破爆发展开，直接是 burst 候选，也就是把当前的 "burst 候选" 移到 “突破爆发” 的展开中，并且移除 "burst 候选" 的名称，因为它和“突破爆发”是一个意思，重复了。同样，“回踩确认”和 “tb 候选” 也是重复的
- role 的颜色和拓扑图和 marker 副图保持一致。
- role item 和K线图或副图的同 event 的 marker 联动(取决于 marker 的 render_grid)，选中高亮
- 每个 role 展开都支持多个 level 的显示，至于显示哪个 level 也由 level 旋钮统一控制，切换 level 时，如果 item 还在，则选中 item 不变，如果 item 不在该 level,则不选中。

下方坐标图


.claude/skills/authoring-path2-app/design-heuristics.md： 
不要加具体 detector 的过于细节，只需要给出这种 detector/事件的含义，让模型知道在某些场景下也许能用上该事件。
着重于 dag 机制的描述，加入 anchor_field







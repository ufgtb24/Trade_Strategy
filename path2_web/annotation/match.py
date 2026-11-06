"""compare 对照用的两种容差(`.scratch/annotation-path2/spec.md` 第 10 节「match 容差」「认出」,共用常数):

- POS_TOL / NEG_TOL:sample 与 hit 比较时,hit 的买点离样本日几根以内算 matched;
- SUB_TOL:认出时子框对子段,子段终点离子框终点几根以内算对上(框本身按框终点那天精确取,不用容差)。

只在这里设定一处。界面(`path2_web_ui/src/annotate/compareRead.ts` 的 matchOf、pairOn)读的是标注路由带出的
同一组值(GET /annotations 的 match);以后由后端按 app 版本存 match 结果时,也读这里,不另设一份。
买点按 app 的 eval_meta 声明的买点 node 取,所以「样本日落在买点 node 那段事件里」已包含在「离样本日 0 根」里。
"""
POS_TOL = 3   # 暂定值,待用户在第一批真实标注后定:正样本,买点离样本日几根以内算 matched
NEG_TOL = 1   # 暂定值,同上:负样本
SUB_TOL = 2   # 暂定值,同上:子框终点与子段终点相差几根以内算对上

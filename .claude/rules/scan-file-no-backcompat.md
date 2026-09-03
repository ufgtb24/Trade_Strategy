---
paths:
  - "path2_web/**"
  - "path2_web_ui/**"
  - "scripts/path2/**"
  - "outputs/path2_web/scans/**"
---

# 扫描文件不做向后兼容

**`outputs/path2_web/scans/` 下的 scan 文件是一次性产物**。开发内容（scan/pattern_spec schema、参数换代、序列化字段、event_styles/前端渲染契约等）**不需要兼容旧 scan 文件**：改了就改了，不做迁移、双读或版本分支；旧 scan 过期作废，重新扫描即得新格式。

**Why**：scan 是「代码当前状态 × 当日数据」的快照，为快照保兼容等于冻结代码演进（实例：event_styles 内嵌进 scan 文件，颜色换代后旧 scan 仍带旧色——这是预期行为，不是要修的 bug）。

**How to apply**：
- schema/字段/样式变更不为旧 scan 写适配层；review 也不以「旧 scan 打不开/显示旧样式」为由要求兼容代码。
- 变更影响旧 scan 读者可见行为时，交付说明里提醒一句「旧 scan 需重扫生效」即可（例：92bc7e1 的 tb_seg 分色）。
- 真要跨版本对照旧数据：用当时的代码 checkout 跑，而不是让新代码背双格式。

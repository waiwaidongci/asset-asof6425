# 002 排借方案表

应用启动时以 SQLAlchemy 模型补建排借用表，不改动既有表结构。

- `plans` 排借方案：来源盘点运行、状态（draft 拟定中 / confirmed 已确认）、确认时间。新盘点完成后 `run_id` 跟进到最新运行。
- `plan_events` 方案场次：起止日、优先级（key 重点 / normal 普通）、需求行 JSON（工具、件数、替用品）、排借状态（scheduled 已排 / pending 待排 / conflict 冲突）、分配结果 JSON 与待排原因。

确认与后台刷新通过 `pg_advisory_xact_lock(20261121)` 串行，后确认的方案按已确认方案的占用重算。

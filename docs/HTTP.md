# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批和当前复核状态。

`PATCH /api/runs/<id>` 接收 `revision`、`status` 和 `note`。状态使用 `APPROVED` 或 `HELD`。冲突返回 409，客户端读取新版本后重试。

`GET /api/runs/<id>/evidence` 下载内含运行清单、行号隔离、业务证据和复核信息的 JSON。

## 表级独立签发

表版本接口以 `/api/tables` 或 `/api/release/tables` 为前缀，两组路径等价：

- `POST /api/tables`：登记表。
- `POST /api/tables/<table>/write-versions`：登记候选写版本，body 至少包含 `version` 与 `fields`。
- `POST /api/tables/<table>/read-versions`：登记读版本；`status=ACTIVE`（默认）表示仍在用。
- `POST /api/tables/<table>/read-versions/<version>/retire|restore`：退役或恢复读版本。
- `POST /api/tables/<table>/checks`（或 `/check`、`/verify`）：按稳定字段编号核对候选写版本与所有 ACTIVE 读版本，返回 `check_id`、逐读版本结论和阻塞读版本。
- `POST /api/release/checks/<check_id>/sign`（或 `/release`）：凭核对结论签发。核对后只要发生过读版本退役/恢复，就返回 `409 STALE_CHECK`，需重新核对。
- `POST /api/release-batches`：提交 `{batch_id, items:[{table, write_version, check_id}]}`。每张表独立事务；单表不兼容、结论失效或候选写版本冲突只影响该表，其他表仍返回 `RELEASED`。

`POST /api/release/demo` 载入兼容/不兼容样例；`POST /api/release/demo-concurrent` 直接运行两个并发批次并返回每张表的独立结果。

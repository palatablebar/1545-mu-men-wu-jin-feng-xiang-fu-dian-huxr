# SEAL STATION运行手册

更换班次或复算派单时使用。先确认 `/health` 返回 `ok`，再检查以下入口和凭证中的 `run_id`。

| 文档或路由 | 用途 |
|---|---|
| `sample_data/packing_plans_sample.json` | 同时提供拟合、校准、回放和当班的样例 |
| `GET /api/hingepack/overview` | 默认额度和样例处置 |
| `POST /api/hingepack/run` | 用 `capacity` 和 `strategy` 调整派单，也可同时提供 `records` 与 `as_of` |
| `POST /api/hingepack/revise` | 提交 `changes` 改单；支持 `request_id` 或 `Idempotency-Key` 重试 |
| `POST /api/hingepack/export` | 用同一次改单结果生成封签名册和余额 |
| `GET /api/hingepack/stages/<环节>` | 样例的分环节核对，可传相同额度、策略 |

导入 JSON 对象时 `records` 为 1–2500 条单据，`as_of` 为整数工日；默认第 96 日。额度接受 1–60，策略接受 `balanced` 或 `focus`。入站异常保留于第一环节。整批缺少成熟窗口时响应 422 并给出原因。

`/revise` 的 `changes` 可传新版单据或字段补丁（如 `key`、`revision`、`mass_g`）。旧版和同版冲突不会改变原派单；响应中的 `rows`、`export.roster` 与 `export.balance` 是同一份新名单和余额。网络重试应复用 `Idempotency-Key`。

```sh
docker compose exec -T app python -m hingepack.entry evaluate --input sample_data/packing_plans_sample.json --capacity 9
```

在网页筛选单号、作业区或原因，点击结果中的单号查看完整字段与处置证据。下载 JSON 可检视结果、对照原始资料摘要和模型特征版本。

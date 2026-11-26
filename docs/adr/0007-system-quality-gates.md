# ADR 0007：系统质量门禁与受控性能测试

**免责声明：仅供本科毕业设计、科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

- **状态：** 已采纳
- **日期：** 2026-11-26

## 决策

1. 复用阶段一至七已有的 xUnit、Angular、pytest、Playwright 与 PostgreSQL 集成用例；在回归报告内以需求、既有/新增用例、命令、运行记录 ID 和 `Pass` / `Fail` / `Blocked` / `NotRun` 状态追溯，不把 fixture 或跳过的 PostgreSQL 测试标为通过。
2. CI 的 PostgreSQL 服务是 EF Core 原生约束与迁移测试的必需依赖；本机无 PostgreSQL 时报告 `Blocked`，不改用 SQLite 的结果冒充 PostgreSQL。
3. 后台 Worker 租约恢复、固定请求 ID 的安全重试和标准 HTTP 熔断分别通过 SQLite/内存 HTTP 受控 fixture 验证；真实 PostgreSQL/MinIO 多进程恢复仍须由 Compose/集成流程验证。
4. 推理基准脚本只允许 `artifactKind: research` 且本地 manifest/权重哈希通过的模型。它测量一次 256×256 CPU ONNX 前向、完整病例模型前向及客户端完整 HTTP 请求；并发 1/5/10、连续 50 次、P95、错误码和可选本地进程 RSS 均写入版本化 JSON 报告。
5. 性能 API 调用会持久化预测对象；执行前必须显式确认使用可丢弃对象存储。报告不保存原始影像、患者标识、输入路径或服务令牌。当前推理 runtime 固定使用 CPUExecutionProvider，GPU性能状态必须是 `NotRun`，不能以主机检测到 GPU 代替 GPU 推理证据。
6. CI 通过 xUnit TRX、pytest JUnit XML 和 Playwright 输出保留测试证据。真实模型性能仅由手动触发、`research-controlled` 环境审批和专用 self-hosted runner 执行；不作为普通 pull request 的冒烟测试。

## 后果

- 应用 fixture 的通过结果与真实数据库、真实权重和真实体数据验证严格分开。
- 如果受控 runner、真实模型/输入或隔离对象存储未配置，性能工作流必须失败或记录 `NotRun`，不可形成空成功结论。
- 本地 Windows 环境缺少 Docker CLI 和 PostgreSQL 服务时，Compose 与 PostgreSQL 集成验收仍需在 CI 或受控环境完成。

## 验证

阶段八的实际命令、测试结果、错误码覆盖和环境阻塞记录在[阶段八系统质量门禁报告](../test-reports/0008-system-quality-gates.md)。合成 fixture 只验证软件行为，不构成研究结果。

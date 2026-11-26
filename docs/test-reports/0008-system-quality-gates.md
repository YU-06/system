# 阶段八：系统质量门禁与测试追溯

**免责声明：仅供本科毕业设计、科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

日期：2026-11-26  
目标分支：`test/phase-8-system-quality-gates`  
本地运行记录 ID：`phase8-local-20261126-a`  
运行环境：Windows x64、.NET SDK 10.0.400、Python 3.12.10、uv 0.13.7、Node 22；本机无 Docker、PostgreSQL、真实 BraTS 输入或研究权重。

## 状态定义

- **Pass**：命令实际执行且断言通过；报告同时标明 fixture 或真实依赖类型。
- **Fail**：实际执行存在失败；保留退出码与失败细节，不以其他重跑覆盖历史记录。
- **Blocked**：已尝试或因缺少必需环境无法执行。
- **NotRun**：未启动该项；特别用于真实数据/权重/GPU/远程 Actions 性能结果。

## 需求 → 用例 → 命令 → 运行记录 → 状态

| 需求 | 复用/新增用例 | 命令 | 记录 ID | 数据/环境 | 状态 |
| --- | --- | --- | --- | --- | --- |
| Domain 状态机、参数边界、重试上限 | `AggregateTests`、`JobStateTests` | `dotnet test apps\backend\BrainSeg.slnx --configuration Release --no-restore --logger "console;verbosity=minimal"` | `phase8-local-20261126-a` | xUnit 领域测试 | Pass |
| Application 上传、授权/匿名拒绝、幂等、并发戳、审计脱敏 | `StudyApplicationTests`、`PermissionTests`、`WorkflowTests` | 同上 | `phase8-local-20261126-a` | ASP.NET TestServer + SQLite + 合成 NIfTI | Pass |
| EF Core 模型/约束与 PostgreSQL 原生约束 | `PersistenceTests`；`PostgreSqlPersistenceTests` | 同上；CI 另外配置 PostgreSQL 17 service | `phase8-local-20261126-a` | SQLite 已执行；本机 PostgreSQL 未配置 | Blocked（4 项 skip） |
| 过期 Worker claim 恢复、重试后重新 claim | `InferenceReliabilityTests.Worker_recovers_an_expired_claim_and_retries_before_processing` | `dotnet test apps\backend\tests\BrainSeg.Tests\BrainSeg.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~InferenceReliabilityTests --logger "console;verbosity=minimal"` | `phase8-local-20261126-b` | SQLite + 等待型 processor 替身 | Pass |
| 推理请求安全重试、CorrelationId/requestId 保持 | `InferenceReliabilityTests.Segment_retry_reuses_request_and_correlation_ids` | 同上 | `phase8-local-20261126-b` | 内存 HTTP handler + 合成输入 | Pass |
| 标准 HTTP 熔断器在失败后阻断请求 | `InferenceReliabilityTests.Standard_http_resilience_pipeline_opens_circuit_after_failures` | 同上 | `phase8-local-20261126-b` | `Microsoft.Extensions.Http.Resilience` + 503 handler | Pass |
| FastAPI 标签、同步变换、参数/尺寸、空掩膜、预处理一致性、未就绪、非法输入、超时 | `ml/training/tests/*`、`services/ml-inference/tests/test_service.py` | `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q` | `phase8-local-20261126-a2` | 合成 NIfTI、ONNX fixture、替身 Predictor | Pass（88 passed；此前一次瞬时失败单独保留） |
| Angular 表单、权限、错误、切层/透明度及主流程 | `apps/web` Vitest 与 Playwright | `npm run format:check`; `npm run lint`; `npx tsc --noEmit --project tsconfig.json`; `npm test`; `npm run build`; `npm run test:e2e` | `phase8-local-20261126-a` | 合成影像 + HTTP fixtures，桌面/移动浏览器 | Pass |
| 上传类型/大小、路径隔离、错误码与日志/审计隐私 | `StudyApplicationTests`、`StorageTests`、`test_service.py`、`test_infrastructure.py` | 后端与 Python 测试命令见本表 | `phase8-local-20261126-a` | 安全测试 fixture；无真实敏感文件 | Pass（fixture） |
| CI 质量门禁、保留失败证据 | `test_ci_contains_all_required_executable_gates`、`test_real_performance_benchmark_is_manual_controlled_and_requires_pass` | `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q tests\test_infrastructure.py` | `phase8-local-20261126-c` | 本地 YAML/配置断言；远程 Actions 未触发 | Pass（静态配置）；远程运行 NotRun |
| Docker Compose 构建/启动、真实 PostgreSQL/MinIO 联调 | CI `docker` job | `docker --version` | `phase8-local-20261126-a` | Docker CLI 不存在 | Blocked |
| 单张前向、病例推理、端到端与并发 1/5/10 性能 | `infra/scripts/benchmark_inference.py` + NotRun fixture | `.tools\uv\uv.exe run --frozen --extra training --extra reports python infra\scripts\benchmark_inference.py --output "$env:TEMP\brainseg-phase8-performance-notrun.json"` | `phase8-local-20261126-perf` | 无真实数据/研究权重；脚本只生成 NotRun 模板，退出码 0 | NotRun |
| GPU 性能、真实 50 次成功率/资源变化 | 受控 workflow `Controlled Research Performance Benchmark` | 仅 `workflow_dispatch` 手动工作流 | `phase8-controlled-perf` | 无 GPU/真实模型；远程 workflow 未触发 | NotRun |
| 正式 BraTS 测试、论文成绩与错误统计 | 冻结测试流程及真实部署日志 | 未执行 | `phase8-research-notrun` | 无真实患者体数据及正式权重 | NotRun |

## 实际命令与结果

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `dotnet test apps\backend\BrainSeg.slnx --configuration Release --no-restore --logger "console;verbosity=minimal"` | 0 | 79 passed、4 skipped、0 failed；跳过的是 PostgreSQL 专项，不能计为通过 |
| `dotnet test apps\backend\tests\BrainSeg.Tests\BrainSeg.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~InferenceReliabilityTests --logger "console;verbosity=minimal"` | 0 | 3 passed：租约恢复、幂等重试、熔断 |
| `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q` | 1 | 86 passed、1 failed；`test_segment_request_id_replays_the_same_artifact_and_rejects_reuse` 首个请求 500、重放 200。日志只暴露稳定 `INTERNAL_ERROR`，无异常明文 |
| `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q services\ml-inference\tests\test_service.py::test_segment_request_id_replays_the_same_artifact_and_rejects_reuse` | 0 | 单项重跑 1 passed；全量失败目前未能隔离复现，不能据此删除失败证据 |
| `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q` | 0 | 最新全量重跑（含错误码断言更新）88 passed、0 failed；1 条 Starlette/httpx 弃用警告 |
| `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q services\ml-inference\tests\test_service.py::test_internal_service_key_protects_inference_and_prediction_download services\ml-inference\tests\test_service.py::test_evaluate_requires_traceable_prediction_and_reports_patient_and_slice_metrics services\ml-inference\tests\test_service.py::test_invalid_type_nifti_and_values_return_safe_errors services\ml-inference\tests\test_service.py::test_upload_decompression_and_dimension_limits` | 0 | 4 passed；验证新增的鉴权、标签、请求 ID 与上传大小错误码断言；1 条 Starlette/httpx 弃用警告 |
| `.tools\uv\uv.exe run --frozen --extra training --extra reports python infra\scripts\benchmark_inference.py --output "$env:TEMP\brainseg-phase8-performance-notrun.json"` | 0 | JSON 报告状态 `NotRun`、1 个 blocker；没有真实体数据或权重，临时文件已清理 |
| `.tools\uv\uv.exe run --frozen ruff format --check .` | 0 | 65 个 Python 文件已格式化 |
| `.tools\uv\uv.exe run --frozen ruff check .` | 0 | All checks passed |
| `dotnet format apps\backend\BrainSeg.slnx --verify-no-changes --no-restore` | 2（首次） | 新增测试文件行尾不符合仓库规则；已对该文件运行 `dotnet format ... --include ...` |
| `dotnet format apps\backend\BrainSeg.slnx --verify-no-changes --no-restore` | 0（修复后） | 格式门禁通过 |
| `npm run format:check` / `npm run lint` / `npx tsc --noEmit --project tsconfig.json` / `npm test` / `npm run build` / `npm run test:e2e`（工作目录 `apps\web`） | 均为 0 | 16 unit tests、4 desktop/mobile E2E 通过；构建初始 bundle 508.01 kB |
| `npm audit --audit-level=high`（工作目录 `apps\web`） | 0 | 0 项高危及以上依赖漏洞 |
| `docker --version` | 1 | `docker` 命令不存在；Compose 没有启动 |

全量 pytest 的一次性失败已保留；随后单项重跑和完整 88 项重跑均通过。失败当时为首个分割请求返回 500、同一请求重放 200，API 只返回 `INTERNAL_ERROR`。为不泄露异常文本，服务错误日志现在仅额外记录异常类型；新增受控 receipt 写入故障测试验证日志脱敏及幂等恢复。此前失败的准确异常类型不可从旧日志恢复，原因标记为未确证，不声称已定位原失败根因。Python 运行另有一条 Starlette/httpx 测试客户端弃用警告，未屏蔽。

本轮实现/验证中新增测试 harness 曾出现以下失败，修正记录保留在此：Python 测试模块一度不能导入 `infra`，改为按文件 URI 加载脚本；熔断测试最初配置非法 `Retry.MaxRetryAttempts=0`，后按真实 resilience 配置并显式禁用 unsafe HTTP retry；新 C# 测试文件行尾由 `dotnet format --include` 修正。这些是测试/格式配置问题，不作为产品功能通过证据。

## 性能协议与真实性限制

脚本输出 JSON 时记录源码提交、脚本版本、操作系统/处理器/逻辑核数、ONNX Runtime、模型架构/版本/预处理版本/阈值/权重哈希、输入尺寸与字节数、预热与重复次数、P95 nearest-rank 算法、1/5/10 并发吞吐、50 次成功率、错误码数和可选服务 PID RSS 变化。脚本不记录输入路径、影像字节、患者标识或令牌；每个完整 API 请求会创建预测对象，因此必须确认是可丢弃的隔离对象存储。

- 单张前向：经共享 `flair-v1` 预处理后，ONNX `session.run` 一张 256×256 切片的纯前向墙钟时间。
- 病例推理：FastAPI 返回的所有二维批次 `session.run` 时间总和，不包含排队。
- 完整请求：客户端 multipart POST 开始至响应体接收完成的墙钟时间。
- 当前 runtime 固定 `CPUExecutionProvider`，没有 GPU 同步路径；GPU 推理结果为 `NotRun`。可通过 `--service-pid` 采样同机推理进程 RSS；远程进程或无 PID 时资源监控明确写 `NotRun`。
- 本机 `data/` 与 `artifacts/models/` 不存在。没有执行训练、正式测试或真实研究模型推理，不报告任何性能数值、准确率或通过率作为研究结论。

## 性能结果表

| 指标 | 实测值 | 状态 | 缺失依据 |
| --- | --- | --- | --- |
| 单张 256×256 CPU ONNX 前向（ms） | — | NotRun | 无已验证真实研究权重 |
| 患者病例模型推理时间（ms） | — | NotRun | 无真实体数据与权重 |
| 完整 HTTP 请求时间（ms） | — | NotRun | 无真实推理部署及输入 |
| 并发 1：吞吐 / P95 | — | NotRun | 同上 |
| 并发 5：吞吐 / P95 | — | NotRun | 同上 |
| 并发 10：吞吐 / P95 | — | NotRun | 同上 |
| 连续 50 次：成功率 / RSS 变化 | — | NotRun | 受控 runner、真实输入与权重未配置 |
| GPU 推理时间 | — | NotRun | 当前服务仅使用 CPUExecutionProvider |

## 错误码与失败统计

服务 fixture 明确验证 `SERVICE_AUTH_REQUIRED`、`SERVICE_AUTH_NOT_CONFIGURED`、`MODEL_MANIFEST_NOT_CONFIGURED`、`MODEL_NOT_READY`、`MODEL_HASH_MISMATCH`、`TEST_ARTIFACT_NOT_ALLOWED`、`INVALID_FILE_TYPE`、`INVALID_NIFTI`、`INVALID_DIMENSIONS`、`INVALID_ORIENTATION`、`INVALID_NUMERIC_RANGE`、`INVALID_REQUEST_ID`、`UPLOAD_TOO_LARGE`、`VOLUME_TOO_LARGE`、`INVALID_LABELS`、`LABEL_ALIGNMENT_INVALID`、`PREDICTION_SOURCE_MISMATCH`、`INVALID_OBJECT_REFERENCE`、`IDEMPOTENCY_CONFLICT`、`REQUEST_RECEIPT_INVALID`、`INFERENCE_TIMEOUT` 与 `INTERNAL_ERROR`。这些是替身服务的断言覆盖，不是线上发生次数。

| 范围 | 实际记录 | 状态 |
| --- | --- | --- |
| 后端完整套件 | 79 passed、4 skipped、0 failed | Pass（PostgreSQL 4 项仍 Blocked） |
| Python 全量最终运行 | 88 passed、0 failed | Pass；保留此前 1 个瞬时失败记录 |
| Python 全量失败历史 | 1 次 `INTERNAL_ERROR` 首请求；同请求重放成功 | Fail（单次历史证据，根因未确证） |
| Angular 单元与 E2E | 16 + 4 passed、0 failed | Pass（合成 fixtures） |
| 服务错误码 fixture 覆盖 | 上述 22 类稳定错误码有断言 | Pass（不代表生产次数） |
| 真实服务错误码发生次数 | — | NotRun |
| 性能请求失败/50 次资源变化 | — | NotRun |

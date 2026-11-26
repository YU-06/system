# BrainSeg 科研教学系统

**仅供本科毕业设计、科研与教学演示。非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

## 当前范围

当前已实现 BrainStudy、SegmentationJob、ModelVersion、SegmentationResult、ExperimentRun 的领域/应用/持久化功能，并将完整 NIfTI 上传、幂等 Job 创建、数据库轮询后台推理、模型/权重快照、结果哈希登记、授权下载及独立 GT 评价串联起来。后台处理通过数据库 Pending 队列、ClaimToken/租约认领及对象写入补偿支持进程恢复；完整 Worker + FastAPI + PostgreSQL/MinIO 故障恢复联调仍需按[阶段六测试报告](docs/test-reports/0006-abp-inference-background-jobs.md)完成。没有真实训练权重、完整训练实验或正式测试结果，所有真实研究指标仍为 `NotRun`。

初始化时仓库仅包含 Git 元数据与 Copilot 约定，未找到独立审计报告。本次以现有约定和实际构建/测试结果为依据，不声称存在未提供的审计结论。

## 工程与版本

| 部分 | 版本与位置 |
| --- | --- |
| 后端 | .NET SDK 10.0.400、ABP 10.7.1，`apps/backend`，七层模块化单体 |
| 对象映射 | ABP AutoMapper 模块，AutoMapper 15.1.4 安全修补版；配置工厂已适配 |
| 前端 | Node 22.23.4、Angular 22.2.4、CLI/build 22.2.6，`apps/web`，Standalone |
| 推理 | Python 3.12.10、FastAPI 0.162.0、ONNX Runtime 1.31.1，`services/ml-inference` |
| 训练骨架 | `ml/training` 与 `ml/configs/baseline.yaml`，可选 PyTorch 2.15.0 |
| 数据库 | PostgreSQL 17，EF Core PostgreSQL，已生成基础设施及五个领域表的迁移与快照 |
| 文件 | 开发默认 `IObjectStorage` 本地实现；Compose 使用 MinIO/S3 适配器 |
| 对象存储镜像 | 官方 MinIO 2025-10-15 源码固定提交构建，保留 AGPL 许可证 |
| 锁定 | NuGet `packages.lock.json`、npm `package-lock.json`、Python `uv.lock` |

没有使用 Redis，因此没有创建无消费者的 Redis 容器。不引入多租户、微前端或额外业务微服务。

## 领域功能

五个聚合均使用 ABP 审计、软删与并发戳；状态没有公共 setter。Job 只允许 Pending → Running → Succeeded/Failed/Cancelled、Pending → Cancelled，以及 Failed → Pending 的显式重试，最多三次重试。创建请求按请求人和幂等键去重，成功状态和唯一结果在同一事务写入。

所有业务接口都要求认证；写操作还要求相应权限，未创建默认管理员或匿名写入口。列表支持分页、筛选与白名单排序，每页最多 100 条。上传计算真实 SHA-256，数据库不存 MRI 二进制。删除 Study 会软删，活动任务会阻断删除，关联终态任务、结果和对象文件保留，不做隐式物理级联清理。

类图、ER 图、状态图、权限、API 与保留策略见 [领域文档](docs/api/research-domain.md)，请求示例见 [research.http](apps/backend/research.http)，设计决策见 [ADR 0002](docs/adr/0002-research-domain.md)，本阶段验证见 [测试报告 0002](docs/test-reports/0002-research-domain.md)。现有 `--migrate` 命令会同时应用新增领域迁移。

AutoMapper 15 的无许可证开发/测试运行会发出许可提示，未屏蔽；生产使用须遵守其许可要求，通过本地 `.env` 或部署密钥配置 `AutoMapper__LicenseKey`，禁止把真实许可证提交到 Git。

## 从零启动：Docker Compose

前置条件：安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/) 并启动 Linux 容器引擎，使用 Compose v2.20 或更高版本；安装 [uv 0.13.7](https://docs.astral.sh/uv/getting-started/installation/)。首次构建需要访问 GitHub、NuGet、npm、PyPI 和容器镜像仓库。MinIO 从源码构建，首次启动耗时长于后续启动。

在仓库根目录执行，以下命令也适用于 PowerShell：

```powershell
uv python install 3.12.10
uv sync --frozen
uv run --frozen python infra/scripts/init_env.py
docker compose config --quiet
docker compose up --build --wait --wait-timeout 240
```

初始化脚本从唯一的 `.env.example` 创建被 Git 忽略的 `.env`，为 PostgreSQL、MinIO 和 FastAPI 服务间认证分别生成独立随机密钥，并将共享推理密钥配置到后端与推理容器，不打印密钥、不覆写已有 `.env`。已有文件时跳过初始化命令。不要提交 `.env`、真实权重、MRI、证书或私钥；不要运行会把解析后密钥输出到终端/日志的普通 `docker compose config`。

启动顺序为 PostgreSQL 就绪、一次性 `backend-migrate` 执行 EF 迁移、后端启动、前端启动；MinIO 与推理进程也有健康检查。迁移失败时后端不会继续启动。

| 地址 | 用途 |
| --- | --- |
| http://localhost:4200 | 中文研究工作台 |
| http://localhost:5000/swagger | 后端 OpenAPI |
| http://localhost:5000/health | 后端存活，不依赖外部服务 |
| http://localhost:5000/ready | 数据库、对象存储、推理进程连接检查 |
| http://localhost:8000/docs | 推理服务 OpenAPI |
| http://localhost:8000/health | 推理进程存活，可在无模型时成功 |
| http://localhost:8000/ready | 模型完整性与加载就绪；无模型时 **503 是预期结果** |
| http://localhost:9001 | MinIO 控制台，账号来自本地 `.env` |

所有对外端口仅绑定 `127.0.0.1`。端口冲突时修改 `.env` 中对应的端口；本地前后端分开运行时同步调整 `BACKEND_DEV_URL` 与 `App__CorsOrigins`。

```powershell
docker compose ps
docker compose logs --follow backend ml-inference
docker compose down
```

`down` 保留命名数据卷；`down --volumes` 会删除本地数据库和对象文件，仅适用于明确需要重置的演示数据。

## 不使用容器运行应用

除 uv 外，安装上述精确版本的 .NET SDK 与 Node，并先准备 PostgreSQL；可仅用 `docker compose up -d postgres object-storage` 启动依赖。各应用从同一个根 `.env` 读取配置，前端只在开发代理/生成代理脚本中使用后端地址，不将私有环境变量打入浏览器包。

后端，根目录 PowerShell：

```powershell
dotnet tool restore
dotnet restore apps/backend/BrainSeg.slnx --locked-mode
$env:ASPNETCORE_ENVIRONMENT = 'Development'
dotnet run --project apps/backend/src/BrainSeg.HttpApi.Host -- --migrate
dotnet run --project apps/backend/src/BrainSeg.HttpApi.Host --urls http://127.0.0.1:5000
```

推理服务，在另一个根目录终端：

```powershell
uv run --frozen uvicorn brainseg_inference.app:app --host 127.0.0.1 --port 8000 --no-access-log --log-config services/ml-inference/logging.json
```

前端，在第三个终端：

```powershell
cd apps/web
npm ci
npm start
```

没有数据库时仍可启动后端查看 `/health`、Swagger 和公开系统状态；`/ready` 将返回不包含内部连接详情的 503。Identity/OpenIddict/Permission 模块和迁移已配置，管理 API 要求认证；本阶段**不创建默认管理员、OAuth 客户端或登录界面**。开发环境使用临时签名密钥，重启后失效。

## 推理与训练协议

推理提供 `GET /health`、`GET /ready`、`GET /models`、`POST /v1/segment`、`POST /v1/evaluate`。数据接口要求 Compose 生成的 Bearer 服务密钥；未配置密钥时推理、评价与预测下载 fail-closed。仅接受经过类型、大小、解压后大小、维度、仿射矩阵和有限值校验的 NIfTI-1 `.nii/.nii.gz`，用户文件名不用于存储路径。接口错误使用稳定错误码。

推理服务仅在部署提供经验证的研究 ONNX 权重和版本化 YAML 清单后才会就绪。把两者放在被忽略的 `artifacts/models`，令 `weightFile` 使用同目录文件名，并在清单中登记实际 SHA-256、模型版本、架构、`flair-v1`、256 输入尺寸、验证集冻结阈值及 `artifactKind: research`。在 `.env` 中设置 `ML_MODEL_MANIFEST_PATH=/models/model-manifest.yaml`，然后重建推理容器。仓库中的 [`model-manifest.example.yaml`](services/ml-inference/model-manifest.example.yaml) 明确标为合成测试产物，不能用于启用研究模型：

```powershell
docker compose up -d --force-recreate ml-inference
```

启动时核对清单与权重 SHA-256，并验证 ONNX 模型元数据里的架构、预处理版本、输入尺寸和阈值。模型输入是 float32 `[N,1,256,256]`，输出为同尺寸 logits，不是已 sigmoid 的概率。未配置模型或加载失败时进程仍可通过 `/health` 诊断，但 `/ready` 返回 503；不静默使用随机模型。阈值必须来自验证集，不能用测试集调参。仅 `artifactKind: research` 可就绪，合成测试权重不会登记成研究权重。

`POST /v1/segment` 的 multipart 字段为完整 T2-FLAIR NIfTI `file` 和稳定 `requestId`，返回逆变换到原空间的三维预测对象键、SHA-256、模型/预处理/权重版本、阈值、计时和关联 ID，不含准确性指标。相同请求标识可安全重放并返回相同预测对象。`POST /v1/evaluate` 接收原始 `file`、BraTS `label` 与系统生成的 `predictionObjectKey`，先严格核对形状、方向、spacing、affine、qform/sform 和单位，不匹配时拒绝计算、不静默插值；结果包含患者级与切片宏平均指标。响应和对象 sidecar 会标明 `artifactKind`，合成替身结果不属于真实研究结果。接口契约与稳定错误码见 [推理 API 文档](docs/api/ml-inference.md)，模型清单和就绪策略见 [阶段五 ADR](docs/adr/0004-fastapi-inference-service.md)，实际验收结果见 [阶段五测试报告](docs/test-reports/0005-fastapi-inference-service.md)。ABP 上传—任务—结果时序、任务状态、权限、错误码、重试、逻辑取消与对象补偿策略见 [科研领域与 API 文档](docs/api/research-domain.md)。阶段四实验控制、配对统计口径与测试冻结规则见 [阶段四实验协议](docs/adr/0003-experiment-protocol.md) 和 [阶段四测试报告](docs/test-reports/0004-experiment-protocol.md)。真实 BraTS 训练、正式测试及相应真实指标尚未执行，仍为 `NotRun`。禁止把合成 smoke 作为论文结果。

```powershell
uv run --frozen python -m training validate-config
uv run --frozen python -m training split --patients data/patient_ids.json --output artifacts/split_manifest.json
```

患者 ID 文件必须是真实数据集中 369 个不同的去标识化 ID 的 JSON 数组，不是切片列表。工具固定生成 258/74/37 患者级划分和 SHA-256；没有真实患者清单时不会伪造 manifest。共享 `flair-v1` 预处理只使用当前体数据非零脑区统计量。默认协议为 3 个种子、相同通道与训练参数、最大 100 轮、验证 Dice 15 轮早停、测试集锁定。

阶段四固定种子为 17、42、2024；阈值由验证集三维重建后的患者宏平均 Dice 从 0.30–0.70（0.05 步长）中选择，并提供固定 0.50 敏感性分析。测试 CLI 仅接受配置、划分、模型权重和验证报告完全匹配的冻结记录。真实产物齐备后可用 `uv run --frozen --extra reports python -m training.generate_reports --runs artifacts/runs --split artifacts/split_manifest.json --cache artifacts/preprocessed/index.json --output artifacts/paper-reports` 生成表图，固定 0.50 敏感性分析另加 `--threshold-mode fixed_050` 并写入独立输出目录；该命令不训练、不测试，合成或不完整输入只生成 `NotRun` 模板。

## 验证与 CI

骨架阶段的 Angular 7 项、Python 24 项及浏览器 2 项测试结果见 [骨架报告](docs/test-reports/0001-skeleton.md)。2026-11-06 领域阶段完整后端回归为 **79 通过、4 项 PostgreSQL 环境跳过、0 失败**；严格依赖恢复、Release 构建、格式门禁、迁移快照及幂等 SQL 生成均通过，详情见 [领域报告](docs/test-reports/0002-research-domain.md)。阶段六回归为后端 **76 通过、4 项跳过**、Python **83 通过**；并行 Worker、进程重启与结果提交故障注入尚未端到端验证，详见[阶段六报告](docs/test-reports/0006-abp-inference-background-jobs.md)和[阶段六 ADR](docs/adr/0005-abp-inference-background-jobs.md)。许可证和依赖弃用提示均如实保留。

**容器验收尚未完成：Docker build、Compose 启动、真实 PostgreSQL 迁移与 MinIO 联调均未执行。应用测试通过不能替代容器全链路验收。** 需先在宿主机安装并启动 Docker Desktop 的 Linux 容器引擎，再按上文命令完成验证；本项目不会自动提权安装系统组件。

```powershell
dotnet restore apps/backend/BrainSeg.slnx --locked-mode
dotnet build apps/backend/BrainSeg.slnx --configuration Release --no-restore
dotnet format apps/backend/BrainSeg.slnx --verify-no-changes --no-restore
dotnet test apps/backend/BrainSeg.slnx --configuration Release --no-build
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen --extra training --extra reports pytest
```

前端目录：

```powershell
npm ci
npm run format:check
npm run lint
npx tsc --noEmit --project tsconfig.json
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Windows 已安装 Edge 时可用 `$env:PLAYWRIGHT_CHANNEL='msedge'`，跳过 Chromium 下载，运行相同 E2E。API 变更后先启动后端，再在前端执行 `npm run generate-proxy`；使用官方 ABP schematics，随后通过 TypeScript AST 将生成代码中的 `any` 收紧为 `unknown`，不手写重复 HTTP 请求。

CI 分别执行 .NET restore/build/format/test、npm ci/format/lint/test/build/E2E、Python Ruff/pytest，以及所有 Docker 镜像构建与 Compose 健康冒烟测试。实际执行结果、环境阻塞和未执行项见 [测试报告](docs/test-reports/0001-skeleton.md)，架构选择见 [ADR](docs/adr/0001-skeleton.md)。

## 日志与边界

ABP/Serilog、FastAPI、Nginx 输出 JSON 日志，统一使用 `CorrelationId` 字段与 `X-Correlation-Id` 请求头。后端与反向代理验证外部 ID，只接受 1–64 位 ASCII 字母、数字、`-`、`_`，否则重新生成；命名 ML HTTP 客户端传播 ID，Python 在日志、响应头和响应体中保持一致。不记录 MRI 内容、令牌、患者真实身份或请求体。

这是本地演示配置，不是生产部署：没有 TLS 终止、永久 OpenIddict 证书、生产 IAM、备份恢复或高可用；部署到非本机环境之前必须补齐这些控制并扫描镜像。非开发环境后端要求显式证书，不回退到开发证书。MinIO 社区源码的许可证和维护状态需要在正式部署前单独评估。
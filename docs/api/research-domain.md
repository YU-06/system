# 科研领域与 API

仅供科研与教学演示，非医疗器械，不用于临床诊断。本文中的指标字段不是实际 BraTS 实验结论。

## 分层与约束

Domain.Shared 放枚举、错误码和本地化资源；Domain 放五个聚合及仓储接口；Application.Contracts 放 DTO、服务接口及权限定义；Application 编排授权、存储、事务及映射；EntityFrameworkCore 实现仓储、约束和迁移；HttpApi.Host 沿用 ABP 自动控制器，不在控制器实现业务规则。

所有实体继承 `FullAuditedAggregateRoot<Guid>`，共用 Id、CreationTime、CreatorId、LastModificationTime、LastModifierId、IsDeleted、DeletionTime、DeleterId、ConcurrencyStamp 和 ExtraProperties。业务时间以 UTC 存储。结果和实验记录是不可变记录，没有任意更新或物理删除 API。

## Mermaid 类图

```mermaid
classDiagram
  direction LR
  class FullAuditedAggregateRootGuid {
    +Guid Id
    +DateTime CreationTime
    +Guid CreatorId
    +bool IsDeleted
    +string ConcurrencyStamp
  }
  class BrainStudy {
    +string StudyNumber
    +string Pseudonym
    +string Modality
    +string OriginalFileObjectKey
    +string OriginalFileSha256
    +string GroundTruthObjectKey
    +string GroundTruthSha256
    +int Width
    +int Height
    +int SliceIndex
    +BrainStudyStatus Status
    +int JobRequestCount
    +MarkReady()
    +ChangePseudonym(string)
    +RecordJobRequest()
    +Archive(bool)
    +EnsureCanDelete(bool)
  }
  class SegmentationJob {
    +Guid StudyId
    +Guid ModelVersionId
    +Guid RequesterId
    +string IdempotencyKey
    +SegmentationJobStatus Status
    +int Progress
    +string CorrelationId
    +DateTime RequestedTime
    +DateTime StartedTime
    +DateTime CompletedTime
    +string ErrorCode
    +string ErrorMessage
    +int RetryCount
    +string InputSha256
    +string WeightSha256
    +string PreprocessingVersion
    +double Threshold
    +DateTime LeaseExpiresAt
    +Start(DateTime, lease, claimToken)
    +ReportProgress(int)
    +Complete(DateTime)
    +Fail(JobFailureReason, DateTime)
    +Cancel(DateTime)
    +Retry(DateTime)
  }
  class ModelVersion {
    +string Name
    +string NormalizedName
    +ModelArchitecture Architecture
    +string SemanticVersion
    +string PreprocessingVersion
    +string WeightObjectKey
    +string WeightSha256
    +int InputSize
    +double Threshold
    +string MetricsJson
    +bool IsActive
    +bool IsDefault
    +DateTime PublishedTime
    +Activate(DateTime)
    +Deactivate()
    +MakeDefault()
    +ClearDefault()
  }
  class SegmentationResult {
    +Guid JobId
    +string MaskObjectKey
    +string MaskSha256
    +string RemotePredictionObjectKey
    +string RemotePredictionSha256
    +string GroundTruthSha256
    +string EvaluationProtocol
    +string OverlayObjectKey
    +string ContourObjectKey
    +double Dice
    +double IoU
    +double Precision
    +double Recall
    +int TumorAreaPixels
    +double TumorAreaRatio
    +double InferenceMilliseconds
    +double PreprocessingMilliseconds
    +double PostprocessingMilliseconds
    +DateTime CreatedTime
  }
  class ExperimentRun {
    +string ExperimentName
    +string ConfigHash
    +string GitCommit
    +string DatasetSplitHash
    +int RandomSeed
    +Guid ModelVersionId
    +string MetricsJson
    +string ArtifactObjectKey
    +DateTime CreatedTime
  }
  class ObjectWriteIntent {
    +string ObjectKey
    +string Purpose
    +DateTime RequestedTime
    +DateTime NextAttemptTime
    +int AttemptCount
  }
  FullAuditedAggregateRootGuid <|-- BrainStudy
  FullAuditedAggregateRootGuid <|-- SegmentationJob
  FullAuditedAggregateRootGuid <|-- ModelVersion
  FullAuditedAggregateRootGuid <|-- SegmentationResult
  FullAuditedAggregateRootGuid <|-- ExperimentRun
  BrainStudy "1" --> "0..*" SegmentationJob : StudyId
  ModelVersion "1" --> "0..*" SegmentationJob : ModelVersionId
  SegmentationJob "1" --> "0..1" SegmentationResult : JobId
  ModelVersion "1" --> "0..*" ExperimentRun : ModelVersionId
```

图中的 StartedTime、CompletedTime、PublishedTime、ErrorCode/ErrorMessage 和四个结果指标允许为空。没有真值标签时，结果指标保持 null，不用 0 或 1 冒充实验结果。

## Mermaid 数据库 ER 图

```mermaid
erDiagram
  BrainStudies ||--o{ SegmentationJobs : retains
  ModelVersions ||--o{ SegmentationJobs : versions
  SegmentationJobs ||--o| SegmentationResults : produces
  ModelVersions ||--o{ ExperimentRuns : records
  ObjectWriteIntents {
    uuid Id PK
    varchar ObjectKey UK
    varchar Purpose
    timestamptz RequestedTime
    timestamptz NextAttemptTime
    int AttemptCount
  }
  BrainStudies {
    uuid Id PK
    varchar StudyNumber
    varchar Pseudonym
    varchar Modality
    varchar OriginalFileObjectKey
    varchar OriginalFileSha256
    varchar GroundTruthObjectKey
    varchar GroundTruthSha256
    int Width
    int Height
    int SliceIndex
    int Status
    int JobRequestCount
    timestamptz CreationTime
    uuid CreatorId
    boolean IsDeleted
    varchar ConcurrencyStamp
  }
  SegmentationJobs {
    uuid Id PK
    uuid StudyId FK
    uuid ModelVersionId FK
    uuid RequesterId
    varchar IdempotencyKey
    int Status
    int Progress
    varchar CorrelationId
    varchar InputSha256
    int Architecture
    varchar ModelSemanticVersion
    varchar PreprocessingVersion
    varchar WeightSha256
    int InputSize
    double Threshold
    uuid ClaimToken
    timestamptz LeaseExpiresAt
    timestamptz RequestedTime
    timestamptz StartedTime
    timestamptz CompletedTime
    varchar ErrorCode
    varchar ErrorMessage
    int RetryCount
    varchar ConcurrencyStamp
  }
  ModelVersions {
    uuid Id PK
    varchar Name
    varchar NormalizedName
    int Architecture
    varchar SemanticVersion
    varchar PreprocessingVersion
    varchar WeightObjectKey
    varchar WeightSha256
    int InputSize
    double Threshold
    varchar MetricsJson
    boolean IsActive
    boolean IsDefault
    timestamptz PublishedTime
    varchar ConcurrencyStamp
  }
  SegmentationResults {
    uuid Id PK
    uuid JobId FK, UK
    varchar MaskObjectKey
    varchar MaskSha256
    varchar OverlayObjectKey
    varchar ContourObjectKey
    varchar RemotePredictionObjectKey
    varchar RemotePredictionSha256
    varchar GroundTruthSha256
    varchar EvaluationProtocol
    double Dice
    double IoU
    double Precision
    double Recall
    int TumorAreaPixels
    double TumorAreaRatio
    double InferenceMilliseconds
    double PreprocessingMilliseconds
    double PostprocessingMilliseconds
    timestamptz CreatedTime
    varchar ConcurrencyStamp
  }
  ExperimentRuns {
    uuid Id PK
    varchar ExperimentName
    varchar ConfigHash
    varchar GitCommit
    varchar DatasetSplitHash
    int RandomSeed
    uuid ModelVersionId FK
    varchar MetricsJson
    varchar ArtifactObjectKey
    timestamptz CreatedTime
    varchar ConcurrencyStamp
  }
```

为简洁起见，ER 图省略部分继承审计列；五张表都包含完整审计与软删列。所有外键使用 RESTRICT，不进行物理级联。复合及条件唯一性以实际索引表为准，不把复合键误画成单列唯一。

| 唯一索引 | 键 | 范围 |
| --- | --- | --- |
| UX_BrainStudies_Number | StudyNumber | 仅 IsDeleted=false，编号归一化为大写 |
| UX_BrainStudies_FileSlice | OriginalFileSha256, SliceIndex | 仅 IsDeleted=false；同体不同切片可单独登记 |
| UX_ModelVersions_Identity | Architecture, NormalizedName, SemanticVersion | 仅 IsDeleted=false |
| UX_ModelVersions_Default | IsDefault | 仅 IsDefault=true 且 IsDeleted=false，全局最多一个默认模型 |
| UX_SegmentationJobs_Idempotency | RequesterId, IdempotencyKey | 保留历史身份，不因软删而释放 |
| UX_SegmentationResults_Job | JobId | 一个任务最多一个结果 |
| UX_ExperimentRuns_Reproducibility | ExperimentName, ConfigHash, DatasetSplitHash, GitCommit, RandomSeed, ModelVersionId | 同一可复现身份不能重复登记 |

另建 Study 状态/时间、Job 状态/请求时间、StudyId/状态、模型启用/架构、结果及实验时间索引。检查约束限定图像尺寸、进度、重试数、输入尺寸、阈值、默认模型启用状态、面积、指标及耗时。

## 状态机

```mermaid
stateDiagram-v2
  [*] --> Pending
  Pending --> Running: persistent worker claims with concurrency stamp
  Pending --> Cancelled: Cancel
  Running --> Succeeded: worker commits one result and success atomically
  Running --> Failed: Fail
  Running --> Cancelled: logical cancellation; remote work may continue
  Running --> Failed: lease expires; retry eligible when below limit
  Failed --> Pending: Retry count below 3
  Succeeded --> [*]
  Cancelled --> [*]
```

进度仅在 Running 下可递增到 99，只有成功完成能设为 100。失败原因来自受限枚举，不接受任意堆栈/内部路径作为 ErrorMessage。重试保持同一 Job，递增 RetryCount，清空上一轮错误、计时及进度。Failed 达到上限后不再重试。

Study 是 Uploaded → Ready → Archived；只有 Ready 且未删除的影像可接受任务。模型登记初始未启用；启用前验证对象 SHA-256，设为默认必须先启用，停用同时取消默认标记。停用不删除权重，也不阻止此前已接收任务完成；新建和重试任务要求启用模型。注册/启用仅表示业务登记状态，不替代 FastAPI 的模型加载就绪检查。

## API 与权限

沿用现有 ABP 自动控制器和统一错误封装。OpenAPI JSON 为 `/swagger/v1/swagger.json`，Swagger UI 为 `/swagger`；运行时地址和 FastAPI schema 见 [API/OpenAPI 索引](README.md)。创建与命令返回 200，删除成功返回 204；未认证 401、无权限 403、未找到 404、并发与状态/唯一性冲突 409、无效输入 400、超限 413、推理依赖不可用 503。不要另加绕过 Application Service 的写接口。

| 资源前缀 `/api/app/` | 操作 | 父级读权限 | 写入附加权限 |
| --- | --- | --- | --- |
| brain-study | 列表/详情、upload、PUT、archive、DELETE、register-ground-truth、download-ground-truth、delete-ground-truth | BrainSeg.BrainStudies | Create / Update / Delete / RegisterGroundTruth / DeleteGroundTruth |
| segmentation-job | 列表/详情、创建、cancel、retry | BrainSeg.SegmentationJobs | Create / Cancel / Retry |
| model-version | 列表/详情、创建、set-state | BrainSeg.ModelVersions | Create / Manage |
| segmentation-result | 列表/详情、download-mask、evaluate | BrainSeg.SegmentationResults | Download / Evaluate |
| experiment-run | 列表/详情、创建不可变记录 | BrainSeg.ExperimentRuns | Create |

Job 的 Start、Fail、Complete 和进度更新仅由后台 Worker 在服务端执行；没有允许调用方提交预测键、结果指标或终态的 HTTP API。任务创建必须有用户 ID，服务主体不能靠随机请求人绕过幂等分区。取消 Running Job 是逻辑取消：远端计算可能继续，但 claim token 已失效，迟到结果会被丢弃。当前是权限控制的单租户科研工作区，不提供患者姓名、证件号或医院编号字段。

写命令必须提交详情接口返回的 ConcurrencyStamp。PUT 和 POST 将其放入 JSON；Study DELETE 使用查询参数 `?concurrencyStamp=...`。服务器先拒绝已过期的客户端戳，再由 EF 的并发令牌拒绝“两个调用同时读到旧版本”的竞争。

列表参数为 skipCount、maxResultCount（1–100）、filter、sorting（单字段及 asc/desc）。默认 creationTime desc，附加 Id 稳定排序。排序白名单：Study 的 creationTime/studyNumber/pseudonym/status；Job 的 creationTime/requestedTime/status/progress；模型的 creationTime/name/semanticVersion/architecture；结果的 creationTime/createdTime/inferenceMilliseconds/tumorAreaPixels；实验的 creationTime/createdTime/experimentName/randomSeed。语义版本字符串排序为字典序，不冒充版本优先级比较。

宿主 API 请求上限为 64 MiB + 128 KiB multipart 开销；全局固定窗口限流为 Kestrel 所见客户端地址每分钟 120 次，满额直接 429、不排队。当前 Host 未配置 Forwarded Headers 信任规则；反向代理部署前必须设置可信代理和客户端 IP 传递，避免所有请求共用代理地址额度，也不能信任任意转发头。生产需由边缘代理增加速率限制和 HTTPS；CORS 默认仅本机工作台来源，不能作为服务端授权。

各列表另支持状态、StudyId、ModelVersionId、架构、启用、JobId 或随机种子的相应筛选。结果 filter 匹配 Job CorrelationId。禁止传任意动态 LINQ 表达式。

## 文件、事务与保留策略

上传为 multipart：StudyNumber、Pseudonym、SliceIndex、File。只收 NIfTI-1 .nii/.nii.gz，原始文件上限 64 MiB、解压上限 128 MiB，检查头、字节序、三维尺寸、切片边界、真实数值类型和完整载荷。服务端从头读取尺寸，文件名不用于对象路径；原始字节计算 SHA-256 后交给 IObjectStorage，数据库只存键、哈希和元数据。完整数值范围、仿射变换及模型输入验证仍由共享 Python 推理实现负责，不在 ABP 中重写模型算法。

上传、真值与预测对象写入前先持久化 `ObjectWriteIntent`。Study/Result 与移除意图在同一数据库 Unit of Work 提交；进程重启后补偿 Worker 等待五分钟宽限，再检查外键/对象键引用，删除未引用对象，失败时指数退避重试。这样也能处理数据库提交结果未知的情况，而不会在已提交 Result 仍引用对象时提前删除文件。File 属性标记 DisableAuditing，不把文件名或原始文件内容放进审计参数；仍记录上传操作及操作者。

创建或重试任务会更新 Study.JobRequestCount，推进同一 Study 的并发版本。因此“检查无活动任务后软删”和“并发调度”不能同时用旧版本成功。JobRequestCount 是已接收的调度次数，包含重试，不是切片数或研究指标。

Study 删除策略是**软删除、保留关联科研记录和文件**。Pending/Running Job 会阻断归档和删除；终态 Job、Result 与模型/实验版本均不级联清除，仍要求相应权限才能查阅。旧 Study 不出现在常规 Study 查询，其他保留记录可按 ID 审计追溯。当前不提供自动物理清理或恢复 API；未来清理必须单独定义保留期、审计和授权，不能复用本删除接口。

Pending Job 本身就是持久化队列记录，Worker 启动后轮询，不依赖易失内存队列。Worker 在事务内选择 Pending 项并以 ConcurrencyStamp 原子认领，写入 ClaimToken 与五分钟 Lease；相同任务不会被两个 Worker 成功认领。进程重启后 Pending 项继续执行，过期 Running 项转为失败并按最多三次策略重新入队。结果对象先按写入意图保存，随后在单一事务中同时验证 ClaimToken、插入唯一 Result、标记 Job 成功并移除意图。失败或取消后迟到的结果不能覆盖终态。若结果提交状态未知，保留对象交由补偿扫描器检查引用，避免危险的即时删除。

结果掩膜是 FastAPI 逆变换到原始 NIfTI 空间后的三维预测，返回对象键、SHA-256、模型/预处理版本、权重哈希、阈值、CorrelationId 和计时。没有 GT 时 Dice、IoU、Precision、Recall 保持 null；登记 GT、授权访问、评价、删除 GT 与下载预测分别受权限控制。评价必须通过 FastAPI 核对原始影像、标签和预测的形状、方向、spacing、affine、qform/sform 与标签集合；不匹配时拒绝，不做静默插值。GT 删除会清除相关评价值，并把不再引用的 GT 对象交给延迟补偿清理。

研究影像采用软删除并保留原始文件、任务、结果和历史模型。结果没有公开删除 API；服务端对象和推理服务 sidecar 在没有授权的独立保留/审计策略前不自动清除。孤立的 ABP 对象由 ObjectWriteIntent 补偿；FastAPI 预测对象按 requestId 确定性键支持安全重放，存放在独立推理数据卷，卷级备份和管理员清理属于部署运维职责，不能从用户输入构造文件路径。

### 上传到结果时序

```mermaid
sequenceDiagram
  actor User
  participant API as ABP Application API
  participant DB as PostgreSQL
  participant Store as IObjectStorage
  participant Worker as Persistent inference worker
  participant ML as FastAPI inference
  User->>API: multipart NIfTI upload
  API->>DB: persist ObjectWriteIntent
  API->>Store: stream object and SHA-256
  API->>API: bounded NIfTI type/header/size validation
  API->>DB: insert BrainStudy and remove intent in one UoW
  User->>API: create job + IdempotencyKey
  API->>DB: commit Pending job and model/input snapshot
  Worker->>DB: poll and atomically claim with ClaimToken/Lease
  Worker->>ML: POST /v1/segment, requestId=jobId-retryCount
  ML-->>Worker: prediction reference, hash, provenance and timings
  Worker->>ML: GET prediction by controlled object key
  ML-->>Worker: binary NIfTI stream + SHA-256 header
  Worker->>Store: stream object under generated key
  Worker->>DB: verify claim; insert result, mark success, remove intent
  User->>API: authorized result query/download
  User->>API: separately register GT, then request evaluation
  API->>ML: POST /v1/evaluate with stored references and CorrelationId
  ML-->>API: metrics + input/GT/prediction/model provenance
  API->>DB: validate provenance and persist evaluation
```

### Retry, error, and cleanup rules

| Condition | Behavior |
| --- | --- |
| Same requester + idempotency key + same study/model | Return existing Job; no duplicate queue item |
| Same idempotency key with changed study/model | 409 `BrainSeg:IdempotencyConflict` |
| Segment transport timeout/network fault or HTTP 408/429/502/503/504 | One explicit replay with same requestId, correlationId, input hash; FastAPI persists a receipt and deterministic prediction key |
| Evaluation/metadata validation failure | No metric update; stable mapped error; caller may retry after resolving cause |
| Circuit breaker open or inference dependency unavailable | 503 `BrainSeg:InferenceUnavailable`; no caller-supplied result can bypass Worker |
| Worker crash while Pending | Restarted worker rediscovers the database row |
| Worker crash while Running | Lease expiry invalidates old ClaimToken and schedules bounded retry |
| User cancels Running Job | Status becomes Cancelled immediately; remote work is best-effort/logically cancelled, late output is not persisted |
| Object write or DB result commit fails | Keep write intent; delayed reference check removes orphan or retains committed object; retries are idempotent |

Stable FastAPI codes are passed through `InferenceClientException` internally and mapped to ABP business codes; raw service bodies, file paths and stack traces are not returned. ABP writes JSON logs with JobId and CorrelationId only, never MRI bytes, access tokens or user filenames.

## 迁移与验证

迁移文件：[AddResearchDomain](../../apps/backend/src/BrainSeg.EntityFrameworkCore/Migrations/20261106041834_AddResearchDomain.cs)、[AddInferenceReliability](../../apps/backend/src/BrainSeg.EntityFrameworkCore/Migrations/20261126015421_AddInferenceReliability.cs)。运行根 README 的 `--migrate` 命令应用全部迁移，不使用 EnsureCreated 替代生产迁移。

本地关系测试使用真实 SQLite，测试认证和内存审计只存在于测试工程；生产授权、审计与 PostgreSQL provider 未被替换。专用 PostgreSQL 测试读取 `BRAINSEG_TEST_POSTGRES`，要求可创建临时数据库的隔离测试实例；每次仅创建/删除自身随机命名的 `brainseg_test_<guid>` 数据库，不删除传入连接的业务数据库。未配置时显示 Skip，CI 后端 job 会提供仅绑定 loopback 的临时 PostgreSQL，trust 认证仅用于该一次性 CI 容器，不能复制到生产配置。

AutoMapper 14 的递归 DoS 告警通过固定 15.1.4 修补，ABP 配置创建器已适配新构造函数，未关闭 NuGet 审计。开发/测试未配置许可证时的提示不屏蔽；生产许可通过 AutoMapper__LicenseKey 由部署环境提供。
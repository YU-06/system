# 系统与部署图

**免责声明：仅供本科毕业设计、科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

部署图对应 [基础 Compose 配置](../compose.yaml)；`compose.dev.yaml` 只是宿主机调试 overlay。

## 系统架构

```mermaid
flowchart LR
  Researcher[研究/教学用户浏览器] -->|HTTP local demo; production TLS required| Nginx[Angular static app / Nginx]
  Nginx -->|same-origin /api and /swagger proxy| ABP[ABP modular monolith]
  ABP --> Identity[Identity / OpenIddict / Permission Management]
  ABP --> Domain[Application + Domain services]
  Domain --> EF[EF Core]
  EF --> PostgreSQL[(PostgreSQL)]
  ABP -->|IObjectStorage| Storage[(Local files or MinIO / S3-compatible)]
  ABP -->|authenticated internal HTTP + CorrelationId| FastAPI[FastAPI inference]
  FastAPI --> ONNX[ONNX Runtime CPU]
  FastAPI --> Objects[(Inference receipt/prediction volume)]
  Training[Python + PyTorch training] --> Shared[Versioned flair-v1 preprocessing]
  FastAPI --> Shared
  Training --> Evidence[Hashed runs / freeze / paper reports]
```

## Compose 网络与持久化部署

```mermaid
flowchart TB
  Host[Host loopback only] -->|4200| Web[web / Nginx]
  Host -->|5000| Backend[backend / ABP]
  Host -->|9000 / 9001 loopback| MinIO[object-storage / MinIO API + console]
  Web -->|frontend bridge| Backend
  Backend --> Internal[backend-internal: internal network]
  Migrator[backend-migrate one-shot] --> Internal
  Internal --> PG[(postgres: postgres-data)]
  Internal --> MinIO
  Internal --> ML[ml-inference:8000; no host port]
  Backend --> BackendVolume[(backend-data)]
  MinIO --> MinioVolume[(object-data)]
  ML --> InferenceVolume[(inference-data)]
  Models[artifacts/models read-only] --> ML
```

Compose `healthcheck` is process liveness; `/ready` performs service/model readiness checks. Without real valid weights, ML and ABP `/ready` return 503 even if Compose reports containers healthy.

## Upload-to-result sequence

```mermaid
sequenceDiagram
  actor User
  participant Web as Angular / Nginx
  participant API as ABP Application API
  participant DB as PostgreSQL
  participant Store as IObjectStorage
  participant Worker as Persistent DB-polling worker
  participant ML as Internal FastAPI
  User->>Web: Upload complete NIfTI + request job
  Web->>API: Authenticated same-origin API request
  API->>DB: Persist object-write intent and pending Job
  API->>Store: Stream object, compute SHA-256
  Worker->>DB: Atomically claim Pending Job with lease
  Worker->>ML: POST /v1/segment with stable requestId
  ML-->>Worker: Prediction key, hash, model provenance and timings
  Worker->>ML: Fetch prediction by generated object key
  Worker->>Store: Save generated mask and preview objects
  Worker->>DB: Validate claim and write one result/terminal state
  User->>API: Authorized result query/download
  User->>API: Register GT and request separate evaluation
  API->>ML: POST /v1/evaluate with stored object references
  ML-->>API: Metrics + source/label/prediction hashes
  API->>DB: Validate provenance and store evaluation
```

## ER 图来源

正式 Mermaid ER 图（含五个聚合和对象写入意图）由[科研领域与 API 文档](api/research-domain.md)维护，以迁移和实体配置为准。本页不复制第二份 ER 源，避免两份图漂移。此链接不表示 PostgreSQL 容器已在本阶段启动或迁移。

# 部署、升级与恢复手册

**免责声明：仅供本科毕业设计、科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

本手册描述仓库内的本机 Compose 演示包，不代表已完成生产部署。不要把此配置直接暴露到公网或承载真实患者数据。

## 能力与证据边界

| 项目 | 当前状态 | 说明 |
| --- | --- | --- |
| Dockerfile、Compose 服务依赖、健康检查与持久卷 | 有实现；静态配置可检查 | 镜像构建和容器运行需要 Docker Engine/Compose |
| 数据库迁移入口 | 有实现 | `backend-migrate` 执行 EF Core `MigrateAsync`；本阶段未实测容器迁移 |
| 无模型时诊断 | 有实现 | 推理 `/health` 是进程存活；无有效研究模型时 `/ready` 返回 503 |
| 首位用户、OpenIddict 客户端与角色权限的 bootstrap | 未实现 / Blocked | 仓库没有默认管理员、默认密码、登录页或安全的一次性管理员引导 |
| TLS、生产密钥托管、最小权限 MinIO/S3 账号、备份恢复演练 | 仅有操作原则 | 不是生产就绪配置；未在隔离环境演练 |
| 模型导入 | 仅接受已经校验的研究 ONNX 清单与权重 | 仓库没有经验证的 PyTorch checkpoint → ONNX 导出流程；不得把 `.ckpt` 改名为 `.onnx` |

## 版本与前置条件

| 组件 | 仓库锁定/要求 |
| --- | --- |
| Docker Desktop 或 Docker Engine | Linux 容器；需启用 Compose v2，README 当前要求 Compose 2.20+ |
| .NET SDK | 由 `global.json` 固定为 10.0.400 |
| Node.js | 22.23.4（`.nvmrc`） |
| Python | 3.12.10（`.python-version`） |
| uv | 0.13.7（`pyproject.toml`） |
| PostgreSQL 容器 | `POSTGRES_IMAGE` 默认 `postgres:17-alpine` |
| 容器构建依赖 | 首次 build 需访问 NuGet、npm、PyPI、GHCR、MCR 与 MinIO 源码仓库 |

镜像标签不是 OCI digest；要做发布级供应链复现，应在发布记录中锁定各镜像的 `RepoDigest`，并在受控 runner 上验证构建。当前没有该 digest 清单，也没有镜像签名/漏洞扫描证据。

## Compose 网络、端口、健康检查和资源

在仓库根目录执行。基础 `compose.yaml` 仅发布 Web、ABP 和供本机开发者使用的 MinIO 端口，且都绑定 loopback。PostgreSQL 和 FastAPI 推理端口没有基础映射；`backend-internal` 是 Compose 的 internal network，承载数据库、MinIO API、推理服务和后端。Web/后端间通过 `frontend` 网络转发。

| 组件 | 宿主机端口 | 存活检查 | 容器上限 | 持久数据 |
| --- | --- | --- | --- | --- |
| Web / Nginx | `127.0.0.1:4200` | `/health` | 0.5 CPU / 256 MiB / 128 PIDs | 静态资源在镜像 |
| ABP Host | `127.0.0.1:5000` | `/health`（仅存活） | 1.5 CPU / 1 GiB / 256 PIDs | `backend-data`（本地对象存储切换时使用） |
| PostgreSQL | 无 | `pg_isready` | 1 CPU / 1 GiB / 256 PIDs | `postgres-data` |
| MinIO API / Console | `127.0.0.1:9000` / `:9001` | `/minio/health/live` | 1 CPU / 768 MiB / 256 PIDs | `object-data` |
| FastAPI 推理 | 无 | `/health`（仅存活） | 2 CPU / 4 GiB / 256 PIDs | `inference-data`；`artifacts/models` 只读挂载 |
| `backend-migrate` | 无 | 一次性进程，无 healthcheck | 1.5 CPU / 1 GiB / 256 PIDs | 复用后端环境 |

Compose `healthcheck` 用于判断进程/容器是否存活，不等同于模型就绪。`backend-migrate` 必须成功完成，后端才会启动；后端 `/ready` 检查 PostgreSQL、对象存储及 FastAPI `/health` 进程连接，并不要求模型已加载。没有研究模型时，推理 `/health` 仍应是 200，FastAPI `/ready` 是 503；后端 `/ready` 仍可能是 200，但实际分割请求会因模型未就绪失败。Compose `--wait` 成功也不代表有可推理模型。

所有容器使用 Docker `local` 日志驱动，单文件 10 MiB、最多 3 个文件；业务日志结构化且禁止记录 MRI 和令牌。容器 CPU/内存/PID 限额是本地默认值，低资源机器可在本地覆盖 Compose 文件；不要通过移除上传、推理或磁盘上限来“解决”资源不足。

Nginx 与 Kestrel 对请求体的限制分别是 64 MiB 和 64 MiB + 128 KiB multipart 开销；推理服务默认压缩文件 64 MiB、解压 NIfTI 128 MiB、16,777,216 voxels、每维 512、批次 16，配置上限由 [ML API 文档](api/ml-inference.md)说明。后端当前固定窗口限流为 Kestrel 看到的每个 `RemoteIpAddress` 每分钟 120 次、拒绝时返回 429、不排队。当前不配置可信代理转发；在反向代理后，多个用户可能共享代理 IP 的额度。生产环境必须设置可信代理链及代理侧限额，不可盲信任任意 `X-Forwarded-For`。

HTTPS 未在 Compose 终止。非本机部署必须由受控 TLS 反向代理终止 HTTPS，设置精确 `App__CorsOrigins`，限制管理端、上传和 OpenAPI 的网络可达性，并配置可信转发头、请求限额及服务间认证。当前 CORS 默认仅 localhost:4200；CORS 不是认证或网络隔离的替代品。

## 从零启动（PowerShell）

### 1. 获取依赖并生成本地密钥

```powershell
uv python install 3.12.10
uv sync --frozen
uv run --frozen python infra/scripts/init_env.py
```

`init_env.py` 仅在 `.env` 不存在时创建文件，生成彼此独立的随机 PostgreSQL、MinIO 和 FastAPI 服务间密钥，不打印它们，也不会覆盖已有配置。模板中的密码字段为空，Compose 会拒绝未初始化或空的必需密钥。不要手动复制 `.env.example` 后直接启动，不要把 `.env`、真实权重、MRI、证书或备份提交 Git。Windows 上还应使用仅当前开发者可读的目录 ACL；`chmod` 不应被当作 Windows ACL 配置。

`AutoMapper__LicenseKey` 可在本机 `.env` 配置；不需要的开发场景可留空。真实许可证必须按其许可条款使用，不能提交。

### 2. 安全检查配置并构建

```powershell
docker compose config --quiet
docker compose build
```

`--quiet` 仅校验 Compose，不把解析后的密钥打印到终端。不要运行会回显完整环境的 `docker compose config` 并把输出粘贴到日志或工单。

### 3. 启动并应用数据库迁移

一条命令启动基础栈（依赖健康检查及一次性迁移顺序由 Compose 管理）：

```powershell
docker compose up --build --wait --wait-timeout 240
```

如需单独观察迁移，可在 build 后分步执行；`up` 后端时 Compose 仍会确保命名迁移服务成功：

```powershell
docker compose build
docker compose up -d postgres object-storage ml-inference
docker compose run --rm backend-migrate
docker compose up -d --wait --wait-timeout 240 backend web
```

迁移由 `apps/backend/src/BrainSeg.HttpApi.Host/Program.cs` 的 `--migrate` 分支调用 EF Core `Database.MigrateAsync()`，不是 `EnsureCreated`。迁移异常时容器退出并阻止后端依赖启动；先查看只含错误诊断的日志，不要直接删 PostgreSQL 卷。

### 4. 检查存活、就绪与 API

```powershell
docker compose ps
Invoke-WebRequest http://127.0.0.1:4200/health
Invoke-WebRequest http://127.0.0.1:5000/health
Invoke-WebRequest http://127.0.0.1:5000/ready
Invoke-WebRequest http://127.0.0.1:5000/swagger/v1/swagger.json
```

没有有效研究 ONNX 权重时，FastAPI 模型就绪端点预期返回 503；基础 Compose 不公开该端口，可在容器内诊断：

```powershell
docker compose exec ml-inference python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready')"
```

无模型时上面的命令应以 HTTP 503 错误结束；该状态是预期的“模型未就绪”，不是服务已通过真实推理验证。后端 `/ready` 是基础依赖健康检查，不可替代 FastAPI `/ready`。可用 `docker compose exec ml-inference python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').status)"` 检查推理进程存活。OpenAPI 访问方式见 [API 索引](api/README.md)。

### 5. 导入模型和校验哈希

模型目录 `artifacts/models/` 被只读挂载至 `/models`。只允许已有、经研究流程验证的 ONNX 文件及配套 `model-manifest.yaml`，不能使用仓库中 `artifactKind: synthetic_test` 的示例清单。训练 checkpoint 是 PyTorch `.ckpt`，仓库目前没有已验证的 ONNX 导出脚本；没有合规 ONNX 产物时，不要伪造清单或宣称模型已导入。

若由独立、已审核流程提供了 ONNX 文件，将文件和 manifest 放入忽略目录，manifest 需声明实际 `weightFile`、`weightSha256`、版本、架构、`flair-v1`、256 输入尺寸、验证集冻结阈值及 `artifactKind: research`。Windows PowerShell 检查：

```powershell
(Get-FileHash .\artifacts\models\model.onnx -Algorithm SHA256).Hash.ToLowerInvariant()
docker compose up -d --force-recreate ml-inference
Invoke-WebRequest http://127.0.0.1:5000/ready
```

首行结果须与 YAML 中哈希完全一致。服务在加载时检查 manifest、权重 SHA-256、ONNX metadata 和模型协议；失败后 `/health` 保持诊断可用，`/ready` 为 503。Compose readiness 只有在模型就绪时才可作为完整服务验收依据。

### 6. 首位用户与权限初始化

仓库配置了 ABP Identity、OpenIddict 与 Permission Management 模块，也声明 `BrainSeg.*` 权限，但**没有**默认管理员、默认密码、OAuth 客户端 bootstrap、登录页面或一次性管理员创建工具。不得用 SQL 手工插入用户/权限或把测试账号用于部署。首次真实登录与权限授予必须由待补充的受控运维 bootstrap 流程完成，并把客户端密钥保存在密钥管理系统。该流程未实现、未验证，是当前功能验收的 Blocked 项；在完成之前，不宣称完整用户主流程可部署验收。

### 7. 日志、故障诊断和停止

```powershell
docker compose logs --tail 200 backend backend-migrate ml-inference postgres object-storage
docker compose logs --follow backend ml-inference
docker compose stop web backend
docker compose down
```

`down` 保留命名数据卷；`down --volumes` 会不可逆删除本地 PostgreSQL、对象存储、推理收据和后端本地存储数据，只能在确认无保留需要后用于演示重置。不要使用 `docker volume prune` 清理仍有研究/测试证据的卷。

### 常见故障

| 现象 | 检查方式 | 处理边界 |
| --- | --- | --- |
| `docker` 命令不存在 | `docker --version` | 安装并启动 Docker Desktop/Linux Engine；此时 Compose 不能验证 |
| 缺少必需环境变量 | `docker compose config --quiet` | 运行 `uv run --frozen python infra/scripts/init_env.py`；不把解析后的配置输出 |
| PostgreSQL unhealthy / 迁移失败 | `docker compose logs postgres backend-migrate` | 检查磁盘、凭据和 migration 日志；先备份，禁止删 volume 作为通用修复 |
| Web/API 可访问但推理失败 | 检查 `backend /ready`，在内部检查 `ml-inference /health` 与 `/ready` | ML `/health`=200 且 `/ready`=503 表示无有效模型/权重；检查 manifest 及 SHA-256 |
| 413 上传超限 | 对照 Nginx、Kestrel、ML 三层限制 | 只按批准的研究数据上限统一配置，不能移除解压/体素限制 |
| 429 请求过频 | 检查 Kestrel 限流与反向代理客户端 IP 传递 | 不使用伪造 `X-Forwarded-For`；正确配置可信代理或降低请求速率 |
| MinIO/对象读写失败 | `docker compose logs object-storage backend` | 检查 bucket、端点和密钥是否一致；不要将 root secret 写入命令历史 |
| Compose 显示 healthy 但业务不可用 | 检查 `/ready`、迁移任务、模型版本及用户授权 | 容器 health 不证明登录、权限、研究模型或完整主流程通过 |

## 本地存储、MinIO 与 S3 兼容存储

- **本地文件**：应用开发配置 `ObjectStorage__Provider=Local` 和 `ObjectStorage__RootPath=data/objects`；本机开发时目录位于被忽略的 `data/`。若让 Compose 后端使用本地实现，必须先将其配置为 Local，并确认 `backend-data:/app/data` 持久化卷已保留。
- **MinIO（当前 Compose 默认）**：`ObjectStorage__Provider=Minio`、`ObjectStorage__Endpoint=http://object-storage:9000`、bucket 与 MinIO 凭据均由 Compose 注入。MinIO 首次写入会创建 bucket。API 端口仅映射到 loopback 以支持本机工具，容器互访走内部网络。
- **S3 兼容端点**：后端已有 MinIO SDK 适配器，使用 `ObjectStorage__Endpoint` 的 scheme/host/port、bucket 与 access/secret credentials；需按提供商配置 HTTPS 和专用最小权限账号。不要把云密钥放进仓库 `.env.example`。当前 Compose 专为本地 MinIO 配置，使用外部 S3 前必须由部署者覆盖 endpoint/凭据，并移除本地 MinIO 依赖和映射；仓库没有完成 S3 厂商联调或 IAM 策略验证。

## 升级、备份与回滚

以下是运维方案，不是已演练的恢复承诺。当前无备份自动化和恢复演练，所有恢复步骤状态均为 **未验证**。

### 升级前检查与备份

1. 在隔离环境先跑当前 CI、Compose config/build/启动、迁移和主流程；记录 Git commit、镜像 RepoDigest、数据库 migration 名称、模型 manifest/权重哈希与对象存储快照标识。
2. 暂停新任务提交；等待任务进入终态。若不能等待，应记录所有 Running Job，停止 Worker 后再升级；服务端逻辑取消不表示远端推理立即终止。
3. 备份 PostgreSQL 自洽快照。示例在数据库容器内写自定义格式，再通过 `docker compose cp` 取回，避免 PowerShell 文本重定向破坏二进制：

```powershell
New-Item -ItemType Directory -Force .\backups
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/brainseg.dump'
docker compose cp postgres:/tmp/brainseg.dump .\backups\brainseg.dump
```

4. 通过已审核的 S3/MinIO 客户端按版本对 `brainseg` bucket 做完整对象镜像，并保存对象 key/哈希清单；同时备份 `inference-data`（幂等 receipt 和 prediction）、`backend-data`（若用 Local）以及 `artifacts/models`。对象存储在线复制要核对一致性；需要严格快照时先暂停写入并使用存储层快照。备份包含敏感研究文件，必须加密、限权并设置保留期。
5. 确认备份可读、记录大小/哈希与位置，不要把备份放进 Git 或公共 CI artifacts。

在隔离副本验证 PostgreSQL dump 的示例（不要恢复到当前演示数据库）：

```powershell
docker compose exec -T postgres createdb -U brainseg brainseg_restore_check
docker compose cp .\backups\brainseg.dump postgres:/tmp/brainseg-restore-check.dump
docker compose exec -T postgres pg_restore -U brainseg -d brainseg_restore_check /tmp/brainseg-restore-check.dump
docker compose exec -T postgres psql -U brainseg -d brainseg_restore_check -c "select count(*) from public.""BrainStudies"";"
```

上面 `brainseg` 用户/数据库仅对应 `.env.example` 的本地默认值；若有不同名称，应使用本地配置中的值，不能将命令直接移植到生产。验证库的清理、角色映射、对象文件对齐还需单独确认。本步骤当前未执行。

### 应用升级

```powershell
docker compose stop web backend
docker compose build
docker compose run --rm backend-migrate
docker compose up -d --force-recreate backend web ml-inference
docker compose ps
Invoke-WebRequest http://127.0.0.1:5000/health
Invoke-WebRequest http://127.0.0.1:5000/ready
```

上线前还需核验版本兼容迁移、模型 ready、对象读写与授权主流程。EF Core migration 的自动 `Down` 不作为本项目的回滚方案；不要在数据已写入后盲目降级 schema。

### 验证恢复与回滚

先在隔离副本/临时环境恢复 PostgreSQL dump，再恢复对应时间点的对象存储和模型 manifest/权重，验证迁移版本、关键实体行数、对象哈希、引用关系、`/health` 与 `/ready`、受权下载及合成 smoke。不得将恢复副本连接至真实数据或正式测试流程。

若升级失败，停止新版本 API/Worker，保留失败日志与任务状态；从升级前一致性快照恢复数据库与全部相关对象，并部署原 Git commit 和记录的镜像 digest。数据库回滚同时恢复对应 MinIO、FastAPI receipt/prediction、Local volume 和模型 manifest，不能仅恢复数据库或只恢复权重。若无法证明数据库与对象存储同一时点，应保持服务停止并标记 Blocked，不能人工补写成功结果。

上述备份、隔离恢复、跨版本迁移及回滚目前均未在本机或 CI 演练。真实恢复前必须补充受控演练和可审计结果。

### 模型版本切换与任务状态

ABP `ModelVersion` 登记和 FastAPI 单一启动 manifest 是两套状态；不得假定更改 ABP 默认模型会自动切换 Python 进程。切换前停止新任务并等待现存 Pending/Running Job 处理完，保留旧 manifest、ONNX、哈希和容器日志；验证新研究权重哈希、metadata、threshold 与 ABP 模型快照一致后，再按权限启停/设默认并重建推理服务。检查 `/ready`、`/models` 和实际模型版本，再恢复任务入口。失败时恢复旧 manifest、旧权重与旧服务版本。运行任务的历史快照不能被新 manifest 覆盖。

这里没有真实模型切换或待处理任务升级演练；真实结果为 NotRun。

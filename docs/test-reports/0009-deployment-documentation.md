# 阶段九：部署文档与科研复现证据

**免责声明：仅供本科毕业设计、科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

日期：2026-11-26  
目标分支：`chore/phase-9-deployment-documentation`  
代码基线：`798b727`（本阶段修改尚未提交）  
运行环境：Windows x64、.NET SDK 10.0.400、Node v26.13.1、uv 0.13.7、Python 3.12.10。Docker CLI/Compose 未安装；无 PostgreSQL 容器、真实 BraTS 数据或真实研究权重。

阶段八前置状态依据[阶段八质量门禁报告](0008-system-quality-gates.md)：软件套件结果与 PostgreSQL、Docker、真实研究数据、模型和 GPU 的 Blocked/NotRun 项分别记录。本阶段不把阶段八 fixture 通过解释为系统部署通过。

## 需求 → 证据 → 状态

| 需求 | 来源/验证 | 状态 | 说明 |
| --- | --- | --- | --- |
| Dockerfile、服务依赖、健康检查、网络和持久卷文档 | `compose.yaml`、四个 Dockerfile、[部署手册](../deployment.md)、[部署图](../diagrams.md) | Pass（代码/文档检查） | Dockerfile 已含非 root 用户与健康检查；本阶段新增网络、资源限制及限端口声明 |
| 配置模板没有可用默认密码 | `.env.example`、`init_env.py`、`test_environment_initialization_generates_secrets_without_overwriting` | Pass（测试 fixture） | 初始化行为测试不证明 Windows ACL 或密钥管理系统配置 |
| Postgres/ML 默认无宿主机端口；本地 overlay loopback | `compose.yaml`、`compose.dev.yaml`、`test_compose_has_real_dependencies_health_checks_and_no_unused_redis`、`test_host_development_port_overrides_are_loopback_only` | Pass（PyYAML 静态配置） | 没有执行 Docker Compose schema 校验 |
| 迁移、就绪、故障排除与停止手册 | [部署手册](../deployment.md) | Pass（文档方案） | 容器迁移/健康流程未执行；无模型时 FastAPI `/ready` 应为 503 |
| 首位用户、客户端和权限初始化 | [部署手册 §6](../deployment.md) | Blocked | 仓库无安全 bootstrap、默认管理员或登录 UI；文档没有虚构账号或 SQL 步骤 |
| Local/MinIO/S3 兼容切换说明 | [部署手册](../deployment.md)、`IObjectStorage` 与现有 MinIO adapter | Pass（代码路径与文档） | S3 厂商、TLS、IAM 未联调 |
| 备份、升级、恢复、模型切换 | [部署手册](../deployment.md) | NotRun | 操作步骤已写；恢复、迁移回滚和模型切换均未演练 |
| 训练、验证冻结、测试与报表复现 | [复现手册](../reproducibility.md)、实验协议 ADR | Pass（命令/协议文档） | BraTS 数据、完整六组权重和测试结果缺失 |
| 论文证据索引、图表与数据来源 | [复现手册 §论文证据索引](../reproducibility.md) | Pass（索引模板） | 真实成绩、图表、截图及正文页码均 NotRun |
| OpenAPI、架构/部署/时序/ER 图 | [API 索引](../api/README.md)、[系统图](../diagrams.md)、[领域 API/ER](../api/research-domain.md) | Pass（文档链接/契约核对） | 未启动服务生成或下载运行时 schema |
| `docker compose config/build/up/migrate/health/main flow` | `docker --version` | Blocked | Docker 未安装，相关容器命令未执行 |
| 真实模型推理、页面截图、性能/临床结果 | 无研究权重/数据/运行环境 | NotRun | 未生成假图、模拟趋势或研究结论 |

## 本地实际命令和结果

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `docker --version` | 1 | PowerShell 找不到 `docker`；Compose CLI/Engine 不可用 |
| `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q tests\test_infrastructure.py`（首轮） | 1 | 6 passed、2 failed：CI 静态断言仍禁止 schema 命令中的内部容器地址；阶段九报告文件尚未创建，免责声明测试无法读取。随后修复断言并增加本报告，失败证据保留 |
| `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q tests\test_infrastructure.py`（修复后） | 0 | 8 passed |
| `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q`（首轮全量） | 1 | 88 passed、1 failed：测试发现敏感 `backups/` 未在 `.dockerignore` 排除；已补充规则，失败证据保留 |
| `.tools\uv\uv.exe run --frozen --extra training --extra reports pytest -q`（最终） | 0 | 89 passed、0 failed；1 条 Starlette/httpx 弃用警告 |
| `.tools\uv\uv.exe run --frozen ruff format --check .` | 0 | 74 个 Python 文件已格式化 |
| `.tools\uv\uv.exe run --frozen ruff check .` | 0 | All checks passed |
| `git diff --check` | 0 | 无 whitespace errors |
| Inline Python Markdown-link check over `README.md` and `docs/**/*.md` | 0 | 0 个失效的本地 Markdown 链接 |
| `dotnet --version` | 0 | 10.0.400 |
| `node --version` | 0 | v26.13.1；与项目 `.nvmrc` 的 Node 22.23.4 不同，本阶段未运行前端构建 |
| `docker compose config --quiet` / build / clean startup / DB migration / health | NotRun | Docker 缺失，不能以 YAML parsing 代替 Compose 验证 |
| PostgreSQL/MinIO 主流程、备份恢复和模型切换 | NotRun | 无容器与研究模型；未启动外部部署 |

测试替身只覆盖配置与初始化代码，不能视为容器启动、数据库迁移或服务间联调。

## 明确的证据缺口

- 用户身份初始化与授权角色分配当前无受控 bootstrap；外部开发者不能仅靠仓库文档完成首次登录。
- Compose 引用的是版本 tag，尚未形成 OCI RepoDigest/签名/漏洞扫描清单；跨时间的 byte-identical 镜像重现未证明。
- 无真实 ONNX 权重与验证阈值；无 ONNX 导出流程；FastAPI model `/ready` 预期未就绪。
- Postgres、MinIO、S3、OpenAPI 运行时 schema、Docker volume 与完整上传—推理—结果主流程未实测。
- HTTPS 终止、可信 Forwarded Headers、代理侧 rate limit、S3 最小权限、备份一致性和回滚恢复演练缺失。
- 无研究数据和权重；真实训练/测试成绩、性能结果和论文病例图均为 `NotRun`。没有产生部署或科研系统截图。

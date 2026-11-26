# ADR 0008：部署文档、内部网络与复现边界

**免责声明：仅供本科毕业设计、科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

- **状态：** Accepted with deployment blockers
- **日期：** 2026-11-26

## 决策

1. 基础 Compose 只对 loopback 发布 Web、ABP 和本机 MinIO 管理/API 端口。PostgreSQL 与 FastAPI 推理没有宿主机端口；数据库、对象存储和推理服务位于 `backend-internal` internal network。
2. 使用明确命名卷保留 PostgreSQL、MinIO、推理幂等 receipt/预测对象和可选本地后端对象。容器设置 CPU、内存、PID 和日志轮转上限。Compose healthcheck 表示进程/依赖存活；`/ready` 单独表示业务就绪。
3. `compose.dev.yaml` 仅供宿主机进程调试，显式把 Postgres/ML 端口绑定到 `127.0.0.1`。它不改变基础 Compose，也不能用于公网部署。
4. `.env.example` 不提供可用密码；初始化脚本生成独立随机本地密钥。所有密钥、真实权重、MRI、备份及证书都必须留在 Git 外。
5. 本地 MinIO 是 Compose 默认；Local 文件系统由 `IObjectStorage` 配置选择；MinIO SDK adapter 可连接 S3 兼容 endpoint，但具体云厂商/IAM 尚未集成验证。
6. 升级文档要求数据库和对象卷同一时间点备份、隔离恢复验证、迁移前停止写入与模型历史保留。未演练的恢复步骤不得宣称已验证。
7. 复现流程和论文证据索引只记录真实产物 hash、运行标识、统计参数和正文位置；无真实数据、模型或运行时只保留 `NotRun`。

## 后果和未完成项

- 当前 Compose 是本机 HTTP 开发配置，不提供 TLS、生产 secret manager、最小权限 S3 账号、可用身份 bootstrap、备份自动化或 HA。
- 仓库没有初始管理员/OpenIddict client 创建流程，也没有已验证的 `.ckpt` 到 ONNX 导出工具。
- Postgres/MinIO/S3/模型切换/恢复及正式流程尚无本阶段实测证据。容器版本 tag 尚未统一锁定到 OCI digest。

## 验证

实现及运行记录见[阶段九部署与科研复现测试报告](../test-reports/0009-deployment-documentation.md)。本 ADR 接受文档和静态配置，不把 Docker 缺失时的 Compose 文件读取等同于容器验证。

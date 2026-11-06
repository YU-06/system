# 科研领域实现验证

日期：2026-11-06。仅供科研与教学演示，非医疗器械，不用于临床诊断。

## 已执行的针对性检查

| 检查 | 结果 | 证据范围 |
| --- | --- | --- |
| 五个聚合与 Job 状态机 | 通过 | 非法转换、UTC、单调进度、重试上限、模型默认约束、结果空指标与制品校验 |
| AutoMapper、权限发现、中文资源 | 2 项通过 | 真正从 ABP 容器解析服务并读取嵌入 JSON；不是仅检查类型存在 |
| SQLite 关系约束及并发 | 12 项通过 | 文件/切片、模型身份/默认、Job 幂等、唯一结果、实验身份、FK、软删及真实双上下文冲突 |
| 权限矩阵与分层依赖 | 11 项通过 | 只读用户拒绝十类写命令；Domain/Contracts/Application 无逆向引用 |
| 上传和跨实体 HTTP 工作流 | 10 项通过 | multipart、真实 SHA-256、拒绝坏文件、审计无文件内容、幂等、409、删除保留及完成失败无部分提交 |
| PostgreSQL 迁移生成/快照 | 通过 | AddResearchDomain 已生成，模型无 pending changes |
| 新领域全量回归首次执行 | 74 通过、4 跳过 | 随后又补充了文件/事务边界测试，最终计数待下面门禁更新 |

上传和工作流使用合成 NIfTI 与标记为 NotRun 的合成制品；不代表已完成真实模型推理、BraTS 实验、患者级指标或临床验证。

## 最终门禁

| 门禁 | 最终实际结果 |
| --- | --- |
| `dotnet restore --locked-mode` | 通过，所有新增依赖已固定到锁文件 |
| 完整方案 Release 构建 | 通过，8 个工程，未报告编译或 NuGet 安全告警 |
| `dotnet format --verify-no-changes --no-restore` | 通过 |
| 完整方案 `dotnet test` / TRX | **79 通过、4 跳过、0 失败**，本次实际执行 |
| EF `has-pending-model-changes` | 通过，快照与当前模型一致 |
| PostgreSQL 新增迁移幂等 SQL 生成 | 通过，确认五张表、七个唯一索引和四条 RESTRICT 外键；未连接业务数据库 |
| 仓库 Python / 基础设施回归 | 24 通过，包含更新后的 CI、Compose、环境模板；1 条既有 httpx 弃用警告 |

PostgreSQL 迁移文件为 `20261106041834_AddResearchDomain`。真实 PostgreSQL 应用迁移、原生索引与并发测试在本机**未执行**，不能用生成 SQL 或 SQLite 测试替代。

PostgreSQL 专用测试本机未执行：没有 BRAINSEG_TEST_POSTGRES；xUnit 显式记录 4 项定义跳过，其中参数化约束测试在有环境时会展开。CI 已配置隔离 PostgreSQL 并复用相同约束/并发断言，但远程工作流未触发，不能声称 CI 已通过。

AutoMapper 15.1.4 无许可证开发/测试会给出运行时许可警告，允许本地开发测试的提示未屏蔽；生产需要适当许可。Python 的既有 httpx 弃用提示与真实训练/GPU、Docker/MinIO 集成仍按骨架报告单独记录，不与本阶段测试混算。

`research.http` 已提供各 API 的认证请求示例，制品键、哈希、耗时、面积和阈值读取实际环境值；未使用真实访问令牌手工执行这些示例。API 行为由真实 TestServer HTTP 集成测试验证，测试认证和内存审计只注入测试工程，不对生产开放。
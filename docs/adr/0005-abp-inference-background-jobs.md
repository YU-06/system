# ADR 0005：ABP 持久化后台推理任务

状态：Accepted  
适用范围：内部科研与教学演示，BraTS 2020 T2-FLAIR Whole Tumor 二分类

**免责声明：仅供科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

## 决策

分割 Job 先作为 ABP 持久化领域记录提交，再由 Host 中的数据库轮询 Worker 派发；不依赖易失内存队列。Worker 在事务中按请求时间选择 Pending 项，以 EF 并发戳、随机 ClaimToken 和五分钟 Lease 认领。进程恢复后 Pending 项重新可见，过期 Running 项失效并按 Job 重试上限重新入队。结果提交时必须再次验证 ClaimToken，并在同一数据库 Unit of Work 中写入唯一结果、置 Job 为 Succeeded、移除对象写入意图。

完整 NIfTI 先由服务端校验并流式写入 `IObjectStorage`，同时计算 SHA-256。每个新对象写入前登记 `ObjectWriteIntent`；数据库提交成功后移除意图。结果写入或数据库提交状态未知时不立即删除对象，由延迟补偿 Worker 检查数据库引用后再清理未引用对象，删除失败时退避重试。

强类型 `IMlInferenceClient` 集中处理服务地址、服务间 Bearer 认证、超时、稳定错误映射和 CorrelationId。Segment 调用带确定性 requestId（Job ID + 重试次数），只有可安全重放的同一请求才执行一次显式重试；通用 HTTP resilience 不自动重放非幂等请求。FastAPI 以 requestId 和输入哈希实现安全重放，输入哈希不同则返回幂等冲突。评价不会被当作新的预测请求重试。

客户端只能创建、查询、筛选、取消和重试 Job；开始、失败、完成、进度及结果均由 Worker 管理。取消 Running Job 是逻辑取消：立即使 ClaimToken 失效，远端计算可能继续，迟到响应不能覆盖终态。上传、GT 和预测下载、GT 评价及删除分别经过服务端权限检查；FastAPI 只接受内部服务认证及受控对象引用，不保存用户或权限数据。

对象和研究记录默认保留。Study 软删除不级联清理文件或结果；孤立的 ABP 对象由写入意图补偿。FastAPI 预测对象使用确定性 requestId 键并保留在服务数据卷，自动到期清理暂不启用，避免破坏重放追踪；备份和管理员清理属于部署运维职责。

## 后果与限制

- Job 表同时是工作队列和恢复来源；多 Worker 安全依赖数据库并发控制，不依赖进程内锁。
- Lease 为五分钟。超过 Lease 的慢请求可能被再次调度；稳定 requestId 让同一 attempt 的重放保持幂等。
- 服务间密钥必须经部署环境分别注入 ABP 和 FastAPI。密钥缺失时推理、评价与预测下载 fail-closed。
- 当前没有生产 PostgreSQL/MinIO 联调和真实模型权重；SQLite/合成服务替身测试只证明对应的契约与代码路径，不代表全链路部署或研究表现。
- 进程重启恢复、并发 Worker 争抢、远端超时后的真实重放，以及数据库提交结果未知后的补偿仍需专门的集成/故障注入验收。

上传到结果的时序、状态机、错误映射、重试、逻辑取消和保留规则见 [科研领域与 API 文档](../api/research-domain.md)。实际执行范围和未完成验收见 [阶段六测试报告](../test-reports/0006-abp-inference-background-jobs.md)。

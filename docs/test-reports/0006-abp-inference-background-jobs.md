# 阶段六：ABP 后台推理任务

日期：2026-11-26

**免责声明：仅供科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

## 验收范围

- 完整 NIfTI 上传、服务端对象键与 SHA-256、幂等 Job 创建和授权查询/命令。
- 持久化 Pending 队列、ClaimToken/Lease、模型与输入来源快照、结果写入意图及补偿策略。
- 强类型 FastAPI 客户端的服务间认证、CorrelationId、稳定错误映射和同 requestId 安全重放。
- 预测产物哈希校验、结果落库、GT 单独登记与评价，以及逻辑取消后的迟到响应保护。

## 执行结果

- 后端 `BrainSeg.Tests`：**76 passed、4 skipped、0 failed**。
- 全仓 Python pytest：**83 passed、0 failed**。
- Ruff 仓库级 lint：通过；仓库级格式检查：61 个文件已格式化。
- 后端解决方案 `dotnet format` 格式验证：通过。
- `git diff --check`：通过；Git 对部分 LF/CRLF 文件给出工作区换行提醒，无空白错误。
- pytest 唯一警告为 Starlette 对当前 `httpx` TestClient 集成的弃用提示，未屏蔽。

## 覆盖与真实性边界

- 后端测试覆盖领域状态、幂等接口、权限、并发戳、对象存储及禁止调用方伪造终态/预测结果；四项 PostgreSQL 专项测试因未配置隔离 `BRAINSEG_TEST_POSTGRES` 而跳过。
- Python 服务测试覆盖上传、哈希/对象完整性、请求重放和丢失 receipt 后的 sidecar 恢复；新增篡改 prediction hash、requestId 或 input hash 时拒绝重放的断言。
- FastAPI 服务契约测试使用显式合成 predictor，不是已训练模型；合成结果不会作为研究权重或论文指标。
- 当前测试没有实际运行完整 ABP Worker + FastAPI + PostgreSQL/MinIO 的服务集成，也未对两个并行 Worker、进程重启租约恢复、结果提交故障注入和补偿清理做端到端验收。这些是剩余验收项，不能由单元测试或接口契约测试替代。
- 仓库没有可用真实研究权重；未执行真实权重推理、正式测试集评价、完整训练或临床工作流。研究结果保持 `NotRun`。
- Docker/Compose、真实 PostgreSQL 迁移及 MinIO 联调未执行。

## 命令记录

| 命令 | 结果 |
| --- | --- |
| `dotnet test apps\backend\tests\BrainSeg.Tests\BrainSeg.Tests.csproj --no-restore --logger "console;verbosity=minimal"` | 76 passed、4 skipped、0 failed |
| `$env:PYTHONPATH="services\ml-inference;ml"; .venv\Scripts\python.exe -m pytest -q` | 83 passed、0 failed |
| `.venv\Scripts\python.exe -m ruff check services\ml-inference\brainseg_inference\app.py services\ml-inference\brainseg_inference\storage.py services\ml-inference\tests\test_service.py` | All checks passed |
| `.venv\Scripts\python.exe -m ruff format --check services\ml-inference\brainseg_inference\app.py services\ml-inference\brainseg_inference\storage.py services\ml-inference\tests\test_service.py` | 3 files already formatted |
| `.venv\Scripts\python.exe -m ruff check .` | All checks passed |
| `.venv\Scripts\python.exe -m ruff format --check .` | 61 files already formatted |
| `dotnet format apps\backend\BrainSeg.slnx --verify-no-changes --no-restore` | 通过 |
| `git diff --check` | 通过；有换行风格提示 |
| Docker/Compose、真实 PostgreSQL/MinIO、真实模型推理、完整训练和正式测试集评价 | 未执行 |

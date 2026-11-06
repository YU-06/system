# 工程骨架验证记录

日期：2026-11-06。仅供科研与教学演示，非医疗器械，不用于临床诊断。

## 验证环境

Windows；.NET SDK 10.0.400；Node 22.23.4；Python 3.12.10；uv 0.13.7。系统 Node 19 不满足 Angular 要求，因此使用忽略目录中的独立 Node；Python 同样为用户空间安装。浏览器测试使用已安装的 Edge 156，与 CI 默认的 Playwright Chromium 分开记录。没有安装 Docker CLI/引擎。

## 已执行结果

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| ABP 初始 restore/build | 通过 | 七层模块真实恢复与编译 |
| 后端 xUnit / ABP Host | 12 通过，0 失败 | 存活、依赖失败 503、UTC、科研范围、Swagger、401、关联 ID、存储哈希/路径/限额 |
| EF 初始迁移生成 | 通过 | 官方 EF 工具生成迁移及模型快照 |
| EF pending model changes | 通过 | 快照与当前模型一致；不等于已连接真实 PostgreSQL |
| NuGet use-lock-file / locked-mode restore | 通过 | 所有项目锁文件已生成，严格恢复通过 |
| 后端完整 Release 构建与格式门禁 | 通过 | 8 个工程构建成功，`dotnet format --verify-no-changes` 成功 |
| 官方 ABP Angular 代理生成 | 通过 | 读取真实运行 Host，重复生成并生产构建成功 |
| npm ci | 通过 | Node 22 配套 npm 可从锁文件干净恢复，无 peer 告警 |
| npm audit | 0 项漏洞 | 定向修补后结果；不等于镜像安全扫描 |
| Angular lint | 通过 | 严格类型与模板规则 |
| 全前端 TypeScript 检查 | 通过 | 应用、单元测试、E2E、Playwright 配置均通过 `tsc --noEmit` |
| 前端 Prettier 格式门禁 | 通过 | 包含源码、配置、代理生成器和 E2E |
| Angular 单元测试 | 7 通过，0 失败 | loading/empty/error/success、重试、并发刷新抑制 |
| Angular 生产构建 | 通过 | 最终初始资源 346.11 kB，预算内 |
| Playwright 桌面/移动 | 2 通过，0 失败 | 状态刷新/错误恢复、标题、免责声明、图片加载、312px 无横向溢出、小屏图标隐藏、无未预期控制台错误 |
| 推理/训练协议 pytest | 18 通过，0 失败 | 合成 NIfTI/ONNX；文件、哈希、超时、标签、预处理、患者划分、种子、指标与日志边界 |
| 基础设施 pytest | 6 通过，0 失败 | `.env` 不覆写、随机密钥、Compose/CI/Dockerfile 结构与免责声明；不是容器运行 |
| 全仓 pytest | 24 通过，0 失败 | 1 条依赖弃用警告，见下文 |
| Python Ruff 全仓格式与 lint | 通过 | `ruff format --check`、`ruff check` 通过 |
| 真实前后端页面联通 | 通过 | 浏览器显示后端服务已连接；桌面与窄屏截图已人工核对 |
| 真实后端/Python 关联 ID 传播 | 通过 | 后端 `/ready` 调用 Python `/health`，两个服务保留同一 `smoke-correlated-001`，Python JSON 日志已核对 |
| 编辑器诊断 | 通过 | 最终工作区无诊断错误 |

Starlette 当前对 `httpx` 测试客户端发出 1 条弃用警告，建议后续迁移至其 `httpx2` 适配；未屏蔽警告，没有将警告误报为零。测试正常通过，运行服务不使用该测试客户端。

## 同日再次复核

2026-11-06 本轮重新执行了严格 NuGet 恢复、8 个工程的 Release 构建、12 项 xUnit/VSTest、后端格式与迁移快照检查；全部通过，并生成新的 TRX。

前端重新执行 `npm ci`、lint、7 项单元测试、完整 TypeScript 检查、生产构建、Prettier 和 2 项桌面/移动 Edge E2E；全部通过，npm 审计为 0 项漏洞，生产初始资源仍为 346.11 kB。Python 重新执行全仓 Ruff lint、格式检查和 pytest，24 项通过，仍保留上述 1 条弃用警告。

本轮未发现需要修改业务实现的失败。再次检查确认 Docker CLI、Docker Desktop 和引擎管道均不存在，因此没有尝试管理员提权安装；Docker build、Compose、真实 PostgreSQL/MinIO 联调和 GitHub Actions 远程运行仍为未执行。此前记录的真实进程健康与关联日志结果不视为本轮 Docker 验收证据。

## 最终门禁与未执行项

最终应用构建、格式、类型、lint 和回归已完成。以下结果明确区分可验证的应用行为与当前环境无法执行的集成/研究工作。

| 检查 | 当前状态 | 原因 |
| --- | --- | --- |
| 全仓格式门禁与最终回归 | 通过 | .NET 12、Angular 7、Python 24、浏览器 2 项，均实际执行 |
| 后端 `/health`、推理 `/health` | 200，符合预期 | 两个真实进程存活，不要求虚构模型或数据库连接 |
| 后端 `/ready` | 503，符合预期 | 数据库未启动；本地对象存储与 Python 健康项为 Healthy |
| 推理 `/ready` | 503，符合预期 | `MODEL_NOT_CONFIGURED`；没有真实模型权重 |
| Docker build / Compose config / up | 未执行 | 本机无 Docker CLI 和运行中的守护进程 |
| 真实 PostgreSQL 迁移与 MinIO 读写 | 未执行 | 无容器环境；仅生成/校验迁移与存储本地测试 |
| GitHub Actions 远程运行 | 未执行 | 未推送或触发远程工作流 |
| 正式训练、真实权重推理、患者级评估 | 未执行 | 本阶段仅骨架；没有提供数据/权重，实验为 NotRun |
| GPU/CUDA 与 1/5/10 并发性能 | 未执行 | 未配置 GPU/CUDA，也未进行性能实验 |

## 修复记录

- 修复 ABP 10 模块命名空间和缺失 Serilog 宿主依赖。
- 动态请求本地化会访问数据库，改为固定中文/英文文化，使 `/health` 不被数据库故障阻断；静态权限/设置定义不在迁移前写数据库。
- 修复 Swagger 对 ABP 分组控制器的收录，防止代理生成缺少应用服务。
- 固定加密库修补版本；Angular 升级到安全修补线，补充 ABP 验证库和 Node 类型，消除 npm 安全/peer 告警。
- 浏览器测试发现 ABP 初始配置跳过后 locale 未定义，显式设置中文 locale，并将控制台错误纳入回归断言。
- 使用 ABP 标题策略的公开 DI 令牌去除默认 `MyProjectName`，标题加入 E2E 断言。
- 窄屏截图发现页面最小宽度和图标宿主默认样式挤压状态栏，解除最小宽度并提高响应式样式精度，加入 312px 与图标隐藏回归。
- 统一 ABP、Python 和 Nginx 的 `CorrelationId` 日志字段；反向代理校验/生成关联 ID，真实后端到 Python 的传播已验证。
- MinIO 历史镜像不能确认匿名拉取，改为固定官方源码提交构建；未将 metadata 验证当作 Docker 构建成功。

pytest 使用的是合成数据；合成模型的 Dice=1 是测试断言，不是 BraTS 实验结果。没有删除测试集困难样本、生成伪造患者清单或报告虚构研究指标。
# ADR 索引

**免责声明：仅供本科毕业设计、科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

| 编号 | 决策 | 状态 |
| --- | --- | --- |
| [0001](0001-skeleton.md) | 可构建科研工程骨架与分层结构 | Accepted |
| [0002](0002-research-domain.md) | BrainStudy / Job / Result 等领域模型 | Accepted |
| [0003](0003-experiment-protocol.md) | BraTS 配对实验、验证冻结与评价协议 | Accepted |
| [0004](0004-fastapi-inference-service.md) | FastAPI NIfTI 推理与模型清单 | Accepted |
| [0005](0005-abp-inference-background-jobs.md) | ABP 持久任务、幂等与恢复 | Accepted |
| [0006](0006-angular-research-ui.md) | Angular 科研工作台和查看器 | Accepted |
| [0007](0007-system-quality-gates.md) | 系统质量门禁与受控性能测试 | Accepted |
| [0008](0008-deployment-documentation.md) | 可复现部署文档、私有网络与证据限制 | Accepted with deployment blockers |
| [0010](0010-2p5d-boundary-uncertainty.md) | 2.5D 跨切片注意力、边界深监督与不确定性产物 | Accepted |

ADR 记录设计选择，不等同于实现或运行证明；各阶段实际命令和 `Pass` / `Fail` / `Blocked` / `NotRun` 状态应以对应测试报告为准。

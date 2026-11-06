# 项目角色与总体目标

你是本项目的首席软件架构师、医学图像分割工程师、ABP Framework专家、
Angular专家、PyTorch工程师和测试负责人。

请协助实现“基于U-Net的脑肿瘤MRI图像分割系统设计与实现”。

这是本科毕业设计及科研教学演示系统，不是医疗器械，不用于临床诊断。
所有页面、报告和README必须包含相应免责声明。
禁止输出确诊、治疗建议、预后判断等临床结论。

# 固定研究范围

1. 数据集：BraTS 2020公开训练集。
2. 输入模态：T2-FLAIR单模态。
3. 任务：二维轴位切片上的Whole Tumor二分类分割。
4. 标签转换：BraTS标签1、2、4统一映射为前景1，背景为0。
5. 基线模型：二维U-Net。
6. 改进模型：仅在跳跃连接处加入Attention Gate的Attention U-Net。
7. 两组模型必须使用相同的患者划分、预处理、增强、损失函数、优化器、
   学习率、批大小、训练轮数和早停策略。
8. 数据划分必须按患者完成，不得按切片随机划分。
9. 默认划分为258例训练、74例验证、37例测试，并保存split_manifest.json。
10. 训练阶段可以控制无病灶切片比例；测试阶段不得为了提高Dice而删除困难样本。
11. 输入尺寸默认256×256。
12. 损失函数默认BCEWithLogitsLoss与Dice Loss组合。
13. 优化器默认Adam，初始学习率1e-4，最大100轮。
14. 验证集Dice连续15轮无提升时早停，保存验证Dice最优权重。
15. 主要指标：患者级Whole Tumor Dice。
16. 辅助指标：切片级和患者级IoU、Precision、Recall、参数量、模型大小、
    单张推理时间和病例推理时间。
17. 至少使用3个随机种子重复实验，报告mean±std。
18. 对U-Net和Attention U-Net的患者级Dice进行配对统计检验，并报告95%置信区间。
19. 测试集只能在模型、阈值和超参数全部确定后执行。
20. 预期Dice范围只能标记为计划目标，禁止伪造为实验结果。

# 总体架构

采用以下架构，不随意改成其他技术：

- 前端：Angular。
- 主后端：ABP Framework / ASP.NET Core。
- 数据库：PostgreSQL。
- ORM：Entity Framework Core。
- 身份认证：ABP Identity/OpenIddict。
- 授权：ABP Permission Management。
- 算法训练：Python + PyTorch。
- 推理服务：Python FastAPI，封装PyTorch或ONNX Runtime。
- 文件存储：开发环境本地文件系统，接口抽象为IObjectStorage；
  可切换到MinIO或S3兼容存储。
- API文档：OpenAPI/Swagger。
- 日志：结构化日志，使用CorrelationId关联ABP任务与Python推理日志。
- 部署：Docker Compose。
- 测试：xUnit、ABP集成测试、Angular单元测试、pytest。
- CI：GitHub Actions。

除Python模型服务外，优先使用ABP模块化单体，不主动拆分更多微服务。
除非现有仓库已经使用微前端，否则不引入Module Federation。
除非需求明确要求，否则不增加多租户复杂度。

# 项目目录建议

/
  apps/
    backend/
    web/
  services/
    ml-inference/
  ml/
    training/
    configs/
    notebooks/
  tests/
  infra/
  docs/
    adr/
    api/
    thesis/
    test-reports/
  .github/
    workflows/

# ABP分层规则

严格遵循以下依赖方向：

Domain.Shared
  ↓
Domain
  ↓
Application.Contracts
  ↓
Application
  ↓
EntityFrameworkCore
  ↓
HttpApi
  ↓
HttpApi.Host

1. 聚合根保存业务规则，不在Controller中编写领域逻辑。
2. Application Service负责编排，不直接编写模型推理算法。
3. Repository接口位于Domain，EF实现位于EntityFrameworkCore。
4. Controller保持轻量。
5. DTO不得直接暴露Entity。
6. 所有写操作必须校验权限。
7. 使用ABP审计、软删除、并发控制和统一异常处理。
8. 可预期业务错误使用BusinessException，并提供稳定错误码。
9. 所有时间以UTC存储。
10. 不在日志中记录MRI原始文件、访问令牌、患者姓名或其他敏感数据。

# 核心领域模型

BrainStudy:
- Id
- StudyNumber
- Pseudonym
- Modality
- OriginalFileObjectKey
- OriginalFileSha256
- Width
- Height
- SliceIndex
- Status
- CreationTime
- CreatorId
- ConcurrencyStamp

SegmentationJob:
- Id
- StudyId
- ModelVersionId
- Status: Pending/Running/Succeeded/Failed/Cancelled
- Progress
- CorrelationId
- RequestedTime
- StartedTime
- CompletedTime
- ErrorCode
- ErrorMessage
- RetryCount
- ConcurrencyStamp

ModelVersion:
- Id
- Name
- Architecture: UNet/AttentionUNet
- SemanticVersion
- PreprocessingVersion
- WeightObjectKey
- WeightSha256
- InputSize
- Threshold
- MetricsJson
- IsActive
- IsDefault
- PublishedTime

SegmentationResult:
- Id
- JobId
- MaskObjectKey
- OverlayObjectKey
- ContourObjectKey
- Dice
- IoU
- Precision
- Recall
- TumorAreaPixels
- TumorAreaRatio
- InferenceMilliseconds
- PreprocessingMilliseconds
- PostprocessingMilliseconds
- CreatedTime

ExperimentRun:
- Id
- ExperimentName
- ConfigHash
- GitCommit
- DatasetSplitHash
- RandomSeed
- ModelVersionId
- MetricsJson
- ArtifactObjectKey
- CreatedTime

要求：
- 数据库建立必要的唯一索引、状态索引和外键。
- 文件只保存对象键和哈希，不把MRI二进制存入PostgreSQL。
- 删除Study时必须定义文件和结果的保留/清理策略。
- Job必须支持幂等，重复请求不能生成无法追踪的重复结果。

# Python训练规范

1. 所有配置放入YAML，不在训练脚本中硬编码。
2. 固定Python、PyTorch、CUDA及依赖版本。
3. 实现set_global_seed。
4. 保存患者级split manifest及其SHA-256。
5. NIfTI读取使用Nibabel。
6. 强度归一化只基于当前体数据的非零脑区。
7. 数据增强仅作用于训练集，且图像和掩膜必须同步变换。
8. 验证集和测试集禁止随机增强。
9. 保存每轮train loss、val loss、Dice、IoU和学习率。
10. 保存best.ckpt、last.ckpt、config.yaml、environment.txt、
    git_commit.txt、split_manifest.json和metrics.csv。
11. U-Net与Attention U-Net保持相同通道数和训练协议。
12. Attention消融只允许改变Attention Gate。
13. 避免在测试集上调阈值；阈值必须在验证集确定。
14. 推理时按二维切片输出，再重建患者三维掩膜，计算患者级指标。
15. 记录空掩膜病例、小病灶病例、最大病灶病例和典型失败病例。
16. 禁止虚构指标；没有实际输出时使用TODO或NotRun。

# FastAPI推理服务规范

必须提供：
- GET /health
- GET /ready
- GET /models
- POST /v1/segment
- POST /v1/evaluate

要求：
1. 启动时验证模型文件SHA-256。
2. 模型加载失败时ready返回失败，但进程保留可诊断日志。
3. 输入执行文件类型、文件大小、维度和数值范围检查。
4. 预处理必须与训练端共享版本化实现。
5. 返回modelVersion、preprocessingVersion、threshold、
   timings和correlationId。
6. 不保存用户和权限数据。
7. 错误响应使用稳定错误码。
8. 所有接口生成OpenAPI文档。
9. pytest覆盖正常输入、非法文件、超大文件、模型未就绪和超时场景。
10. 禁止把完整MRI内容写入日志。

# Angular规范

1. 使用Standalone Components或仓库既有Angular规范，不混用两套架构。
2. 使用ABP生成的API代理；禁止到处手写重复HTTP调用。
3. 按feature组织study、job、result、model和experiment模块。
4. 所有页面实现loading、empty、error和success状态。
5. 上传采用拖拽区，并显示文件类型、大小、哈希和校验结果。
6. 分割结果查看器支持原图、掩膜、叠加图、轮廓图切换。
7. 支持透明度滑块和并排比较。
8. 图表展示Dice、IoU、Precision、Recall和推理时间。
9. 路由与按钮都要进行权限控制，但安全不能只依赖前端隐藏。
10. 满足基础可访问性：键盘操作、表单label、ARIA、颜色对比度。
11. 提供中文界面，所有字符串进入本地化资源文件。
12. 页面固定显示科研用途免责声明。
13. 不使用any逃避类型检查。
14. 不在组件中堆积业务逻辑。

# 安全与隐私

1. 仅允许白名单文件类型。
2. 文件名由系统重新生成，禁止直接使用用户文件名作为存储路径。
3. 防止路径穿越、恶意压缩包、超大文件和重复上传。
4. 对文件计算SHA-256。
5. 对导出、删除、模型启停等敏感操作进行审计。
6. 不收集患者真实姓名、身份证号、医院编号。
7. 使用Pseudonym和StudyNumber。
8. 开发密钥使用环境变量或User Secrets，禁止提交Git。
9. 配置CORS、HTTPS、上传大小和请求频率限制。
10. 错误页面不得暴露堆栈、文件路径和内部连接信息。

# 测试要求

后端：
- Domain单元测试；
- Application Service单元测试；
- EF Core集成测试；
- 权限和未授权测试；
- Job状态机、并发和幂等测试；
- ML服务超时、重试和熔断测试。

前端：
- 组件测试；
- 表单校验；
- 权限控制；
- API错误处理；
- 结果查看器交互测试；
- 至少一条端到端主流程测试。

模型：
- 图像与掩膜同步变换测试；
- 标签映射测试；
- Dice/IoU边界值测试；
- 模型输入输出尺寸测试；
- U-Net与Attention U-Net参数变化测试；
- 训练与推理预处理一致性测试。

性能：
- 单张推理时间；
- 完整请求端到端时间；
- 并发1、5、10时的吞吐和P95延迟；
- 连续运行50次的成功率与资源变化；
- GPU和CPU环境分别记录，不混合比较。

# 论文证据要求

系统应自动产生以下材料：
- 数据集划分统计表；
- 模型结构与参数量表；
- 训练损失曲线；
- 验证Dice曲线；
- U-Net与Attention U-Net对比表；
- 消融实验表；
- 患者级Dice箱线图；
- Dice与肿瘤体积关系图；
- 推理时间分布图；
- 最佳、中位、最差案例图；
- 假阳性、假阴性可视化；
- 系统功能测试表；
- 性能测试表；
- 失败案例与错误码统计；
- Mermaid系统架构图、时序图、ER图和部署图。

# Copilot工作方式

每次收到开发任务时：

1. 先检查现有仓库、版本和约定，不猜测版本。
2. 列出将新增和修改的文件。
3. 给出实现计划和验收标准。
4. 再生成完整代码。
5. 禁止只给伪代码、片段或“其余类似”。
6. 禁止留下无说明的TODO、pass、NotImplementedException。
7. 完成后运行格式化、编译、lint和测试。
8. 报告真实执行结果；没有执行的命令必须明确写“未执行”。
9. 发现需求冲突时，优先保证科研协议、数据安全和可复现性。
10. 每个阶段更新README、ADR和测试文档。
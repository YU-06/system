# ADR 0004：FastAPI 全体积推理服务

状态：Accepted  
适用范围：内部科研演示服务，BraTS 2020 T2-FLAIR Whole Tumor 二分类

**免责声明：仅供科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

## 决策

沿用现有 FastAPI、Nibabel、共享 `flair-v1` 预处理和经过测试的 ONNX Runtime CPU 加载路径。未添加新的推理后端。模型从部署控制的 YAML manifest 加载；manifest 与权重位于同一受控目录，权重字段仅允许 basename。进程启动时校验 manifest schema、权重 SHA-256、模型版本、U-Net 架构、预处理版本、256 输入尺寸、阈值及 ONNX 自定义元数据。元数据必须准确声明 `brainseg.architecture`、`brainseg.preprocessing_version`、`brainseg.input_size`、`brainseg.threshold`。任何缺项或不符均保持进程存活但令 `/ready` 返回 503。`artifactKind` 不是 `research` 时拒绝模型就绪；测试替身只在测试代码中注入并在响应/预测 sidecar 中标记 `synthetic_test`。

`/health` 只表示进程存活；`/ready` 表示模型完整校验并可推理；`/models` 返回单一已验证模型。`/v1/segment` 接收完整 NIfTI，要求轴 2 的方向码为 `S` 或 `I` 且 affine-derived spacing 与 header zoom 一致；按训练轴位切片和相同插值规则做预处理、有限批次推理、阈值化，并将掩膜逆缩放到原数组尺寸。服务不自动重定向、不对空间元数据不一致的输入猜测变换。输出 NIfTI 保留输入 affine、qform/sform 与空间单位，以随机服务对象键写入本地 `IObjectStorage` 等价适配边界（当前实现为本地对象存储），返回对象键及 SHA-256，不返回无 GT 的准确性指标。

`/v1/evaluate` 使用已生成的受控预测对象键、原始影像和 GT。它校验哈希、原数组尺寸、方向、spacing、affine、qform/sform、空间单位和 BraTS 标签集合；空间不一致时返回错误而不插值。指标包括患者全体素口径与切片宏平均；空掩膜遵循训练端指标定义。

上传和解压后大小、维度、voxel 数、有限值和强度范围均受限。模型前向通过单工作线程和信号量限制并发，并对队列等待加前向计算实施 deadline。请求路径只接受上传内容或服务生成的对象键，不从用户提供路径/URL读取文件。上传原始 MRI 不持久化；日志不记录影像或令牌。Compose 仅将服务端口绑定到 loopback，并将生成的预测持久化到独立命名卷。此服务不保存用户或权限数据；非本地部署必须继续由内部网络与既有服务间认证策略保护。

## 计时边界

- 预处理：共享体数据归一化和每张二维切片缩放。
- 推理：仅 ONNX `session.run` 每批耗时之和，不含推理队列等待。
- 后处理：sigmoid、阈值、逆缩放、NIfTI 编码、哈希和预测对象持久化。
- 推理 deadline：等待推理槽位与所有纯前向批次；不将超时工作报告为成功。

## 后果

模型缺失或权重校验失败时仍可读取健康诊断端点，且不会加载未校验/合成权重。多模态、非 256 输入或非 `flair-v1` 权重必须先有独立版本化协议，不能通过运行时猜测或静默 resize 兼容。当前仓库不包含真实研究权重；未执行真实权重推理或任何临床工作流。

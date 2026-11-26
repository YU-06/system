# 科研复现与论文证据索引

**免责声明：仅供本科毕业设计、科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

本文是受控实验操作流程，不包含虚构实验结果。当前仓库没有 BraTS 原始影像或真实研究权重；真实训练、正式测试和论文指标均为 `NotRun`。

## 数据获取与使用限制

使用 BraTS 2020 官方渠道取得的公开训练数据，并遵循当期数据访问、许可、引用和再分发限制。仓库不携带 MRI、患者清单、权重或数据库导出。不得向 Git、一般 CI artifacts、公共图床或未经批准的第三方服务上传原始数据。仅使用去标识化患者标识；文件名/目录名不能作为真实身份依据。

预期输入是每个患者的完整 T2-FLAIR NIfTI 与其模态/标签配对文件，目录结构由 `ml/training/scan_dataset.py` 实际解析；先按 CLI 扫描输出检查完整度、几何和模态，再运行划分。正式协议为患者级 **258 train / 74 validation / 37 test**，患者不可跨 split。标签 `1,2,4` 合并为 Whole Tumor 前景，输入为 256×256 二维轴位切片。

## 环境和复现命令

从仓库根目录，使用已锁定的 Python 3.12.10、uv 0.13.7 与 `uv.lock`：

```powershell
uv python install 3.12.10
uv sync --frozen --extra training --extra reports
uv run --frozen --extra training python -m training validate-config --config ml/configs/baseline.yaml
uv run --frozen --extra training python -m training scan --root data/brats2020 --output artifacts/dataset_scan.json
uv run --frozen --extra training python -m training split --scan artifacts/dataset_scan.json --output artifacts/split_manifest.json
uv run --frozen --extra training python -m training preprocess --root data/brats2020 --split artifacts/split_manifest.json --output artifacts/preprocessed
```

检查真实 scan 的患者数、扫描器摘要及 hash 后再训练；命令拒绝错误患者数或无效空间资料。生成并保存 `artifacts/split_manifest.json` 及 sidecar，不手工编辑，不按切片重新抽样。

训练配置来自 `ml/configs/experiment_protocol.yaml` 与 `ml/configs/baseline.yaml`。U-Net / Attention U-Net 使用相同预处理、增强、损失、优化器、学习率、batch size、轮数、早停与患者 split；Gate 是唯一结构消融。按种子 17、42、2024 成对运行。正式训练示例（每个命令单独运行并保留输出）：

```powershell
uv run --frozen --extra training python -m training train --config ml/configs/baseline.yaml --architecture UNet --seed 17
uv run --frozen --extra training python -m training train --config ml/configs/baseline.yaml --architecture AttentionUNet --seed 17
uv run --frozen --extra training python -m training train --config ml/configs/baseline.yaml --architecture UNet --seed 42
uv run --frozen --extra training python -m training train --config ml/configs/baseline.yaml --architecture AttentionUNet --seed 42
uv run --frozen --extra training python -m training train --config ml/configs/baseline.yaml --architecture UNet --seed 2024
uv run --frozen --extra training python -m training train --config ml/configs/baseline.yaml --architecture AttentionUNet --seed 2024
```

训练记录写入 `artifacts/runs/<architecture>/seed_<seed>/`，包括配置、日志、last/best checkpoint、环境、Git commit 与 split 来源。当前默认 CPU；GPU 结果不可与 CPU 混报。不得为缩短训练改动其中一个模型的超参数后仍称配对实验。

## 验证选模、阈值冻结与正式测试

只用验证集完成模型选择和阈值规则。每组训练后按验证集三维重建后的患者级 Dice 完成验证冻结：

```powershell
uv run --frozen --extra training python -m training validate --config ml/configs/baseline.yaml --checkpoint artifacts/runs/UNet/seed_17/best.ckpt --output artifacts/runs/UNet/seed_17/validation.json --freeze artifacts/runs/UNet/seed_17/protocol_frozen.json
```

上述命令需对六组模型/种子分别执行。默认主分析搜索阈值 0.30–0.70、步长 0.05，按预注册并列规则选择；固定 0.50 敏感性分析用 `validate.py --selection-mode fixed_050` 建立独立冻结和结果目录。核对验证报告后才可执行测试：

固定 0.50 的精确命令是在相应 seed 的验证命令上增加参数 `--selection-mode fixed_050`，例如：

```powershell
uv run --frozen --extra training python -m training validate --config ml/configs/baseline.yaml --checkpoint artifacts/runs/UNet/seed_17/best.ckpt --output artifacts/runs/UNet/seed_17/validation-fixed-050.json --freeze artifacts/runs/UNet/seed_17/protocol-fixed-050.json --selection-mode fixed_050
```

该敏感性结果必须使用独立冻结和输出目录，不能与主分析结果混合。每次正式运行前记录 `git rev-parse HEAD`，对实验 protocol、baseline config、split manifest、冻结 sidecar、权重/checkpoint 和生成图表分别计算 SHA-256；训练程序会把关键来源和 hash 写入运行目录。

```powershell
uv run --frozen --extra training python -m training test --config ml/configs/baseline.yaml --checkpoint artifacts/runs/UNet/seed_17/best.ckpt --freeze artifacts/runs/UNet/seed_17/protocol_frozen.json --output artifacts/runs/UNet/seed_17/test
```

对六组分别执行并保留原始输出。测试 CLI 会核对冻结 sidecar、Git commit、配置/split/cache/checkpoint/模型权重 hash、验证报告 hash、种子、模型、阈值来源和指标；校验失败时不应手工修补冻结记录。测试一旦打开，不得再调模型、阈值或超参数。无真实完整配对产物时，不运行或不发布结果表。

## 统计、图表与证据保存

主要分析为患者级 Whole Tumor Dice；切片级、患者宏平均和 pooled 口径、空掩膜规则、三种子患者内汇总、Wilcoxon 零差值处理与患者对 bootstrap 均见 [实验协议 ADR](adr/0003-experiment-protocol.md)。所有结论必须保留数据源 SHA-256、运行 ID、Git commit、配置与协议 hash、split hash、模型版本/权重 hash、预处理版本、阈值冻结来源、统计参数及报表脚本版本。

仅在所有真实运行与测试患者配对齐全后生成正式论文表图：

```powershell
uv run --frozen --extra reports python -m training.generate_reports --runs artifacts/runs --split artifacts/split_manifest.json --cache artifacts/preprocessed/index.json --output artifacts/paper-reports
```

固定 0.50 敏感性报告使用独立输出目录并加 `--threshold-mode fixed_050`。物理病灶体积仅在 NIfTI 空间单位、affine 与 spacing 均可信时使用；否则报告 voxel。合成 fixture 仅验证报表代码，不得作为研究图、趋势或病例示例。

报表产物与运行证据放在受控的 `artifacts/`，不得覆盖既有运行；复制到论文前保存哈希及索引。当前没有真实结果图。不得截图合成页面或容器状态后标记为部署/临床证据。

## 论文证据索引

“正文位置”为计划章节而非已写入论文的位置。来源记录和图表不存在时保持 `NotRun`，不能根据预期构造图表。

| 结论/待证明项 | 来源文件或运行记录 | 对应图表/文件 | 论文正文位置（计划） | 核验状态 |
| --- | --- | --- | --- | --- |
| 数据集纳入、258/74/37 患者 split | `scan_dataset.json`、`split_manifest.json` 及 SHA-256 | 划分统计表 | 数据与方法 | NotRun：无本地数据 |
| U-Net / Attention U-Net 参数量和权重文件大小 | 六个研究 run 的模型结构与权重 SHA-256 | 模型结构/参数量表 | 方法与实验设置 | NotRun：无研究权重 |
| 训练损失和验证 Dice 变化 | 每个 run 的 `metrics.csv`、run ID、配置 hash | 训练/验证曲线 | 实验结果 | NotRun：未训练 |
| 患者级对比、Gate 消融和统计差值 | 冻结测试结果、配对患者统计 JSON | 对比/消融表、Dice 分布图、差值 CI | 实验结果 | NotRun：未执行正式测试 |
| 病灶体积与 Dice 关系 | 标签、空间单位和患者级结果来源 hash | 体积关系图 | 误差与分层分析 | NotRun：无可信真实标签 |
| 推理速度与成功率 | 真实权重性能 JSON、硬件/时钟/运行环境 | 时延分布、性能表 | 系统实现与评估 | NotRun：无研究权重/输入 |
| 最佳/中位/最差病例、FP/FN 与失败案例 | 报表 manifest、冻结测试患者排序和病例来源 | 病例网格、FP/FN 可视化 | 误差分析 | NotRun：不能生成假病例 |
| 系统功能、错误码和测试通过状态 | 阶段 8/9 测试报告、CI run URL/ID | 测试矩阵与错误统计 | 系统测试 | 部分：本地 fixture 通过；真实 Compose/CI 未验证 |
| 部署架构、迁移与恢复能力 | [阶段九测试报告](test-reports/0009-deployment-documentation.md) 与运维演练记录 | 部署/架构/时序/ER 图 | 系统设计与测试 | 部分：文档/静态检查；实部署和恢复未验证 |

本索引随每次真实实验更新：不得只贴图；每张图都需记录输入产物哈希、运行 ID、筛选规则、单位、统计参数、脚本版本、输出哈希及论文页码/小节。此索引不产生任何实验结果。

# 训练协议骨架

仅供科研与教学演示，非医疗器械，不用于临床诊断。

本目录实现了 BraTS 2020 公共训练集的扫描、患者级划分、flair-v1 预处理缓存、二维轴位数据集、同步增强、二维 U-Net、Attention U-Net、组合损失、训练/验证/测试、全患者三维重建、断点恢复和验证阈值冻结。推理直接复用 `flair-v1` 的标签映射、归一化和尺寸变换。

从仓库根目录运行：

```powershell
uv sync --frozen
uv run --frozen --extra training python -m training validate-config
uv run --frozen --extra training python -m training scan --root data/brats2020 --output artifacts/dataset_scan.json
uv run --frozen --extra training python -m training split --scan artifacts/dataset_scan.json --output artifacts/split_manifest.json
uv run --frozen --extra training python -m training preprocess --root data/brats2020 --split artifacts/split_manifest.json --output artifacts/preprocessed
uv run --frozen --extra training python -m training train --config ml/configs/baseline.yaml
uv run --frozen --extra training python -m training validate --config ml/configs/baseline.yaml --checkpoint artifacts/runs/<architecture>/seed_<seed>/best.ckpt --output artifacts/runs/<architecture>/seed_<seed>/validation.json --freeze artifacts/runs/<architecture>/seed_<seed>/protocol_frozen.json
uv run --frozen --extra training python -m training test --config ml/configs/baseline.yaml --checkpoint artifacts/runs/<architecture>/seed_<seed>/best.ckpt --freeze artifacts/runs/<architecture>/seed_<seed>/protocol_frozen.json --output artifacts/runs/<architecture>/seed_<seed>/test
uv run --frozen --extra reports python -m training.generate_reports --runs artifacts/runs --split artifacts/split_manifest.json --cache artifacts/preprocessed/index.json --output artifacts/paper-reports
uv run --frozen --extra training python -m training smoke --config ml/configs/smoke.yaml --output artifacts/smoke/current
uv run --frozen --extra training pytest ml/training/tests
```

正式数据扫描直接读取数据集目录，不需要手工维护患者 ID 数组。正式 scan/split 固定要求 369 个完整且几何一致的患者，输出 258 个训练、74 个验证和 37 个测试患者，并生成清单及 SHA-256。排序后再按固定种子打乱，因此输入排列不影响分组，不进行切片级随机划分。

实验协议以 `ml/configs/experiment_protocol.yaml` 为版本化来源，执行配置为 `ml/configs/baseline.yaml`。U-Net 与 Attention U-Net 按 17、42、2024 配对；自动一致性检查仅允许架构、Attention Gate 开关和运行 ID 不同。验证集在三维重建后按患者宏平均 WT Dice 搜索 0.30–0.70（步长 0.05），并列依次选择更接近 0.50、再选择较低阈值。可用 `--selection-mode fixed_050` 执行预先声明的 0.50 敏感性分析。测试执行要求匹配且完整的冻结记录。

运行正式训练不会自动删除测试集切片，也不会在测试集选择阈值。冻结记录绑定 Git commit、协议/配置/划分/缓存/检查点/权重哈希、模型与预处理版本、种子、验证报告和阈值选择证据。测试入口会验证候选阈值及其验证集患者级 Dice，并拒绝缺项或不匹配的记录。

患者级统计先在每个患者内汇总三种子，再作模型间配对；Wilcoxon 为双侧检验，零差值按 `wilcox` 排除并报告数量。95% CI 通过患者对 bootstrap 计算。切片与重复种子不是独立患者。空真值与空预测的 Dice/IoU/Precision/Recall 为 1；恰有一方为空时均为 0。报表脚本只从完整、哈希匹配的真实研究产物生成论文表图；合成数据或不完整真实数据仅生成模板和 `NotRun` 清单。

真实数据验证就绪后可执行：

```powershell
uv run --frozen --extra reports python -m training.generate_reports --runs artifacts/runs --split artifacts/split_manifest.json --cache artifacts/preprocessed/index.json --output artifacts/paper-reports
```

报表包括患者划分统计、模型参数与文件大小、训练/验证曲线、模型及 Gate 消融对比、患者级 Dice 分布、病灶规模关系、推理计时、预先排序的最佳/中位/最差病例和 FP/FN 可视化。图表来源清单记录运行、权重/冻结/测试报告哈希、协议与划分哈希、参数、单位和脚本版本。只有空间单位、qform/sform 与 affine/spacing 一致时才报告 mm³，否则使用 voxel。表图生成命令不启动训练或测试。

敏感性分析必须使用独立的固定 0.50 验证冻结和六组测试产物，并在报表命令增加 `--threshold-mode fixed_050`、指定独立输出目录；不得将其与主分析搜索阈值的结果合并。

本阶段没有真实 BraTS 权重、正式三种子结果或患者级论文指标；真实 Dice/IoU/Precision/Recall 固定标记为 `NotRun`。合成 smoke 不用于论文，也不生成上述真实指标。可选训练依赖通过 `uv sync --frozen --extra training` 安装，固定 CPU PyTorch 2.15.0；CUDA/GPU 未执行。

研究协议的统计口径、冻结规则和验收结果见 [阶段四实验协议 ADR](../../docs/adr/0003-experiment-protocol.md) 与 [阶段四测试报告](../../docs/test-reports/0004-experiment-protocol.md)。所有真实实验结果及失败案例须来自实际产物；未实际获得时使用 `NotRun`，不得补成示例成绩。
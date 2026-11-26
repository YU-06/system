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
uv run --frozen --extra training python -m training smoke --config ml/configs/smoke.yaml --output artifacts/smoke/current
uv run --frozen --extra training pytest ml/training/tests
```

正式数据扫描直接读取数据集目录，不需要手工维护患者 ID 数组。正式 scan/split 固定要求 369 个完整且几何一致的患者，输出 258 个训练、74 个验证和 37 个测试患者，并生成清单及 SHA-256。排序后再按固定种子打乱，因此输入排列不影响分组，不进行切片级随机划分。

默认协议来自 `ml/configs/baseline.yaml`，U-Net 和 Attention U-Net 共用一份配置，只有 Attention Gate 架构差异。三个实验种子为 42、2024、3407。阈值来源限定为验证集，测试执行状态保持锁定。

运行正式训练不会自动删除测试集切片，也不会在测试集选择阈值。验证集只用于阈值选择和协议冻结；测试入口要求相同配置、split/cache 哈希、验证报告哈希和已冻结最优阈值。

训练产物包含 `best.ckpt`、`last.ckpt`、逐轮 `metrics.csv`、配置、环境、Git 提交、患者划分哈希、切片选择和状态。断点校验架构、种子、配置、split/cache 哈希、优化器和 RNG；不受控恢复会被拒绝。

本阶段没有真实 BraTS 权重、正式三种子结果或患者级论文指标；真实 Dice/IoU/Precision/Recall 固定标记为 `NotRun`。合成 smoke 不用于论文，也不生成上述真实指标。可选训练依赖通过 `uv sync --frozen --extra training` 安装，固定 CPU PyTorch 2.15.0；CUDA/GPU 未执行。

完整三种子实验必须归档验证阈值、最优/最后权重、逐轮指标、患者级结果、配对统计、置信区间和失败案例；这些证据没有实际获得时不能补成示例成绩。
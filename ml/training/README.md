# 训练协议骨架

仅供科研与教学演示，非医疗器械，不用于临床诊断。

本目录已经实现配置校验、可复现患者级划分、全局种子工具、Whole Tumor 标签映射、非零脑区标准化、二维输入变换和指标边界处理。推理直接导入同一版本的预处理代码。

从仓库根目录运行：

```powershell
uv sync --frozen
uv run --frozen python -m training validate-config
uv run --frozen python -m training split --patients data/patient_ids.json --output artifacts/split_manifest.json
uv run --frozen pytest ml/training/tests
```

划分输入是实际 BraTS 2020 数据中 369 个不同的去标识化患者 ID 的 JSON 数组。输出固定为 258 个训练患者、74 个验证患者和 37 个测试患者，并生成清单 SHA-256。排序后再按固定种子打乱，因此输入排列不影响结果，不进行切片级随机划分。

默认协议来自 `ml/configs/baseline.yaml`，U-Net 和 Attention U-Net 共用一份配置，只有 Attention Gate 架构差异。三个实验种子为 42、2024、3407。阈值来源限定为验证集，测试执行状态保持锁定。

本阶段没有训练入口、已训练权重、正式患者级三维评估或实验曲线；结果状态为 `NotRun`，不输出计划 Dice 作为实际结果。可选训练依赖通过 `uv sync --frozen --extra training` 安装，固定 PyTorch 2.15.0；当前只配置 CPU 协议，CUDA/GPU 实验未配置、未执行。安装训练依赖后 `set_global_seed` 才会同时固定 PyTorch 状态，未安装时给出明确错误。

后续训练阶段必须归档最佳/最后检查点、实际配置、环境、Git 提交、患者划分及哈希和逐轮指标，完成至少三种子和患者级配对统计后才能形成论文实验结论。
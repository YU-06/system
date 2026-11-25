# BraTS 2020 训练实现验证

日期：2026-11-25。仅供科研与教学演示，非医疗器械，不用于临床诊断。

## 已交付实现

- `ml/training/scan_dataset.py`：检查 FLAIR/seg 成对存在、NIfTI-1、三维形状、仿射、轴向方向、有限值、标签和源 SHA-256。
- `ml/training/create_split.py`：按固定种子生成患者级 258/74/37 研究划分；合成模式只允许显式小人数。
- `ml/training/preprocess.py`：缓存每个患者的每个轴位切片、WT mask、原始形状、非零脑区归一化结果和完整性哈希。
- `ml/training/datasets/brats2d.py`：训练集可控空片比例；验证/测试集保留全部切片，无随机增强。
- `ml/training/transforms.py`：图像和掩膜同步翻转/旋转。
- `ml/training/models/unet.py` 与 `attention_unet.py`：相同通道协议，Attention UNet 仅增加跳跃 Gate。
- `ml/training/losses.py`：BCEWithLogitsLoss 与 Dice Loss；`metrics.py` 提供切片及患者级二分类指标。
- `train.py`、`validate.py`、`test.py`：固定设备、种子、批大小、损失、Adam、最大学习轮数、15 轮早停、最优权重、断点恢复与测试冻结。
- `reconstruct_volume.py`：要求每个患者全部切片存在后恢复三维 WT，并支持与参考仿射一起保存 NIfTI。

## 实际合成 smoke

顶层命令执行：

```powershell
uv run --frozen --extra training python -m training smoke --config ml/configs/smoke.yaml --output artifacts/smoke/final
```

实际结果：

- 状态：`SmokePassed`
- 数据：仅合成 NIfTI，未使用 BraTS 患者。
- U-Net：验证患者和测试患者均完整处理；恢复到第 2 轮。
- Attention U-Net：验证患者和测试患者均完整处理；恢复到第 2 轮。
- 真实 BraTS 研究指标：`NotRun`
- 论文指标：没有生成 Dice、IoU、Precision、Recall、mean±std 或配对检验。
- smoke 报告：`artifacts/smoke/final/smoke_report.json`
- smoke 报告 SHA-256：`41bd9d20b13944fc590d64ba510100c8372dc3aa029e76b433e0bfdb8a3a42d7`
- 源提交：`297d656925737247db922e293e67f4f1733a3d9f`

## 测试门禁

- 全量 Python：44 passed，0 failed。
- Ruff format：44 files already formatted。
- Ruff lint：All checks passed。
- 单元覆盖包括 WT 标签映射、同步增强、空掩膜指标、模型固定输出、缓存完整性、验证冻结、测试集锁定和断点逐张量一致性。
- Starlette/httpx 只有一条既有弃用警告；未屏蔽，并不影响测试。

## 未执行项

- 未获得 BraTS 2020 公开训练集，未执行真实扫描、258/74/37 划分或真实训练。
- 未获得真实权重，未导出 ONNX 权重。
- 未执行三种随机种子的真实重复实验。
- 未执行真实患者配对统计、95%置信区间或毕业论文指标表。
- 所有真实研究指标仍为 `NotRun`。
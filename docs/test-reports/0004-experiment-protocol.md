# 阶段四：实验协议、验证冻结与论文报表

日期：2026-11-26  

**免责声明：仅供科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

## 验收范围

- 固定的版本化 YAML 协议和文档，U-Net/Attention U-Net 共用控制变量，并按 17、42、2024 配对。
- 配置差异白名单、验证集三维重建患者 Dice 阈值选择、固定 0.50 敏感性模式。
- 测试冻结记录与验证来源检查、缺项/不匹配拒绝。
- 空掩膜口径、切片/患者/患者宏平均/pooled 指标定义、患者对配对检验和 bootstrap。
- 真实产物报表脚本及仅合成/缺数据的 `NotRun` 模板路径。

## 执行结果

本次未发现真实 BraTS 数据或已冻结的真实模型产物。真实数据扫描、研究训练、真实验证冻结、正式测试及论文成绩/图表均未执行；合成 fixture 仅验证报表脚本会返回模板和 `NotRun`，不会被用于填入结果。

- 全仓 Python 测试：**68 passed，0 failed**；包含阶段四配置差异、验证来源篡改、固定阈值冻结、配对缺失/意外病例、零差值、空掩膜，以及合成数据报表门禁。
- Ruff 格式检查：**54 files already formatted**。
- Ruff lint：**All checks passed**。
- `uv lock --check`：通过，锁定 57 个依赖。
- 基线配置 CLI：`status=valid`，结果状态为 `NotRun`；论文报表 CLI `--help` 显示主分析与 `fixed_050` 两种模式。
- 测试期间唯一警告：既有 Starlette/httpx `TestClient` 弃用提示；未屏蔽。
- 本机 `uv sync --frozen --extra training --extra reports` 重试遇到 OneDrive 虚拟环境目录的文件访问拒绝；`uv lock --check` 通过。回归测试使用已安装依赖并显式设置源码路径执行。

## 命令记录

| 命令 | 结果 |
| --- | --- |
| `$env:PYTHONPATH='ml;services\ml-inference'; .venv\Scripts\python.exe -m pytest` | 68 passed，0 failed |
| `.venv\Scripts\python.exe -m ruff format --check .` | 54 files already formatted |
| `.venv\Scripts\python.exe -m ruff check .` | All checks passed |
| `$env:UV_LINK_MODE='copy'; .tools\uv\uv.exe lock --check` | 通过 |
| `.tools\uv\uv.exe sync --frozen --extra training --extra reports` | 本机 OneDrive `.venv` 文件访问拒绝，未完成 |
| 基线配置验证与报表 CLI help | 通过 |
| BraTS 完整训练 / 正式测试 / 真实论文报表 | 未执行（未授权；真实数据及冻结权重未提供） |

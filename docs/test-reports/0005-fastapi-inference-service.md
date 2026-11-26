# 阶段五：FastAPI 全体积推理服务

日期：2026-11-26

**免责声明：仅供科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

## 验收范围

- 五个规定的健康、模型、分割与评价 API 及其 Pydantic/OpenAPI 响应契约。
- 版本化 YAML 清单、权重 SHA-256、模型元数据和阈值不匹配时的 fail-closed 行为。
- 完整三维输入的共享预处理、轴位切片推理、反向缩放、原空间 NIfTI 预测对象和哈希。
- 受控预测对象引用、GT/预测空间核对、患者级和切片宏平均评价。
- 上传/解压大小、数值、维度、方向、并发与推理超时边界；错误响应和 CorrelationId。

## 执行结果

- 全仓 Python 测试：**77 passed，0 failed**。
- Ruff 格式检查：**59 files already formatted**。
- Ruff lint：**All checks passed**。
- `uv lock --check`：通过；未修改依赖清单或锁文件。
- `git diff --check`：通过。
- Compose 服务配置由 `tests/test_infrastructure.py` 解析和断言；未执行 Docker 镜像构建或容器启动。
- 唯一测试警告：既有 Starlette/httpx `TestClient` 弃用提示；未屏蔽。

## 替身与真实权重边界

没有真实模型权重或真实 BraTS 输入。因此没有执行真实权重推理、正式研究评价或临床工作流。服务路径测试使用显式注入的合成 predictor，并断言输出及对象 sidecar 都标记 `artifactKind: synthetic_test`。ONNX 运行时契约测试使用临时 Identity 图和合成权重；该 manifest 同样标记 `synthetic_test`，通过正式启动路径会被 `TEST_ARTIFACT_NOT_ALLOWED` 拒绝。合成结果不代表研究表现，不得用于论文成绩。

## 覆盖的关键断言

- `.nii` 与 `.nii.gz` 全体积输入均可进入服务；预测掩膜回到非方形原始 `(8,10,3)` 尺寸，输出 affine/方向保留，且值为二值。
- 非轴位输入、spacing/方向/affine/形状不匹配、非法标签、错误对象键、输入超限、解压超限及非有限强度均拒绝。
- 预测对象按输入哈希、权重/清单来源、模型版本、预处理版本、阈值和评价协议可追溯；对象哈希会在读取时复核。
- 同一患者完整体数据的预测得到患者级指标及逐切片指标宏平均；空 GT 与空预测按共享定义返回四项指标均为 1。
- 权重哈希错误和测试权重清单不会就绪；模型架构、预处理版本、输入尺寸和阈值元数据不匹配分别拒绝。
- 超时返回 `INFERENCE_TIMEOUT`；无可用模型时 `/health` 保持存活而 `/ready` 返回 503。

## 命令记录

| 命令 | 结果 |
| --- | --- |
| `$env:PYTHONPATH='ml;services\ml-inference'; .venv\Scripts\python.exe -m pytest -q` | 77 passed，0 failed |
| `.venv\Scripts\python.exe -m ruff format --check .` | 59 files already formatted |
| `.venv\Scripts\python.exe -m ruff check .` | All checks passed |
| `.tools\uv\uv.exe lock --check` | 通过 |
| `git diff --check` | 通过 |
| Docker build/Compose 启动、真实研究权重推理、真实 BraTS 评价 | 未执行 |

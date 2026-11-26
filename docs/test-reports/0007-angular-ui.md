# 阶段七：Angular 科研 UI

日期：2026-11-26

**免责声明：仅供本科毕业设计、科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

## 实现范围

- 使用 ABP 生成的 BrainStudy、SegmentationJob、SegmentationResult、ModelVersion、ExperimentRun API 代理；上传代理保留可选进度事件。
- Standalone 页面覆盖病例上传/GT 登记、任务列表与详情、逐层结果查看、模型版本及实验追溯；路由、导航和按钮使用 ABP 权限并 fail-closed。
- 原始 NIfTI 浏览器预校验、上传进度、服务器 SHA-256 对照、任务分页/轮询/取消/重试，以及缺少 GT 时隐藏准确性指标。
- 结果查看器验证掩膜二值性和与原影像的形状/affine 一致性；提供轴位切层、原图/掩膜/叠加/轮廓/对比、透明度和缩放操作。
- 原图只保存在 SPA 内存，缓存上限 192 MiB；刷新或逐出后需要重传。未新增 API，也不把影像保存到浏览器持久化层。

## 执行结果

| 验证 | 结果 |
| --- | --- |
| `npm test` | **7 个测试文件、16 项通过** |
| `npm run lint` | 通过 |
| `npx tsc --noEmit --project tsconfig.json` | 通过 |
| `npm run build` | 通过，初始 bundle 508.01 kB（低于 800 kB warning budget） |
| `npm run format:check` | 通过 |
| `npm run test:e2e` | **4 项通过**：桌面与移动端各运行上传→任务轮询→打开结果主流程及系统状态流程 |

E2E 使用浏览器内生成的微型合成 NIfTI、模拟 ABP 权限配置和 HTTP fixtures；任务/结果使用测试数据，不启动真实后端推理，不加载真实研究权重。单测覆盖 NIfTI 文件验证、ABP 权限 fail-closed、API 错误关联 ID、无 GT 时不展示零分、切层与透明度变更。

## 未执行与限制

- 未运行真实身份提供方/OIDC 登录、真实 ABP 后端/数据库/对象存储联调。
- 未使用真实模型、真实 BraTS 数据或真实病例截图；未运行正式测试集、训练任务或论文性能/指标实验。
- 自动化 E2E 的“成功”只表示 UI 与替身 API 契约可运行，不能解释为真实模型分割结果成功。
- 无原始影像下载端点，刷新页面或缓存逐出后不能重建结果叠加，需重新上传原病例。
- Docker/Compose 未在本阶段重新执行。

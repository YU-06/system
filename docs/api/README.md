# API 与 OpenAPI 索引

**免责声明：仅供科研与教学演示，非医疗器械，不用于临床诊断，不提供确诊、治疗或预后建议。**

| API | 运行时 OpenAPI | Compose 默认宿主机访问 | 详细契约 |
| --- | --- | --- | --- |
| ABP 模块化单体 | `/swagger/v1/swagger.json`；Swagger UI `/swagger` | `http://127.0.0.1:5000/swagger` | [领域、权限与 API](research-domain.md) |
| FastAPI 推理 | `/openapi.json`；Swagger UI `/docs` | 基础 Compose 不映射 `8000`；仅后端通过 `backend-internal` 网络访问 | [ML 推理 API](ml-inference.md) |

ABP 常规控制器由 Application Service 生成，模块化 API 描述以运行时 schema 为准；FastAPI Pydantic 请求/响应模型生成其 schema。修改 DTO、路由、权限、稳定错误码或 FastAPI 模型后，应在已启动且未暴露密钥的受控开发环境重新获取 schema，审阅差异、更新相应契约文档和前端生成代理，并运行 API/权限测试。不要手工杜撰 OpenAPI JSON，也不要将 schema 输出和真实认证 header/配置一同发布。

FastAPI schema 可在推理容器内核对，而不发布内部端口：

```powershell
docker compose exec ml-inference python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json').status)"
```

如开发者确实要从宿主机直接连接 Postgres/FastAPI，须显式叠加 [compose.dev.yaml](../../compose.dev.yaml)；该 overlay 仍只绑定 `127.0.0.1`，不可用于部署：

```powershell
docker compose -f compose.yaml -f compose.dev.yaml config --quiet
```

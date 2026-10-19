# Changelog

## 2.2.0

- 增加 Pydantic API 响应契约与 `schema_version`。
- 前端检查 API schema 版本，避免前后端结构不兼容。
- 版本号收敛为 `grid_analyzer.__version__` 单一来源，`pyproject.toml` 动态读取。
- 移除陈旧的 `requirements.txt`，依赖统一由 `pyproject.toml` 管理。
- 新增 `docs/api.md`。
- 参数扫描新增自包含 HTML 热力图，支持切换评估指标。

# Changelog

## 2.3.0

- 新增 5 分钟参数高原研究：BaoStock 数据层、SQLite 缓存、按交易日 T+1。
- 新增 6 个月窗口、70/30 样本内/样本外、滚动 OOS 和最终锁定盲测。
- 新增已实现年化、Calmar、Sharpe、Sortino、最大回撤等指标。
- API schema_version 升级到 2。
- 前端新增 5 分钟参数高原面板：小多图、滚动 OOS 表、参数稳定性和最终盲测。
- 新增 `scripts/intraday_heatmap.py` 命令行研究工具，输出 JSON/CSV。

## 2.2.0

- 增加 Pydantic API 响应契约与 `schema_version`。
- 前端检查 API schema 版本，避免前后端结构不兼容。
- 版本号收敛为 `grid_analyzer.__version__` 单一来源，`pyproject.toml` 动态读取。
- 移除陈旧的 `requirements.txt`，依赖统一由 `pyproject.toml` 管理。
- 新增 `docs/api.md`。
- 参数扫描新增自包含 HTML 热力图，支持切换评估指标。
- 网页端新增“参数高原热力图”面板，接入 `/api/heatmap`。
- 热力图面板支持编辑格距、止损、初始底仓列表，并显示初始底仓聚合说明。

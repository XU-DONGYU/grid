# 产品文档索引

本目录存放面向用户和产品行为的模块文档。产品文档与代码同仓库维护，模块行为变化时必须同步更新。

| 模块 | 产品文档 | 代码入口 |
|---|---|---|
| 5 分钟参数高原热力图 | [`intraday-heatmap.md`](intraday-heatmap.md) | `grid_analyzer/services/intraday_heatmap.py`（规划中） |
| 单股票网格分析 | 待补充 | `grid_analyzer/services/analysis.py` |
| 日线参数热力图 | 待补充 | `grid_analyzer/services/heatmap.py` |

## 文档规则

- 每个面向用户的模块必须有独立产品文档。
- 输入、输出、指标口径、验证方法、数据源、API、前端交互、性能或已知限制发生变化时，必须在同一提交更新对应产品文档。
- 产品文档必须包含模板中的必需章节。
- CI 会检查文档存在性、必需章节和相对链接。
- 产品文档不能替代 API 文档、方法论文档和 CHANGELOG，四者需要同步。

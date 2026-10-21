# 5 分钟参数高原热力图 产品文档

- `doc_version`: 0.3.0
- `last_updated`: 2026-10-21
- `related_code`: `grid_analyzer/services/intraday_heatmap.py`, `grid_analyzer/services/intraday_research.py`, `grid_analyzer/data/intraday.py`, `grid_analyzer/backtest/engine.py`, `grid_analyzer/backtest/metrics.py`
- `related_api`: `POST /api/intraday-heatmap/jobs`, `GET /api/intraday-heatmap/jobs/{job_id}`
- `related_tests`: `tests/unit/test_intraday_backtest.py`, `tests/unit/test_intraday_cache.py`, `tests/unit/test_intraday_research.py`, `tests/unit/test_metrics.py`, `tests/integration/test_intraday_heatmap.py`

## 1. 产品目标与非目标

### 目标

- 对单只 A 股，扫描网格密度 K 与破网止损组合，寻找可解释的参数高原。
- 使用 5 分钟 K 线执行回测，使用日线 ATR(14) 确定网格密度基准。
- 同时展示样本内参数高原、滚动样本外验证和最终锁定参数盲测。
- 将已实现网格收益、总权益收益、Calmar、Sharpe、Sortino、最大回撤等指标放在同一研究视图中。
- 复用现有单股票分析上下文中的区间、ATR、资金、费用和初始底仓。

### 非目标

- 不提供买卖建议。
- 不保证未来收益。
- 不替代全市场筛选。
- 不在浏览器中计算指标或回测。
- 不建模完整盘口、逐笔成交和真实滑点。

## 2. 用户与使用场景

目标用户是进行个人网格策略研究的用户。

典型场景：

- 已对某只股票完成一次单股票分析，希望研究不同网格密度和止损下的稳健性。
- 希望判断某个 K 值附近是否存在连续参数高原，而不是单点最优。
- 希望看到参数在滚动样本外和最终盲测中的衰减程度。
- 希望对比多个指标，而不是只看收益。

## 3. 输入参数与默认值

| 参数 | 默认值 | 说明 |
|---|---|---|
| `code` | 必填 | 股票代码 |
| `capital` | 100000 | 总资金 |
| `fee` | 0.025 | 单边佣金 % |
| `min_fee` | 5 | 单笔最低佣金 |
| `init_position` | 当前分析输入 | 初始底仓比例 |
| `k_start` | 0.50 | 网格密度 K 起点 |
| `k_end` | 1.50 | 网格密度 K 终点 |
| `k_step` | 0.05 | K 步长 |
| `stop_losses` | 0,3,5,8 | 破网止损 % 列表 |
| `atr_period` | 14 | 日线 ATR 周期 |
| `window_months` | 6 | 每个回测窗口长度 |
| `in_sample_ratio` | 0.70 | 样本内比例 |
| `oos_coverage_months` | 12 | 累计样本外覆盖目标 |
| `final_blind_months` | 3 | 最终锁定盲测长度 |
| `primary_metric` | realized_annual_pct | 参数高原选择的主指标 |
| `adjustflag` | 前复权 | 数据复权方式 |

默认 K 值：

```text
0.50, 0.55, 0.60, ..., 1.45, 1.50
```

共 21 个值。

网格目标间距：

```text
target_gap = K × 日线 ATR(14)%
```

实际间距继续受成本门槛、间距上限和资金不足一手的自动拉宽约束。

## 4. 输出内容与页面结构

页面分为四个区域：

1. **当前上下文**
   - 股票代码和名称
   - 日线 ATR(14)
   - 区间上下限和中轴
   - 资金、费用、初始底仓
   - 数据快照日期

2. **样本内参数高原**
   - 每个指标一张折线小图
   - X 轴为 K
   - Y 轴为指标
   - 每个止损值一条线
   - 标记参数高原中心

3. **滚动样本外验证**
   - 每个窗口的起止日期
   - 选中的 K 和止损
   - 样本内与样本外指标
   - 累计样本外覆盖月数
   - 参数稳定性
   - 正收益窗口比例

4. **最终锁定盲测**
   - 锁定参数
   - 盲测区间
   - 盲测指标
   - 与滚动样本外的对比
   - 明确标注“盲测未参与选参”

## 5. 指标口径

- `realized_annual_pct`：已实现网格盈亏 / 资金，按 243 个交易日年化。
- `total_annual_pct`：总权益年化收益。
- `calmar`：总权益年化收益 / 最大回撤。
- `sharpe`：日度权益收益均值 / 标准差 × √243。
- `sortino`：日度权益收益均值 / 下行波动 × √243。
- `max_drawdown_pct`：5 分钟权益曲线的最大回撤。
- `win_rate_pct`：盈利回合数 / 总回合数。
- `profit_factor`：总盈利 / 总亏损。
- `stop_count`：止损触发次数。
- `positive_window_ratio`：正收益窗口比例。

参数高原评分：

- 收益类、Calmar、Sharpe、Sortino：`mean - stdev`。
- 最大回撤：`-(mean + stdev)`，越低越好。
- 沿 K 方向做 3 点平滑后选择高原中心。

## 6. 数据源、缓存与数据快照

- 5 分钟和日线数据来自 BaoStock。
- 使用前复权。
- 本地 SQLite 缓存，默认路径 `.cache/intraday.sqlite3`。
- 缓存记录代码、频率、时间戳、交易日、OHLCV、成交额和复权标记。
- 历史数据永久缓存；请求超出缓存时只补拉缺失区间。
- 每次分析记录数据快照日期和缓存版本。
- 单只股票失败不能影响其他任务。
- 部署时必须使用项目虚拟环境中的 uvicorn，确保 BaoStock、pandas、numpy 可用；系统 Python 可能未安装这些依赖。

## 7. 验证方法论

### 7.1 6 个月窗口

每个回测窗口固定为 6 个月。

### 7.2 70% / 30% 切分

- 前 70% 为样本内，用于扫描 K × 止损并寻找参数高原。
- 后 30% 为样本外，只验证该窗口样本内选出的参数，不参与选参。

每个窗口的日线 ATR(14)、区间和中轴只使用该窗口样本内结束前可用的数据，避免未来函数。

### 7.3 滚动方式

- 滚动步长等于样本外长度。
- 样本外段不重叠。
- 每个窗口重新选择参数。
- 累计样本外覆盖至少 12 个月。

约需 7 个窗口，总数据约 20 个月。

### 7.4 最终锁定盲测

- 在滚动验证之后，保留最后 3 个月数据。
- 最终盲测段不参与任何选参。
- 锁定参数在最终盲测前确定。
- 最终盲测只评估一次，不允许根据结果反向调参。

### 7.5 数据不足

- 累计样本外不足 12 个月时，明确返回“长期样本外验证不可用”。
- 不静默缩短窗口或伪造结果。

## 8. API 契约

接口：`POST /api/intraday-heatmap/jobs` 创建后台任务，`GET /api/intraday-heatmap/jobs/{job_id}` 轮询状态。同步接口 `POST /api/intraday-heatmap` 保留给短参数和命令行调用。

响应顶层包含：

- `ok`
- `schema_version`
- `data`

`data` 包含：

- `context`
- `k_values`
- `stop_losses`
- `metrics`
- `cells`
- `selection`
- `rolling_oos`
- `final_blind`
- `validation_meta`
- `sample_count`

所有响应由 Pydantic 模型定义，字段变更必须同步更新 API 文档、前端、测试和本产品文档。

## 9. 交互流程与状态

1. 用户输入股票代码和当前分析参数。
2. 点击“生成 5 分钟参数高原”。
3. 前端创建后台任务并显示已等待时间。
4. 后端读取缓存，缺失数据从 BaoStock 补拉。
5. 前端轮询任务状态，完成后展示样本内、滚动样本外和最终盲测结果。
6. 前端渲染小多图、表格和风险提示。
7. 失败时显示明确错误，不展示部分伪造结果。

## 10. 边界条件与已知限制

- 未建模涨跌停、停牌、滑点、成交量和盘口冲击。
- 5 分钟数据可能有缺失 bar、半天市和停牌缺口。
- BaoStock 可用性和登录状态依赖外部服务。
- Sharpe、Calmar 对窗口长度敏感。
- 最终盲测只有一段，不能替代长期实盘验证。
- 滚动样本外重复查看和调参会削弱样本外意义。
- 北交所股票支持情况需要单独验证。

## 11. 性能预算与失败处理

- 默认目标：单股票 5 分钟参数高原在合理时间内完成。
- 优先使用本地 SQLite 缓存。
- 如果滚动窗口和参数组合导致耗时过长，改为后台任务和进度查询。
- 任务失败时保留错误信息，不返回不完整结果。
- 计算过程中不允许无上限并发请求 BaoStock。

## 12. 验收标准

- K 从 0.5 到 1.5，步长 0.05，共 21 个值。
- 每个窗口 6 个月，样本内/样本外 70%/30%。
- 滚动步长等于样本外长度，OOS 段不重叠。
- 累计样本外至少 12 个月。
- 最终盲测 3 个月，且不参与选参。
- T+1 按交易日判断。
- 指标、表格和小多图与后端响应一致。
- 产品文档、API 文档、CHANGELOG 同提交更新。
- `make ci` 和隐私扫描通过。

## 13. 变更记录与相关文档

命令行入口：`scripts/intraday_heatmap.py`。

实验扩展：ATR 归一化参数高原使用独立的 `POST /api/plateau` 接口和 `grid_analyzer/backtest/plateau.py` 引擎，以无量纲 k 为单轴、0/1 阶跃撮合、孤岛剔除和中心偏左高原选择为特征。它不替代本页的滚动 OOS 和最终盲测，详细口径见 [ATR 归一化参数高原（实验）](atr-plateau.md)。

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-19 | 0.1.0 | 初版：确定 6 个月窗口、70/30、滚动 OOS、最终盲测和产品文档约束 |
| 2026-10-19 | 0.2.0 | 实现 BaoStock 数据层、5 分钟引擎、指标、滚动 OOS、最终盲测、API 和前端面板 |
| 2026-10-21 | 0.3.0 | 新增实验性 ATR 归一化参数高原入口和产品文档链接；保留原有滚动验证不变 |

相关文档：

- [ATR 归一化参数高原（实验）](atr-plateau.md)
- [架构说明](../architecture.md)
- [方法论](../methodology.md)
- [API 契约](../api.md)
- [产品文档索引](README.md)

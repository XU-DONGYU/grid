# API 契约

所有分析接口位于 `/api` 下。响应使用 Pydantic 模型定义，模型文件为 `grid_analyzer/api/schemas.py`。

## 版本策略

- `version`：应用版本，位于 `/api/version` 和 `data.version`。
- `schema_version`：API 数据结构版本，位于 `/api/analyze` 响应顶层和 `/api/version`。
- 不兼容的数据结构变更必须递增 `schema_version`。
- 前端会检查 `schema_version`，不匹配时拒绝渲染并提示升级。

## GET /api/analyze

查询参数：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `code` | string | 必填 | 股票代码，如 `002541` 或 `sz002541` |
| `capital` | float | `100000` | 总资金 |
| `fee` | float | `0.025` | 单边佣金百分比 |
| `min_fee` | float | `5` | 单笔最低佣金 |
| `main_ratio` | float | `0.7` | 主网格资金占比 |
| `init_position` | float | `0` | 初始底仓比例 |
| `stop_loss` | float | `5` | 破网止损百分比 |

响应顶层：

```json
{
  "ok": true,
  "schema_version": 2,
  "data": {}
}
```

`data` 主要字段：

- `params`：本次请求参数
- `quote`：股票行情与总市值
- `liquidity`：价差、五档承接、流动性评级
- `axis`：中轴
- `volatility`：HV、ATR、布林带宽分位、Vol of Vol、Squeeze
- `trend`：趋势、%B、行情形态、适配度
- `kline_tail`：图表与回测使用的最近 120 日 K 线
- `main_grid` / `aux_grid`：当前推荐网格
- `backtest`：主/辅网格回测结果
- `backtest_meta`：历史校准窗口与无未来函数标记
- `risks`：风险提示
- `version`：应用版本

## GET /api/heatmap

基于 Walk-forward 结果生成参数高原矩阵。查询参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `code` | 必填 | 股票代码 |
| `capital` | `100000` | 总资金 |
| `fee` | `0.025` | 单边佣金 % |
| `min_fee` | `5` | 单笔最低佣金 |
| `history_days` | `250` | 拉取历史天数 |
| `calib_days` | `120` | 每个窗口的校准天数 |
| `test_days` | `60` | 每个窗口的测试天数 |
| `step` | `60` | 滚动步长 |
| `gap_scales` | `0.8,0.9,1.0,1.1,1.2` | 格距缩放列表 |
| `stop_losses` | `0,3,5,8` | 止损列表 |
| `init_positions` | `0,0.2` | 初始底仓列表（0~1） |
| `metric` | `plateau_score` | 热力图指标 |
| `spread_pct` | `0.05` | 历史价差代理 % |

响应 `data` 包含：

- `name` / `code`
- `metric` / `metric_label` / `direction`
- `gap_scales` / `stop_losses` / `init_positions`
- `cells`：每个单元格的 `gap_scale`、`stop_loss`、`value`、`count`、`color`、`is_best`
- `best`：当前指标最优组合
- `low` / `high`：颜色图例范围
- `sample_count`：参数组合数量

前端页面中的“参数高原热力图”面板会调用该接口，并允许直接编辑格距、止损和初始底仓列表。

## POST /api/intraday-heatmap

基于 BaoStock 5 分钟数据和日线 ATR(14) 生成参数高原、滚动样本外验证和最终锁定盲测。

请求体主要字段：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `code` | 必填 | 股票代码 |
| `capital` | `100000` | 总资金 |
| `fee` | `0.025` | 单边佣金 % |
| `min_fee` | `5` | 单笔最低佣金 |
| `init_position` | `0` | 初始底仓比例 |
| `stop_losses` | `[0,3,5,8]` | 破网止损列表 |
| `k_start` / `k_end` / `k_step` | `0.5 / 1.5 / 0.05` | 网格密度 K 扫描 |
| `window_days` | `126` | 每个窗口约 6 个月 |
| `in_sample_ratio` | `0.70` | 样本内比例 |
| `final_blind_days` | `63` | 最终锁定盲测约 3 个月 |
| `min_oos_days` | `252` | 累计样本外至少约 12 个月 |
| `primary_metric` | `realized_annual_pct` | 参数高原主指标 |
| `history_days` | `500` | 拉取历史交易日数 |

响应 `data` 包含：

- `context`：ATR、区间、资金、数据快照
- `k_values`、`stop_losses`
- `cells`：每个 K × 止损的样本内聚合指标和 plateau_score
- `folds`：每个滚动窗口的样本内/样本外结果
- `parameter_stability`：各窗口选中的 K 和止损
- `locked`：锁定参数和最终盲测结果
- `summary`：累计 OOS 覆盖、正收益窗口比例、均值/最差/标准差
- `data_snapshot`：BaoStock 数据区间和 bar 数量

该接口计算量较大，当前为同步调用；后续可按性能情况改为后台任务。

## POST /api/intraday-heatmap/jobs

创建 5 分钟参数高原后台任务。请求体与 `/api/intraday-heatmap` 相同。

响应：

```json
{"ok": true, "schema_version": 2, "data": {"job_id": "...", "status": "queued"}}
```

## GET /api/intraday-heatmap/jobs/{job_id}

查询任务状态：

- `queued`
- `running`
- `completed`
- `failed`

完成后 `data.result` 为完整的 `IntradayHeatmapData`；失败时 `data.error` 包含错误信息。

前端使用该任务接口，避免长请求被反向代理超时截断。同步接口 `/api/intraday-heatmap` 仍保留，适合短参数或命令行调用。

## GET /api/health

返回：

```json
{"ok": true, "version": "2.3.0", "env": "development"}
```

## GET /api/version

返回：

```json
{"version": "2.3.0", "schema_version": 2}
```

## 错误响应

FastAPI 标准错误结构：

```json
{"detail": "错误说明"}
```

常见状态码：

- `400`：代码格式错误、历史数据不足、资金不足一手
- `404`：行情或 K 线不存在
- `502`：行情服务不可用或返回异常

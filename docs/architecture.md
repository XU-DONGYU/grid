# 架构说明

## 目标

把“行情获取、指标计算、网格设计、回测、风控、展示”拆成独立层，保证：

- 业务规则只有一个事实来源；
- 纯计算可以离线测试；
- 外部依赖（腾讯行情、FastAPI）集中在边缘；
- 回测结果可复现、可解释；
- 前端只负责展示和交互。

## 分层

```text
前端 (grid_analyzer/web)
        ↓ HTTP
API 路由 (grid_analyzer/api)
        ↓
分析服务 (grid_analyzer/services)
        ↓
┌──────────────┬──────────────┬──────────────┐
│ 指标          │ 网格设计      │ 回测/研究     │
│ indicators   │ grid         │ backtest     │
└──────────────┴──────────────┴──────────────┘
        ↓
风控规则 (grid_analyzer/risk)
        ↓
行情数据 (grid_analyzer/data)
        ↓
腾讯行情 / 内存缓存
```

## 依赖方向

- `domain` 模型和纯计算不依赖 FastAPI、不访问网络。
- `data` 负责外部 I/O、解析、缓存和超时重试。
- `api` 负责参数校验、依赖注入和 HTTP 错误映射。
- `services` 负责编排，不包含具体公式。
- `web` 只消费 API 字段，不复制业务公式。

## 目录职责

| 目录 | 职责 |
|---|---|
| `grid_analyzer/api` | `/api/analyze`、`/api/health`、`/api/version` |
| `grid_analyzer/services` | 分析流程编排、参数扫描、Walk-forward |
| `grid_analyzer/data` | 数据源协议、腾讯实现、缓存 |
| `grid_analyzer/indicators` | 中轴、ATR、HV、布林带宽、Squeeze、趋势、评分、流动性 |
| `grid_analyzer/grid` | 间距规则、主/辅网格、资金分配、资金约束 |
| `grid_analyzer/backtest` | 事件驱动撮合、T+1、止损、权益曲线、滚动窗口 |
| `grid_analyzer/risk` | 趋势、挤压、流动性、资金约束、止损风险 |
| `grid_analyzer/web` | HTML 骨架、CSS、ES Modules |
| `scripts` | 参数扫描、Walk-forward、隐私扫描 |
| `tests` | 单元、集成、离线夹具 |

## 回测边界

回测引擎只接收：

- `klines`：日线 OHLCV；
- `grid`：已设计好的档位和每格股数；
- 费用、最低佣金、初始底仓、止损参数。

它不访问网络，也不读取当前行情，因此可以用固定夹具复现。

## 当前推荐参数 vs 回测参数

- 当前推荐参数使用最新数据生成，用于展示。
- 回测参数只使用回测窗口之前的数据校准，避免未来函数。
- Walk-forward 进一步把历史切成多个“校准 → 测试”窗口，输出样本外表现。

## 扩展点

- 新增数据源：实现 `MarketDataProvider`。
- 新增指标：放入 `indicators/`，补单元测试。
- 新增风控规则：放入 `risk/rules.py`。
- 新增研究指标：扩展 `services/research.py`。
- 新增前端模块：在 `web/static/js` 下保持 ES Module 边界。

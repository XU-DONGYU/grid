# A股网格交易参数分析器

基于腾讯财经行情，计算中轴、波动率、布林带宽分位、ATR、网格区间与间距，并对近 120 个交易日进行事件驱动回测。

## 功能

- 中轴、HV、ATR、Vol of Vol、布林带宽历史分位、TTM Squeeze
- 主网格 / 辅助网格设计，等比档位，ATR 与波动率锚定
- 资金约束下自动拉宽间距，保证每格至少一手
- 回测支持 T+1、现金约束、跳空、最低佣金、印花税、破网止损
- 回测参数使用回测起点之前的数据校准，避免未来函数
- 权益曲线、最大回撤、交易次数、费用与风险提示
- 离线行情夹具与特征测试，支持无网络验证

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/`。

## 开发命令

```bash
make install      # 创建 .venv 并安装依赖
make dev          # 开发模式，自动重载
make test         # pytest + coverage
make lint         # ruff
make typecheck    # mypy
make scan         # 隐私与密钥扫描
make ci           # lint + typecheck + test + scan
```

## 配置

配置通过环境变量读取，默认值见 `.env.example`：

```bash
export APP_ENV=development
export APP_HOST=127.0.0.1
export APP_PORT=8000
export QUOTE_CACHE_TTL_SECONDS=30
export KLINE_CACHE_TTL_SECONDS=300
export LOG_LEVEL=INFO
```

行情缓存默认使用进程内 TTL 缓存，不引入数据库。

## 测试

```bash
make test
```

测试使用 `tests/fixtures/` 下的离线行情，不依赖外网。`002541` 与 `600000` 作为固定特征测试样本。

## 参数扫描与 Walk-forward

单组参数滚动验证：

```bash
.venv/bin/python scripts/walk_forward.py \
  --code 002541 \
  --history-days 750 \
  --calib-days 250 --test-days 60 --step 60 \
  --gap-scale 1.0 --stop-loss 5 --init-position 0
```

参数扫描：

```bash
.venv/bin/python scripts/sweep.py \
  --code 002541 \
  --history-days 750 \
  --gap-scales 0.8,0.9,1.0,1.1,1.2 \
  --stop-losses 0,3,5,8 \
  --init-positions 0,0.2 \
  --calib-days 250 --test-days 60 --step 60
```

输出写入 `reports/`（已被 git 忽略）。扫描结果包含：

- `mean_return_pct`：样本外平均收益
- `worst_return_pct`：最差窗口收益
- `compounded_return_pct`：样本外复利收益
- `max_drawdown_pct`：最大单窗口回撤
- `stop_count`：止损触发次数
- `plateau_score = mean_return_pct - stdev_return_pct`：稳健性评分

优先选择 `plateau_score` 高且相邻参数表现接近的“参数高原”，不要只取单点最高收益。

## 隐私与密钥

提交前必须执行：

```bash
make scan
```

扫描内容包括：

- GitHub / AWS / OpenAI 风格 token
- 私钥文件内容
- 密码、secret、API key 赋值
- 邮箱地址
- 用户主目录绝对路径

同时启用 `pre-commit` 的 `detect-private-key` 钩子。不要在仓库中提交 `.env`、私钥、token 或包含个人信息的日志。

## 目录

```text
.
├─ app.py                  # FastAPI 兼容入口
├─ file.md                 # 网格交易方法论文档
├─ grid_analyzer/
│  ├─ main.py              # create_app、中间件、首页
│  ├─ web/                 # HTML 骨架、CSS、ES Modules
│  ├─ config.py            # 环境变量配置
│  ├─ cache.py             # 行情 TTL 缓存
│  ├─ constants.py         # 全局常量
│  ├─ api/                 # FastAPI 路由与依赖
│  ├─ services/            # 分析流程编排
│  ├─ data/                # 腾讯行情与数据源协议
│  ├─ utils/               # 费用与统计工具
│  ├─ indicators/          # 中轴、波动率、趋势、评分、流动性
│  ├─ grid/                # 间距与主/辅网格设计
│  ├─ backtest/            # 事件驱动回测引擎
│  └─ risk/                # 风险规则
├─ pyproject.toml          # 依赖与工具配置
├─ Makefile
├─ scripts/
│  ├─ scan_secrets.py      # 隐私与密钥扫描
│  ├─ sweep.py             # 参数扫描 + Walk-forward
│  └─ walk_forward.py      # 单组参数滚动验证
├─ tests/
│  ├─ fixtures/            # 离线行情
│  ├─ unit/                # 纯函数与回测不变量
│  └─ integration/         # API 特征测试
└─ docs/                   # 架构与方法论文档（后续补充）
```

## 部署

当前使用 systemd 服务 `grid.service`。更新代码后执行：

```bash
sudo systemctl restart grid.service
systemctl show -p MainPID --value grid.service
curl -s http://127.0.0.1:8000/api/health
```

健康检查返回：

```json
{"ok": true, "version": "2.1", "env": "development"}
```

服务重启后 PID 会变化，这是正常现象。应以服务单元名和健康检查判断状态，而不是记旧 PID。

## 免责声明

本项目仅用于参数研究与回测验证，不构成投资建议。历史回测不代表未来收益。

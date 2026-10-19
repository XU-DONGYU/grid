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

## 测试

```bash
make test
```

测试使用 `tests/fixtures/` 下的离线行情，不依赖外网。`002541` 与 `600000` 作为固定特征测试样本。

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
├─ index.html              # 当前前端，后续拆分为静态模块
├─ file.md                 # 网格交易方法论文档
├─ grid_analyzer/
│  ├─ constants.py         # 全局常量
│  ├─ utils/               # 费用与统计工具
│  ├─ indicators/          # 中轴、波动率、趋势、评分、流动性
│  ├─ grid/                # 间距与主/辅网格设计
│  ├─ backtest/            # 事件驱动回测引擎
│  └─ risk/                # 风险规则
├─ pyproject.toml          # 依赖与工具配置
├─ Makefile
├─ scripts/
│  └─ scan_secrets.py      # 隐私与密钥扫描
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
curl -s http://127.0.0.1:8000/
```

服务重启后 PID 会变化，这是正常现象。应以服务单元名和健康检查判断状态，而不是记旧 PID。

## 免责声明

本项目仅用于参数研究与回测验证，不构成投资建议。历史回测不代表未来收益。

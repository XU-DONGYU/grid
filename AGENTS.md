# AGENTS.md

本文件面向在本仓库中工作的 AI 代理和新贡献者。它分为两部分：

1. 通用开发规则：适用于任何软件项目。
2. 项目专用规则：只适用于本仓库的网格交易分析器。

开始工作前先阅读本文件，并遵守其中的“禁止事项”和“完成定义”。

---

## 第一部分：通用开发规则

### 1. 工作方式

- 先理解现状，再修改代码。优先阅读相关文件、测试和文档。
- 修改前明确目标、影响范围和验证方式。
- 优先做小步、可验证、可回滚的改动，避免一次性大规模重写。
- 保持现有行为兼容，除非任务明确要求改变行为。
- 不猜测外部库的 API；先查看依赖版本和现有用法。
- 不引入新依赖，除非确有必要，并说明原因。
- 不做与当前任务无关的重构、格式化或文件重命名。

### 2. 代码质量

- 遵循仓库现有风格、命名和目录结构。
- 新代码必须有类型标注，尤其是公共函数和数据结构。
- 复杂逻辑必须拆成命名清晰的函数，避免超长函数。
- 不添加无意义注释；注释解释“为什么”，而不是“做了什么”。
- 不提交调试输出、临时文件、注释掉的代码或死代码。
- 错误处理要明确：不要静默吞掉异常。
- 配置通过配置层或环境变量读取，不要散落硬编码。

### 3. 测试

- 修改行为前先确认现有测试覆盖；必要时先补特征测试。
- 新功能必须有单元测试或集成测试。
- 测试必须可离线运行，不依赖真实网络、真实时间或外部服务。
- 使用固定夹具和确定性数据；避免随机测试。
- 修复 bug 时，先写一个能复现问题的测试，再修复。
- 不为了让测试通过而降低断言强度或删除测试，除非明确说明原因。

### 4. 隐私与安全

- 禁止提交 token、私钥、密码、API key、cookie、个人邮箱、手机号、身份证号。
- 禁止提交 `.env`、`.git-credentials`、私钥文件和包含个人信息的日志。
- 文档和示例中使用占位路径，例如 `/path/to/grid`，不要写入个人主目录。
- 不在日志中输出完整请求参数中的敏感信息。
- 提交前必须执行隐私扫描。
- 发现疑似泄露时，先移除文件并说明；不要只依赖历史提交删除。

### 5. Git 工作流

- 每次有意义的修改都要提交并推送到远程仓库，除非用户明确要求暂不提交。
- 提交前检查 `git status`、`git diff` 和隐私扫描结果。
- 提交信息使用 Conventional Commits 风格：
  - `feat:` 新功能
  - `fix:` 修复
  - `refactor:` 重构
  - `test:` 测试
  - `docs:` 文档
  - `chore:` 工具、依赖、版本
  - `style:` 纯格式调整
- 一次提交只做一件逻辑上完整的事。
- 不提交生成物：缓存、覆盖率文件、构建产物、虚拟环境、egg-info。
- 不修改 git 用户配置，不使用 force push，不跳过 hooks，除非用户明确要求。
- 大范围改动建议使用独立分支；小范围修复可直接提交主分支。

### 6. 文档

- 行为、接口、配置或流程发生变化时，同步更新 README 或相关文档。
- API 变更必须更新 API 契约文档。
- 重要架构决策应记录在 ADR 中。
- 示例命令必须可执行，示例路径必须是占位路径。
- 不写无法验证的承诺或收益保证。

### 7. 沟通

- 汇报时说明“做了什么、为什么、验证结果、剩余风险”。
- 不粘贴大段代码或命令输出，除非用户要求。
- 遇到权限、凭据、外部服务不可用时，明确说明阻塞点和需要用户执行的动作。
- 不隐瞒失败；测试失败或未验证项必须明确写出。

---

## 第二部分：项目专用规则

### 1. 项目定位

本项目是个人研究工具，用于：

- A 股单只股票的网格参数分析。
- 网格区间、间距、资金分配建议。
- 事件驱动回测。
- 参数扫描、Walk-forward 和参数高原研究。

不是多人 Web 产品，不是自动交易系统，不提供投资建议。

### 2. 技术栈

- Python 3.11+，当前运行环境可能是 Python 3.14。
- FastAPI + Uvicorn。
- Pydantic 用于 API 契约。
- 原生 HTML/CSS/JavaScript ES Modules，无前端构建步骤。
- 腾讯财经行情接口。
- pytest + pytest-cov + ruff + mypy + pre-commit。
- systemd 部署，服务名为 `grid.service`。

### 3. 常用命令

```bash
make install      # 创建虚拟环境并安装依赖
make dev          # 开发模式，自动重载
make test         # pytest + coverage
make lint         # ruff
make typecheck    # mypy
make scan         # 隐私与密钥扫描
make ci           # lint + typecheck + test + scan
```

研究工具：

```bash
.venv/bin/python scripts/walk_forward.py --help
.venv/bin/python scripts/sweep.py --help
```

### 4. 目录边界

| 路径 | 职责 |
|---|---|
| `app.py` | 兼容入口，只负责导出 FastAPI app 和旧函数 |
| `grid_analyzer/main.py` | 创建 app、中间件、静态资源、首页 |
| `grid_analyzer/api/` | HTTP 路由和 Pydantic 契约 |
| `grid_analyzer/services/` | 分析、研究、热力图编排 |
| `grid_analyzer/data/` | 行情提供方、解析、缓存 |
| `grid_analyzer/indicators/` | 纯指标计算 |
| `grid_analyzer/grid/` | 间距、主辅网格、资金分配 |
| `grid_analyzer/backtest/` | 回测引擎、滚动窗口 |
| `grid_analyzer/risk/` | 风险规则 |
| `grid_analyzer/web/` | HTML 骨架、CSS、ES Modules |
| `scripts/` | CLI 研究工具、隐私扫描 |
| `tests/` | 单元、集成、离线夹具 |
| `docs/` | 架构、方法论、API、ADR |

依赖方向：

```text
api → services → indicators/grid/backtest/risk → data
```

禁止让 `indicators`、`grid`、`backtest`、`risk` 依赖 FastAPI 或直接访问网络。

### 5. 领域规则

#### 网格设计

- 间距同时受成本门槛、ATR、日波动率约束。
- 主网格默认锚定 `0.70 × ATR%`，辅助网格 `0.55 × ATR%`。
- 使用等比档位。
- 资金不足一手时自动拉宽间距，并标记 `capital_constrained`。
- 网格参数分为“当前推荐参数”和“历史校准参数”，不能混用。

#### 回测

必须保持以下不变量：

- 买入不能透支现金。
- 当日买入的仓位当日不能卖出（T+1）。
- 权益恒等式：`cash + holdings == capital + net_profit`。
- 已实现盈亏 + 未实现盈亏 == 净利润。
- 回测参数只能使用回测窗口之前的数据校准，禁止未来函数。
- 破网止损触发后停止新交易，并按 T+1 规则处理当日买入仓位。
- 最低佣金和卖出印花税必须计入。

修改回测逻辑时，必须同步更新：

- `tests/unit/test_backtest.py`
- `tests/integration/test_analyze.py`
- `docs/methodology.md`

#### 研究流程

- Walk-forward 的校准窗口和测试窗口不能重叠。
- 参数扫描默认按 `plateau_score = mean_return_pct - stdev_return_pct` 排序。
- 热力图可见维度是 `gap_scale × stop_loss`。
- `init_position` 是隐藏聚合维度，每个单元格显示其均值。
- 不要把单点最高收益当作最终结论；优先看参数高原。

### 6. API 契约

- 所有响应模型定义在 `grid_analyzer/api/schemas.py`。
- 不允许在路由中直接返回未定义的裸 dict。
- 响应必须包含 `schema_version`。
- 前端会校验 `schema_version`，不兼容时拒绝渲染。
- 修改 API 字段时必须同步更新：
  - `grid_analyzer/api/schemas.py`
  - `grid_analyzer/api/routes.py`
  - `grid_analyzer/web/static/js/api.js`
  - `docs/api.md`
  - 集成测试

当前接口：

- `GET /api/analyze`
- `GET /api/health`
- `GET /api/version`
- `GET /api/heatmap`

### 7. 前端规则

- 前端代码位于 `grid_analyzer/web/`。
- 使用 ES Modules，不引入构建工具。
- 前端只负责展示和交互，不复制后端业务公式。
- 数字格式化放在 `format.js`，请求封装放在 `api.js`，图表放在 `charts.js`，热力图渲染放在 `heatmap.js`。
- 不在 HTML 中写内联事件处理器；事件绑定放在 `main.js`。
- 修改前端后至少运行 `node --check`。
- 生产环境不要依赖浏览器缓存，HTML 和 API 均设置了 no-store。

### 8. 数据层

- 腾讯行情和 K 线解析放在 `grid_analyzer/data/tencent.py`。
- 单元测试必须 mock 外部请求，不访问真实网络。
- 行情和 K 线使用进程内 TTL 缓存。
- 缓存键必须包含代码、周期和天数。
- 新增数据源时实现 `MarketDataProvider` 协议。
- 不要在业务模块中直接调用 `requests`。

### 9. 版本与发布

- 版本号唯一来源是 `grid_analyzer/__init__.py` 的 `__version__`。
- `pyproject.toml` 通过动态版本读取该值，不要重复写版本号。
- 版本变更必须同步更新 `CHANGELOG.md`。
- 不恢复 `requirements.txt`；依赖统一由 `pyproject.toml` 管理。
- 发布前检查：
  - 版本号一致
  - `make ci` 通过
  - 隐私扫描通过
  - 文档更新
  - CHANGELOG 更新

### 10. 部署

- 生产服务使用 systemd 单元 `grid.service`。
- 服务重启后 PID 会变化，这是正常现象。
- 判断服务状态使用服务单元名和健康检查，不要记旧 PID。
- 生产环境不要使用 `--reload`。
- 更新代码后需要重启服务才能加载新代码。
- 没有权限时不要尝试强制重启；明确告知用户需要执行的操作。
- 部署示例使用占位路径 `/path/to/grid`，不要提交个人绝对路径。

### 11. 禁止事项

- 禁止提交个人隐私信息、token、私钥、`.env`。
- 禁止在测试中访问真实外部网络。
- 禁止让回测使用未来数据。
- 禁止在前端重新实现佣金、印花税、网格间距等业务规则。
- 禁止直接修改 `app.py` 添加业务逻辑；它只是兼容入口。
- 禁止在 `grid_analyzer/api/routes.py` 中返回未定义契约的裸 dict。
- 禁止把缓存、覆盖率、egg-info、虚拟环境、研究输出提交到仓库。
- 禁止为了让测试通过而删除不变量断言。
- 禁止在没有说明的情况下改变回测口径。

### 12. 完成定义

一个任务完成前必须满足：

- 行为符合需求，且没有破坏现有功能。
- 新逻辑有测试覆盖；相关旧测试通过。
- `make ci` 通过。
- `make scan` 无发现。
- 相关文档、API 契约和 CHANGELOG 已更新。
- 修改已提交并推送到 GitHub。
- 最终汇报包含：做了什么、为什么、验证结果、剩余风险。

### 13. 快速检查清单

```text
[ ] 阅读相关代码、测试和文档
[ ] 明确修改边界，避免无关改动
[ ] 先补测试或确认现有测试
[ ] 保持 API 契约和 schema_version
[ ] 保持回测无未来函数、T+1、现金约束
[ ] 前端不复制业务公式
[ ] 版本号只在 grid_analyzer/__init__.py 修改
[ ] 更新 README / docs / CHANGELOG
[ ] make ci
[ ] make scan
[ ] git status / git diff 检查
[ ] commit + push
```

---

如果本文件与用户的最新明确指令冲突，以用户指令为准；如果与代码现状冲突，先指出冲突，再决定是否修改。

# ADR 0003: 前端使用原生 ES Modules

## 状态

已采纳。

## 背景

项目是个人研究工具，页面结构稳定，引入 React/Vue 和构建链会增加部署复杂度。

## 决策

- 保持原生 HTML/CSS/JS；
- 使用 ES Modules 拆分 `api`、`format`、`charts`、`render`、`main`；
- 由 FastAPI 挂载 `/static`；
- 继续使用 no-store 缓存策略，避免旧页面残留。

## 影响

- 无构建步骤，部署简单；
- 模块边界清晰，前端不再复制后端业务公式；
- 如果未来交互复杂度显著上升，再评估迁移到 Vite + 框架。

# 99 分目标评分设计

| 评分项 | 满分 | 项目证据 |
|---|---:|---|
| Impact | 25 | 拥堵、可达性、碳排、热暴露和公共资源同时量化 |
| Data Analytics | 20 | 多源数据融合、需求估计、路网分配、容量压力、敏感性和验证 |
| Innovation | 15 | 情景模拟 + 组合优化 + grounded AI action plan |
| Feasibility | 15 | 每项干预都有成本、实施条件和现实执行主体 |
| Legacy | 10 | 事件配置化，可迁移至演唱会、马拉松、会展和校园赛事 |
| Visualization | 10 | 路网压力图、前后对比、Pareto frontier、行动卡片 |
| Pitch | 5 | 问题—模型—现场 demo—量化结果—长期价值 |

## 必须交付的证据

- Baseline 与至少 4 个干预情景；
- 真实数据与 proxy 的来源说明；
- 模型假设、敏感性分析与限制；
- 成本—收益 Pareto frontier；
- 至少一个可复现的城市深度案例；
- 11 城市可迁移框架，不强行伪造精确排名；
- 评委可以在网页中修改预算和方案并立即获得结果。

## v0.8 Distributional Decision Criteria

The optimizer can include three additional result metrics:

- vulnerable-demand non-car coverage;
- zero-vehicle-demand mobility coverage;
- accessible-public-mode coverage proxy.

`Equity-first` gives greater weight to the first and third metrics. `Accessibility-first` gives the greatest added weight to accessible-public-mode coverage. Hard thresholds remove portfolios that fail the configured minimum. These metrics strengthen impact and feasibility only when their data sources, aggregation and limitations are disclosed.

## v0.9 Competition-Readiness Additions

- **Data Analytics:** adds explicit counterfactual benchmarks, standalone effects and leave-one-out marginal contributions.
- **Innovation:** explains portfolio interactions instead of presenting the optimizer as a black box.
- **Feasibility / Implementation:** attaches agency ownership, lead time, approvals, dependencies, verification metrics and go/no-go gates to each action.
- **Presentation:** generates a structured narrative and judging-criteria alignment directly from model outputs.
- **Trustworthiness:** labels marginal effects as model counterfactuals and implementation metadata as planning templates until externally verified.

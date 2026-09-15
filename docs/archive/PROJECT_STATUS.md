> Archived pre-NY/NJ prototype document. Not current evidence.

# Project Status — v0.9

## 已完成

- [x] 区域需求、路线分配和路段压力主模型
- [x] 7 类交通与公共健康干预
- [x] Rice、GTFS、OSM、交通计数、候选设施和公平性数据接入
- [x] 三时段、五类压力测试和 81 组敏感性分析
- [x] 多方式分配及 Shuttle / transit / rideshare 运力约束
- [x] OD calibration、baseline audit 和 evidence package
- [x] 公平性、无障碍目标与优化硬约束
- [x] 预算约束组合优化与 Pareto frontier
- [x] Grounded AI Action Plan
- [x] Intervention standalone 与 leave-one-out 边际贡献分析
- [x] 预设方案 benchmark 与 portfolio interaction effect
- [x] Agency owner、lead time、approval、dependency 和 verification matrix
- [x] T-90 至 T+14 operational playbook 与 go/no-go gates
- [x] Competition Submission Studio
- [x] Markdown / JSON submission package 导出
- [x] 21 个测试、standalone smoke test 和前端语法检查

## v0.9 解决的关键问题

v0.8 可以回答“哪个组合效果最好、是否公平、证据是否充分”。v0.9 进一步回答：

1. 组合中的每项措施贡献了多少；
2. 哪些措施存在重叠或互补；
3. 谁负责实施、需要多久、依赖什么审批和核验；
4. 如何直接形成比赛 narrative 和评分标准对照材料。

## 当前验收点

- Explain API 对每个选中干预返回 standalone 和 marginal result；
- 优化器和 explainability 使用同一 objective scoring；
- Implementation API 为每项干预返回 owner、lead time、difficulty、approval、dependencies 和 verification metric；
- Submission API 生成 executive summary、methodology、findings、playbook、limitations 和 judging alignment；
- Webpage 可下载 Markdown narrative 与 JSON package；
- 所有新增结果保留规划假设和因果边界说明。

## 下一阶段优先级

1. 在用户本地完整 Rice 数据上生成正式 Houston OD calibration；
2. 接入 Houston 官方 GTFS、OSM 和交通计数并保存可复现 evidence snapshot；
3. 用 ACS / CDC SVI 生成真实 zone equity profile；
4. 核验 Park & Ride、Fan Zone、rideshare 和 cooling/medical 候选设施；
5. 增加第二座结构不同的城市作为 transferability case；
6. 完成正式英文 narrative、技术附录、托管网页、pitch deck 和演示视频；
7. 使用观测活动数据或专家评审对方案排序进行外部验证。

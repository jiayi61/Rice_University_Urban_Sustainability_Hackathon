> Legacy prototype documentation. See README.md and NYNJ_METHODOLOGY.md for the current competition case.

# EventFlow AI 设计说明

## 1. 产品目标

给定城市、场馆、赛事时间、预计人流、天气、预算与政策约束，系统完成：

- 赛事出行需求估计；
- 道路与最后一公里压力识别；
- 交通与公共资源干预模拟；
- 预算约束下的组合优化；
- 可解释的城市行动计划生成。

## 2. 核心分析链路

```text
Origin zones
→ Demand estimation
→ Route assignment
→ Road pressure / last-mile gap / heat exposure
→ Intervention simulation
→ Portfolio optimization
→ Action plan
```

## 3. 主模型

区域需求：

```text
d_i = event attendance × origin share_i
```

路段新增车辆流量：

```text
added_flow_e = Σ_i d_i × car_share_i × route_share_{i,e} / occupancy
```

路段压力：

```text
pressure_e = (baseline_e + added_flow_e) / capacity_e
```

## 4. 干预库

- 2-mile Vehicle Restriction Zone
- Park-and-Ride Shuttle
- Temporary Bus-Only Lane
- Transit Frequency Boost
- Rideshare Staging Zones
- Pedestrian Routing and Wayfinding
- Cooling, Water and Medical Points

每个方案必须具有成本、适用条件、模型影响和实施难度字段。

## 5. AI 边界

AI Advisor 不生成底层数值，不直接替代交通模型。它读取情景模拟和优化结果，完成：

- 推荐理由解释；
- 优先级排序；
- 预算变化下的方案调整；
- 城市行动计划编写；
- 风险与限制说明。

## 6. 产品页面

1. 11 城市准备度比较；
2. Houston baseline stress test；
3. 干预情景模拟器；
4. 预算约束优化与 Pareto frontier；
5. AI City Action Plan。

## 7. v0.5 路网构建

系统读取 Overpass JSON，将 OSM way 拆为有向路段。每条路段包含：

- source / target node；
- geometry；
- highway class；
- directional lanes；
- speed；
- free-flow travel time；
- capacity；
- baseline calibration source。

六个 origin zones 和场馆被吸附到道路节点。系统使用 Dijkstra 算法计算主路径，并通过惩罚主路径边生成可行备选路径。实际进入压力模型的路网为所有 origin-assignment paths 的并集，以控制优化器和敏感性分析的运行时间。

## 8. v0.5 交通计数校准

交通计数可以来自 CSV 或 GeoJSON。系统自动识别经纬度与 AADT/ADT/volume 字段，并通过空间网格索引把计数点吸附到道路路段。

默认换算为：

```text
observed directional event-hour flow
= daily count × peak-hour factor × directional factor
```

有观测值的路段使用观测与道路类别先验的加权结果；同一道路类别的未观测路段使用中位校准因子。每条路段保留 `calibration_source`，支持审计。

## 9. 数据层级

```text
Rice signals → origin demand / heat / resource gap
GTFS → transit access and mode-share adjustment
OSM → network topology and route assignment
Traffic counts → baseline road-volume calibration
Scenario model → pressure, travel, emissions, heat
Optimizer → budget-constrained intervention portfolio
AI Advisor → grounded action plan
```

## 9. v0.6 运力约束与多方式分配

v0.6 将区域游客分配到道路车辆、Shuttle、公共交通和步行/骑行四类方式。Park-and-Ride Shuttle 的服务人数受车队、座位数、周转时间、运营窗口和载客率约束。公共交通增班和 Rideshare staging 同样具有显式容量上限。

系统分别输出期望转移人数、可用容量、实际服务人数、未满足人数和容量利用率。未满足的方式转移需求会进入剩余风险，并影响最终 readiness score。

该设计确保情景结果能够回答“需要多少车辆和运力”，避免使用无限交通供给假设。

## 10. 模型证据覆盖

网页显示 visitor demand、GTFS、OSM、traffic calibration、route coverage 和 transit-zone coverage 的数据连接程度。该分数表示证据覆盖，不表示预测准确率。

## 10. v0.7 OD 校准与候选设施

v0.7 将区域需求拆解为可审计校准表。每个 origin zone 展示低、中、高需求范围、POI / visits / customers / spend 信号贡献、热风险、资源缺口和交通可达性。需求范围用于情景规划，不被表述为统计置信区间。

候选设施模块接入 Park-and-Ride、Rideshare、Fan Zone 和 Cooling/Medical 点。系统在 OSM 路网上计算候选点至场馆的路线距离、单程时间和 Shuttle 周转时间，并结合容量、成本、位置和 ADA 属性进行规划初筛。Shuttle 和 Rideshare 的有效运力取运营配置与候选场站吞吐能力的较小值。

Baseline audit 检查 OD demand 守恒、mode assignment 守恒、origin route coverage、observed traffic calibration 和 candidate infrastructure evidence。该审计用于提高方法透明度，不用于声称预测准确率。

## 11. v0.8 公平性、无障碍与证据层

v0.8 为六个 origin zone 接入零车家庭、低收入、残障人口、CDC SVI 和无障碍路径代理指标。系统将这些指标与区域赛事需求结合，计算脆弱人群非驾车覆盖、零车家庭出行覆盖和残障需求加权的无障碍公共方式覆盖。

优化器提供 Balanced、Equity-first 和 Accessibility-first 三种目标，并允许设置最低覆盖约束。公平性指标用于比较干预收益分配，不替代法律意义上的 ADA 审查或个体层面判断。

候选设施同时记录来源、证据等级、容量核验和无障碍核验。官方位置证据只证明设施位置来自官方来源；容量、赛事可用性、许可和临时运营条件需要独立核验。

## 12. v0.9 Explainability, Implementation and Submission Layer

v0.9 为优化后的方案增加两类反事实分析：单项干预相对 baseline 的 standalone effect，以及从完整组合中删除一项措施后的 leave-one-out marginal effect。组合评分、边际评分和优化器使用同一透明权重，便于解释“为什么选择这一组方案”。

每项干预增加责任机构、准备周期、实施难度、审批要求、依赖条件、可逆性和赛事日核验指标。系统根据选中组合生成 T-90 至 T+14 的部署计划、go/no-go gates 和 after-action review。

Submission Studio 将模型结果、证据覆盖、边际贡献、实施计划、评分标准匹配和限制条件组合为英文 Markdown narrative 与 JSON package。生成内容完全来自确定性模型和当前数据状态。

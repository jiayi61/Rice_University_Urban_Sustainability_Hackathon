# API 配置与跨城市建模

## 密钥填写位置

在项目根目录的 `.env` 文件中填写（与 `start.py` 同级）：

```dotenv
OPENAI_API_KEY=你的OpenAI密钥
OPENAI_MODEL=gpt-4.1-mini
```

首次配置可复制 `.env.example` 为 `.env`。填完后重新运行 `python3 start.py --no-browser --port 8766`，打开 http://127.0.0.1:8766/#new-event 。不要将密钥写入 HTML、JavaScript 或提交到 GitHub；`.env` 已被忽略。模型名可以改成你账户支持且支持 Responses Structured Outputs 的模型。密钥存在仅表示已配置，连通性和额度会在首次请求时验证。

主界面仍先展示休斯敦。提交活动需求调用后端实时建模；另一个按钮保留有观测依据的纽约预设案例。`legacy.html` 是原休斯敦工作台，顶部提供返回新入口的链接。

## 两种输入方式

1. 配置密钥后，城市框留空，输入中文或英文，例如：“2027年6月8日在芝加哥 Soldier Field 举办5万人演唱会，接驳预算10万美元。”服务端使用 OpenAI Responses API 提取城市、场馆、日期、人数、美元预算；LLM 不生成疏散指标。
2. 没有密钥也可以运行：填写 City / country、Venue、Attendance、Budget 等字段。城市字段非空时使用结构化输入，不调用 OpenAI。建议用英文城市和场馆名称。显式字段覆盖文本抽取值。

请检查返回的场馆名称、人数和参数。指定场馆无法查到时返回错误，不替换为该城市的默认场馆。未指定场馆时，内置城市使用注明为假设的默认场馆，其他城市尝试公开场馆搜索。位置搜索不是唯一性或场馆适用性验证。

## 实际计算内容

`POST /api/v3/brief` 保留路径，结果结构升级为 `schema_version: 4.0`，指标在 `simulation` 中。旧的三个模板方案不再返回；历史 `universal.html/js` 未挂载，不是当前入口。

```json
{
  "prompt": "Concert in Chicago",
  "online": true,
  "inputs": {
    "city_query": "Chicago, USA",
    "venue_query": "Soldier Field",
    "attendance": 50000,
    "budget_usd": 100000,
    "cohort_pct": 40,
    "baseline_service_pph": 12000,
    "fleet_limit": 100,
    "bus_cost_usd": 2500
  }
}
```

模型用道路通行时间计算车辆循环时间：`2 × 单程分钟数 + 上下客时间`。附加小时运力为 `车辆数 × 座位数 × 上座率 × 60 / 循环分钟数`。默认 45 座、85% 上座率、15 分钟上下客，可通过 inputs 的 `bus_seats`、`load_factor`、`dwell_minutes` 修改。

设一个客流区人数为 Q、总小时服务率为 μ，则清空时间为 `60Q/μ` 分钟，排队人时为 `Q²/(2μ)`。需求守恒，车辆按客流份额用最大余数法分配。在 0 到 fleet_limit 间枚举整数车辆数，选预算内排队人时最低的方案；成本包含18%交付余量。另计算需求与服务率各 ±15% 的九个情景。不是全局多模式交通优化。

## 数据覆盖与限制

- OpenAI 仅用于需求解析，后端实现：`src/eventflow/brief_api.py`。
- 公开位置与设施：Nominatim / Overpass；道路通行时间：OSRM。都有超时，路线失败会明确标注为估算直线。公共服务不是有保障的生产数据服务。
- 城市道路不同，会改变循环时间和运力。观众来源、模式份额、基础服务能力仍是显式假设。找到车站不等于核实班次、运力和可达性。
- 结果只覆盖填写的交通人群比例，不声称覆盖所有观众。接驳路线需要核查大巴通行限制、上下客场地、许可与供应商。
- 不自动声称碳排、热风险、公平性或安全收益。要做到城市级可信预测，下一步需接入当地 GTFS/实时服务、计数和票务来源数据，并做留出验证。
- 所有费用以美元假设计算，不假称当地报价。历史天气仅供背景，不驱动当前队列模型。

Nominatim 公共服务仅适合少量、用户触发的查询；代码有全进程串行限速（最多约每秒一次）和缓存。正式部署请使用自有/商业服务，通过服务器环境变量 `NOMINATIM_URL` 切换；多进程部署需共享限速。使用者应阅读 [Nominatim 使用政策](https://operations.osmfoundation.org/policies/nominatim/)。当前服务器面向本机使用，公开部署前需认证、共享请求限流和任务队列。

## 检查与代码位置

- `GET /api/config`：只返回密钥是否存在和模型名，不返回密钥。
- `src/eventflow/universal.py`：数据获取与流程编排。
- `src/eventflow/screening.py`：可重现队列与车队预算计算。
- `start.py` / `app/main.py`：独立服务与 FastAPI 的同等入口。
- `app/static/app.js`：表单、进度、错误、实时结果和下载。

官方接口依据：[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)、[OSRM API](https://project-osrm.org/docs/v5.24.0/api/)。

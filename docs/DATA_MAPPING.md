# 数据接入与字段映射

## 黑客松数据

### urban-heat-index-rice

- `LATITUDE`, `LONGITUDE`, `POINT_GEOMETRY`
- `UHI`
- `MARKET`

用途：构建空间热暴露层。

### store-visits-rice

- `STORE_ID`, `NAME`, `BRAND`
- `STATE`, `MARKET`
- `NAICS_CODE`, `CATEGORY`, `SUB_CATEGORY`
- `LOCAL_DATE`, `DAILY_VISITS`

用途：估计区域活跃度、活动时段需求与商业节点压力。

### spend-patterns-rice

- `SPEND_DATE_RANGE_START`, `SPEND_DATE_RANGE_END`
- `CITY`, `LATITUDE`, `LONGITUDE`, `LOCATION_NAME`
- `RAW_NUM_CUSTOMERS`, `RAW_NUM_TRANSACTIONS`, `RAW_TOTAL_SPEND`
- `SPEND_BY_DAY`, `SPEND_BY_DAY_OF_WEEK`
- `RELATED_RIDESHARE_SERVICE_PCT`
- `MARKET`

用途：辅助构造 visitor origin、商业吸引力、时间分布与 rideshare proxy。

### core-poi-geometry-rice

- `PLACEKEY`, `LOCATION_NAME`, `BRANDS`
- `LATITUDE`, `LONGITUDE`, `POLYGON_WKT`
- `CITY`, `REGION`, `POSTAL_CODE`, `MARKET`
- `TOP_CATEGORY`, `SUB_CATEGORY`, `NAICS_CODE`
- `OPEN_HOURS`, `INCLUDES_PARKING_LOT`, `ENCLOSED`

用途：识别停车、商业、医疗、室内避暑和活动节点。

### daily-weather-rice

- `CITY_LOCATION_IDENTIFIER...`, `VALID_DATE_AS_YYYYMMDD`
- `MAXIMUM_TEMPERATURE_C...`, `MINIMUM_TEMPERATURE_C...`, `AVERAGE_TEMPERATURE_C...`
- `AVERAGE_RELATIVE_HUMIDITY...`, `AVERAGE_WIND_SPEED_KNOTS...`
- `PRECIPITATION...`

用途：计算比赛日天气与热风险情景。

## 公开外部数据

- Houston METRO GTFS：站点、线路、班次和服务日历。
- OpenStreetMap：道路、步行、自行车、停车与 POI。
- TxDOT / Houston open data：AADT、道路流量与速度 proxy。
- FIFA / Host Committee：赛程、场馆和比赛时间。

## 关键限制

黑客松数据经过匿名化、噪声扰动和空间偏移。最终结论需表述为方法展示、情景模拟和决策工作流，不可声称是精确现实预测。

## v0.5 Road Network Profile

`osm_profile.json` contains:

- OSM node coordinates;
- directed road segments;
- road name and highway class;
- geometry;
- inferred directional lanes, speed, capacity and baseline utilization;
- nearest network node for each origin zone and NRG Stadium;
- primary and alternative origin-to-stadium paths;
- dynamic `stadium_core` and `critical_corridors` target groups.

## v0.5 Traffic Calibration Profile

`traffic_profile.json` contains:

- detected latitude, longitude and traffic-count fields;
- count points and road snapping distance;
- configurable peak-hour and directional factors;
- directly calibrated edge baselines;
- road-class calibration factors for edges without nearby observations;
- explicit calibration source per edge.

## v0.6 Operational Parameters

| Parameter | Purpose |
|---|---|
| `shuttle_fleet` | Event-window shuttle vehicle count |
| `shuttle_seats` | Seats per vehicle |
| `shuttle_cycle_minutes` | Round-trip cycle time |
| `operating_window_minutes` | Available service window |
| `shuttle_load_factor` | Expected usable seat share |
| `transit_extra_capacity` | Incremental passenger capacity from frequency boost |
| `rideshare_staging_capacity` | Passenger throughput of managed staging zones |

Scenario outputs now include `mode_split`, `zone_assignments` and `operational_feasibility`.

## v0.7 Candidate Infrastructure Fields

支持 CSV、JSON 或 GeoJSON。字段别名会自动匹配。

| Canonical field | Required | Example |
|---|---:|---|
| `candidate_type` | Yes | `park_ride` |
| `latitude` | Yes | `29.7410` |
| `longitude` | Yes | `-95.4630` |
| `candidate_id` | No | `pr_galleria` |
| `name` | No | `Galleria Park-and-Ride` |
| `capacity_riders` | No | `4200` |
| `cost_usd` | No | `165000` |
| `accessible` | No | `yes` |

支持类型：`park_ride`、`rideshare`、`fan_zone`、`cooling_medical`。

## v0.8 Equity and Accessibility Fields

| Canonical field | Purpose |
|---|---|
| `zone_id` | Match one of the six EventFlow origin zones |
| `population` | Context and future population-weighted analysis |
| `zero_vehicle_share` | Dependence on non-car event access |
| `low_income_share` | Affordability and burden screening |
| `disability_share` | Accessibility-sensitive demand proxy |
| `svi_percentile` | Area-level social-vulnerability screening |
| `ada_path_score` | Planning proxy for accessible origin and last-mile paths |
| `source_name`, `source_url`, `evidence_year` | Provenance and vintage |

Shares accept values from 0–1 or 0–100. `ada_path_score` does not certify ADA compliance.

## v0.8 Candidate Evidence Fields

| Field | Meaning |
|---|---|
| `official_source` | Location or record comes from an official agency source |
| `evidence_level` | User input, planning source, official location or verified operations |
| `capacity_verified` | Capacity value has an identified verifiable source |
| `accessibility_verified` | Accessibility claim has an identified source |
| `source_name`, `source_url` | Evidence provenance |

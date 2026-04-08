# 算法运行时收口说明

本文档记录 2026-04-09 这轮“最小必要的算法收口优化”后的运行时口径。

目标不是升级算法能力，而是统一默认主链路、减少分析层/重算层/图展示层的结果分叉，让展示与答辩时的口径更稳定。

## 1. 当前系统默认使用哪套算法

当前默认主链路是新版 unified control inference：

- `backend.analysis.control_inference.build_control_context()`
- `backend.analysis.control_inference.infer_controllers()`

单公司重算入口仍然是：

- `backend.analysis.ownership_penetration.refresh_company_control_analysis()`

但它默认调用 unified 引擎，不再把 legacy 股权穿透作为默认路径。

## 2. 哪些入口会触发重算

以下入口会触发重算，并默认使用 unified 引擎：

1. `POST /companies/{company_id}/analysis/refresh`
2. `GET /companies/{company_id}/control-chain?refresh=true`
3. `GET /companies/{company_id}/actual-controller?refresh=true`
4. `GET /companies/{company_id}/country-attribution?refresh=true`
5. `GET /analysis/control-chain/{company_id}?refresh=true`
6. `GET /analysis/country-attribution/{company_id}?refresh=true`
7. `backend.analysis.ownership_penetration.refresh_all_companies_control_analysis()`
8. `backend.tasks.recompute_analysis_results.run_recompute(...)`

## 3. 哪些入口只是读取结果

以下入口默认只读取已经写回数据库的结果，不会自动重算：

1. `GET /companies/{company_id}/control-chain`
2. `GET /companies/{company_id}/actual-controller`
3. `GET /companies/{company_id}/country-attribution`
4. `GET /analysis/control-chain/{company_id}`
5. `GET /analysis/country-attribution/{company_id}`
6. `backend.analysis.control_chain.analyze_control_chain_with_options(refresh=False)`
7. `backend.analysis.country_attribution_analysis.analyze_country_attribution_with_options(refresh=False)`
8. `backend.visualization.control_graph.build_control_graph_with_session(...)`
9. `backend.analysis.ownership_graph.get_company_relationship_graph_data(...)`

因此，推荐的展示链路仍然是：

1. 先 refresh
2. 再读取 control-chain / country-attribution
3. 再构图展示

## 4. 这次收口改了什么

### 4.1 默认阈值口径统一

原行为：

- unified 引擎默认 `significant_threshold = 20%`
- 但默认 `disclosure_threshold = 25%`
- 结果是 `20%-25%` 的 significant influence 候选虽然达到了“显著影响”判定门槛，但在默认 refresh / batch recompute 下会先被过滤掉，不会写入 `control_relationships`

本次调整：

- 将 unified 主链路的默认 `disclosure_threshold` 调整为与 `significant_threshold` 一致，即 `20%`
- 同时把默认参数收口成统一常量，供以下路径共用：
  - `infer_controllers()`
  - `refresh_company_control_analysis()`
  - `refresh_all_companies_control_analysis()`
  - `backend.tasks.recompute_analysis_results.py`

为什么这是“小幅收口”，不是算法升级：

- 没有改控制评分公式
- 没有新增控制类型
- 没有改路径搜索和聚合方式
- 只是让“已经定义为 significant influence 的候选”在默认主链路里能稳定落库，避免分析判定和写回结果打架

### 4.2 批量重算默认主链路保持与单公司 refresh 一致

当前 `backend/tasks/recompute_analysis_results.py`：

- 预览模式默认 `engine_mode = unified`
- 执行模式默认 `engine_mode = unified`
- 默认阈值现在与单公司 refresh 使用同一套 unified 常量

legacy 逻辑仍保留，但只能显式启用，不再是默认路径。

### 4.3 图层与分析层使用相同的边过滤规则

当前图层和分析层统一按以下条件过滤基础边：

- `is_current = 1`
- `is_direct = 1`
- `effective_date IS NULL OR effective_date <= as_of`
- `expiry_date IS NULL OR expiry_date >= as_of`

影响范围：

- `backend.visualization.control_graph.py`
- `backend.analysis.ownership_graph.py`

因此，图展示默认不会再把仅“当前有效但非 direct”或“已过期”的边混进分析对齐视图里。

## 5. 这次是否调整了输出格式

输出结构没有做大改，仍然沿用当前展示层和接口已使用的字段：

- `control_relationships.control_type`
- `control_relationships.basis`
- `country_attributions.attribution_type`
- `country_attributions.basis`

本次没有新增复杂输出协议。

当前 joint control / `actual_controller = None` 的稳定口径仍然是：

- `control_relationships` 中会保留 `joint_control` 候选
- `actual_controller` 为空
- `country_attribution.attribution_type = joint_control`
- `country_attribution.basis` 中保留 `joint_controller_entity_ids`

也就是说，这次主要是“默认写回口径统一”，不是重做展示 schema。

## 6. 批量重算现在是否与主引擎一致

是。

默认情况下：

- 单公司 refresh 走 unified
- 批量 recompute 走 unified
- 图层读取的是 unified 写回后的结果

只有显式指定 legacy 时，批量 recompute 才会走旧版股权逻辑。

## 7. legacy 模式还保留在哪里，如何显式启用

legacy 逻辑仍保留在以下位置：

1. `backend.analysis.ownership_penetration` 中的旧版股权穿透函数
2. `backend.tasks.recompute_analysis_results.py` 的 `engine_mode="legacy"` 分支

显式启用方式：

```powershell
$env:CONTROL_INFERENCE_ENGINE = "legacy"
```

或：

```powershell
.\venv\Scripts\python.exe -m backend.tasks.recompute_analysis_results --execute --engine legacy
```

如果不显式指定 legacy：

- 默认就是 unified
- 默认不会隐式回退到 legacy

## 8. 对后续开发的影响

这次改动不会改变你后续“输入公司 -> 展示股权链路图 -> 接产业分析模块”的主开发方向。

实际影响主要有两点：

1. 默认主链路更统一了  
   refresh、批量重算、图展示默认围绕同一套 unified 结果组织，后续串接展示模块时更容易保证口径一致。

2. `20%-25%` 的 significant influence 候选现在会稳定写回  
   这会让边缘但可解释的候选在页面上更容易展示出来，也更符合当前规则文档里的“显著影响”定义。

一句话总结：

> 这次是运行时口径收口，不是算法扩张；默认 unified 主链路更明确，分析结果、批量重算、图展示更一致，且对后续展示开发是正向稳定化改动。

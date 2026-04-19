# 运行时算法链路统一说明

本文档记录 2026-04-09 这次“算法链路统一化”整理后的当前运行时口径。目标不是升级算法，而是让答辩展示时的重算、读接口、可视化尽量基于同一套新版统一控制推断引擎，减少旧版逻辑带来的结果不一致。

## 1. 当前默认使用哪套算法

当前系统默认使用：

- `backend.analysis.control_inference.build_control_context`
- `backend.analysis.control_inference.infer_controllers`

也就是新版 unified control inference 引擎。

单公司 refresh 的主入口仍然是：

- `backend.analysis.ownership_penetration.refresh_company_control_analysis()`

但它在默认情况下会直接走 unified 引擎，不再把 legacy 逻辑作为默认隐式回退。

## 2. 哪些入口会触发重算

以下入口会触发重算：

1. `POST /companies/{company_id}/analysis/refresh`
2. `GET /companies/{company_id}/control-chain?refresh=true`
3. `GET /companies/{company_id}/actual-controller?refresh=true`
4. `GET /companies/{company_id}/country-attribution?refresh=true`
5. `GET /analysis/control-chain/{company_id}?refresh=true`
6. `GET /analysis/country-attribution/{company_id}?refresh=true`
7. `backend.tasks.recompute_analysis_results.run_recompute(...)`

这些入口现在默认都应以 unified 引擎为主链路。

## 3. 哪些入口默认只是读取结果

以下入口默认只读库中已有结果，不会自动重算：

1. `GET /companies/{company_id}/control-chain`
2. `GET /companies/{company_id}/actual-controller`
3. `GET /companies/{company_id}/country-attribution`
4. `GET /analysis/control-chain/{company_id}`
5. `GET /analysis/country-attribution/{company_id}`
6. `backend.analysis.control_chain.analyze_control_chain_with_options(refresh=False)`
7. `backend.analysis.country_attribution_analysis.analyze_country_attribution_with_options(refresh=False)`
8. `backend.visualization.control_graph.build_control_graph_with_session(...)`

也就是说，图展示层默认读的是：

- 已写回的 `control_relationships`
- 已写回的 `country_attributions`
- 以及按统一过滤规则读取的基础边 `shareholder_structures`

## 4. 批量重算现在是否已与默认引擎一致

是。

`backend/tasks/recompute_analysis_results.py` 现在默认使用 unified 引擎：

- 预览模式默认 `engine_mode = unified`
- 执行模式默认 `engine_mode = unified`

批量重算仍然保留原有这些外层能力：

- 预览 schema 和删除计划
- 备份数据库
- 保留手工确认 / 需复核结果
- 分公司事务写回
- 输出 recompute 报告

但内部用于“控制人判别和国别归属生成”的算法核，默认已经切到 unified 引擎。

## 5. 图展示层是否已与分析层使用相同边过滤标准

现在已按分析层口径统一为：

- `is_current = 1`
- `is_direct = 1`
- `effective_date IS NULL OR effective_date <= as_of`
- `expiry_date IS NULL OR expiry_date >= as_of`

统一后的影响范围包括：

- `backend.visualization.control_graph.py`
- `backend.analysis.ownership_graph.py`

因此，图层展示出来的边，默认应与 unified 分析引擎真正参与计算的边保持一致，不再把仅“当前有效但非 direct”或“已过期”的边混进展示图里。

## 6. refresh 入口现在的统一口径

现在 refresh 相关入口统一为：

- 如果 `company_id` 没有映射到 `shareholder_entities.company_id`，则 refresh 视为无效输入
- `analysis` 路由和 `companies` 路由都会按相同口径处理

也就是说：

- `GET /analysis/control-chain/{company_id}?refresh=true`
- `GET /analysis/country-attribution/{company_id}?refresh=true`
- `POST /companies/{company_id}/analysis/refresh`

在是否允许 refresh 这件事上，现在是一致的。

## 7. legacy 逻辑还保留在哪里

legacy 逻辑仍然保留在以下位置：

1. `backend.analysis.ownership_penetration` 中旧版股权穿透函数
2. `backend.tasks.recompute_analysis_results.py` 的 `engine_mode="legacy"` 分支

保留这些代码的原因是：

- 兼容历史结果
- 保留显式 legacy 对比能力
- 降低一次性删除旧逻辑的风险

## 8. 如何显式启用 legacy 模式

当前只有显式指定 legacy 时才会使用 legacy 逻辑：

1. 单公司/批量运行时设置环境变量：

```powershell
$env:CONTROL_INFERENCE_ENGINE = "legacy"
```

2. 批量重算脚本显式传参：

```powershell
.\venv\Scripts\python.exe -m backend.tasks.recompute_analysis_results --execute --engine legacy
```

如果不显式指定 legacy：

- 默认就是 unified
- 单公司 refresh 不再默认因为异常而偷偷回退到 legacy

## 9. 当前统一后的结论

可以把当前系统的运行时口径概括成一句话：

> 默认情况下，重算、读结果、图展示都围绕 unified control inference 引擎组织；legacy 逻辑仍保留，但只作为显式兼容模式存在，不再是默认链路的一部分。

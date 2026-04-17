# 开发联调与演示运行说明

本文档用于统一当前项目的前后端联调、截图和最终演示环境。这里只约定运行方式，不修改控制分析主链路、不改 refresh 逻辑、不改表结构。

## 1. 数据库约定

当前后端默认库：

```text
company_test_analysis_industry_v2.db
```

原因：`backend/database.py` 中默认数据库已切到 `company_test_analysis_industry_v2.db`，即使没有单独设置 `DATABASE_URL`，当前前后端联调也会优先连接这份 V2 演示库。

当前推荐演示库：

```text
company_test_analysis_industry_v2.db
```

完整连接串：

```text
sqlite:///d:/graduation_project/corp_attribution_system/company_test_analysis_industry_v2.db
```

推荐原因：
- 覆盖控制链分析结果。
- 覆盖国别归属结果。
- 覆盖产业分析、业务线、分类映射、多报告期和质量提示。
- 更适合前端联调、截图和答辩演示。

## 2. Windows PowerShell 后端启动命令

在项目根目录执行：

```powershell
$env:DATABASE_URL='sqlite:///d:/graduation_project/corp_attribution_system/company_test_analysis_industry_v2.db'
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

注意：`$env:DATABASE_URL=...` 只对当前 PowerShell 窗口生效。新开终端后需要重新设置。

可用下面命令确认服务启动：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health'
```

## 3. 前端启动命令

另开一个 PowerShell 窗口，在项目根目录执行：

```powershell
cd frontend
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5173
```

默认后端地址：

```text
http://127.0.0.1:8000
```

如需修改前端请求后端地址，可在 `frontend/.env` 中设置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 4. HTML 验证图与前端 API 的数据库一致性

生成 HTML 验证图、运行前端 API、手工查询数据库时，建议尽量使用同一份数据库：

```text
d:/graduation_project/corp_attribution_system/company_test_analysis_industry_v2.db
```

如果使用 HTML 验证图脚本，也建议显式传入数据库路径，例如：

```powershell
.\venv\Scripts\python.exe scripts\build_demo_visualizations.py --database d:\graduation_project\corp_attribution_system\company_test_analysis_industry.db --company-id 124 --skip-refresh
```

这样可以减少以下问题：
- HTML 图来自 `company_test_analysis_demo.db`，但前端 API 来自 `company_test_analysis_industry.db`。
- 控制结论一致但记录 ID、生成时间不同，导致排查时误判。
- 前端截图、接口返回、数据库查询三者口径不一致。

## 5. 推荐联调检查接口

后端启动后，可先检查：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/companies/124/analysis/summary'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/companies/124/relationship-graph'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/companies/124/industry-analysis'
```

如果这些接口返回正常，再启动或刷新前端页面。

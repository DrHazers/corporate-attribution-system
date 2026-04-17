# Frontend

## 演示数据库约定

前端联调、截图和最终演示时，后端请固定使用：

```text
DATABASE_URL=sqlite:///d:/graduation_project/corp_attribution_system/company_test_analysis_industry_v2.db
```

不设置 `DATABASE_URL` 时，后端默认会连接项目根目录下的 `company_test_analysis_industry_v2.db`。这份库是在 `company_test_analysis_industry.db` 基础上复制并升级得到的 V2 演示库，覆盖控制链、国别归属、产业分析、多报告期和质量提示，更适合作为当前前端综合分析页的默认演示库。

这是当前项目的前端第一版，目标是快速跑通一个“企业综合分析展示页”，用于后续逐步扩展。

## 1. 安装依赖

在项目根目录执行：

```powershell
cd frontend
npm install
```

## 2. 启动前端

```powershell
cd frontend
npm run dev
```

默认访问地址：

- `http://127.0.0.1:5173`

## 3. 默认请求的后端地址

默认后端地址：

- `http://127.0.0.1:8000`

如需修改，可在 `frontend/.env` 中设置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 4. 启动后端

建议先启动 FastAPI，并显式指定演示数据库：

```powershell
$env:DATABASE_URL='sqlite:///d:/graduation_project/corp_attribution_system/company_test_analysis_industry.db'
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

HTML 验证图、前端 API 和手工数据库查询建议尽量使用同一份 `company_test_analysis_industry.db`，避免不同库之间控制分析记录 ID、生成时间或产业数据覆盖范围不一致。

## 5. 当前页面能力

当前已经接入：

- 公司总览
- 控制链与国别归属摘要
- 产业分析摘要
- 控制关系明细表
- 业务线与产业分类明细表
- 控制链关系图展示

控制链关系图基于后端 `GET /companies/{company_id}/relationship-graph` 返回的节点和边数据渲染。

## 6. 推荐演示 company_id

- `128`
- `240`
- `9717`
- `8`
- `170`

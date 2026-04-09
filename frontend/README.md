# Frontend

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

建议先启动 FastAPI：

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

为便于演示，建议后端使用更完整的演示数据库，例如：

```powershell
$env:DATABASE_URL='sqlite:///d:/graduation_project/corp_attribution_system/company_test_analysis_industry.db'
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

## 5. 当前页面能力

当前已经接入：

- 公司总览
- 控制链与国别归属摘要
- 产业分析摘要
- 控制关系明细表
- 业务线与产业分类明细表
- 控制链图占位区

控制链图目前仍是占位展示，但已经接入 `relationship-graph` 的节点数、边数和空状态信息，后续可直接替换成真正的图谱组件。

## 6. 推荐演示 company_id

- `128`
- `240`
- `9717`
- `8`
- `170`

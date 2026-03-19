from fastapi import FastAPI
from backend.api.analysis import router as analysis_router
from backend.api.company import router as company_router
from backend.api.control_relationship import router as control_relationship_router
from backend.api.country_attribution import router as country_attribution_router
from backend.api.shareholder import router as shareholder_router
from backend.database import init_db
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.shareholder import ShareholderEntity, ShareholderStructure
app = FastAPI(title="Corporate Attribution System")
app.include_router(analysis_router)
app.include_router(company_router)
app.include_router(control_relationship_router)
app.include_router(country_attribution_router)
app.include_router(shareholder_router)


@app.on_event("startup")
def on_startup():
    # 在应用启动时显式初始化数据库表。
    init_db()


@app.get("/")
def read_root():
    return {"message": "Corporate Attribution System API is running."}


@app.get("/health")
def health_check():
    return {"status": "ok"}

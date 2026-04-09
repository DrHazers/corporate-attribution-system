from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.analysis import router as analysis_router
from backend.api.company import router as company_router
from backend.api.control_relationship import router as control_relationship_router
from backend.api.country_attribution import router as country_attribution_router
from backend.api.industry_analysis import router as industry_analysis_router
from backend.api.relationship_support import router as relationship_support_router
from backend.api.shareholder import router as shareholder_router
from backend.database import init_db
import backend.models  # noqa: F401


app = FastAPI(title="Corporate Attribution System")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(analysis_router)
app.include_router(company_router)
app.include_router(control_relationship_router)
app.include_router(country_attribution_router)
app.include_router(industry_analysis_router)
app.include_router(shareholder_router)
app.include_router(relationship_support_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def read_root():
    return {"message": "Corporate Attribution System API is running."}


@app.get("/health")
def health_check():
    return {"status": "ok"}

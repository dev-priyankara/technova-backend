from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.connection import get_db

from app.routers import categories, supplier_portal, suppliers


app = FastAPI(
    title="TECHNOVA Computers API",
    description="POS and Inventory Management System API",
    version="1.0.0"
)


# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register Categories Router
app.include_router(categories.router)
app.include_router(suppliers.router)
app.include_router(supplier_portal.router)
app.include_router(supplier_portal.branch_router)


# Home Endpoint
@app.get("/")
def home():

    return {
        "message": "Welcome to TECHNOVA API",
        "status": "Running"
    }


# Database Health Check
@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):

    db.execute(text("SELECT 1"))

    return {
        "status": "healthy",
        "database": "connected"
    }
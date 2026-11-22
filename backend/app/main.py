from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import create_indexes, ping
from .routers import auth, documents, records, dashboard, search, audit


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ping()
    await create_indexes()
    yield


app = FastAPI(
    title="BhoomiTrust AI",
    description="AI-Powered Land Record Digitization & Validation System — "
                 "Extract → Validate → Score → Verify → Trust. "
                 "AI extraction and validation do not constitute legal ownership determination.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(records.router)
app.include_router(dashboard.router)
app.include_router(search.router)
app.include_router(audit.router)


@app.get("/api/health")
async def health():
    db_ok = True
    try:
        await ping()
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": "connected" if db_ok else "unreachable", "demo_mode": settings.DEMO_MODE}


@app.get("/")
def root():
    return {
        "product": "BhoomiTrust AI",
        "tagline": "Extract. Validate. Score. Verify. Trust. — a Trust & Validation Layer for digitized land records.",
        "docs": "/docs",
    }

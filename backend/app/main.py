from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import create_indexes, ping
from .routers import auth, documents, audit, document_ai, chat, intelligence
from .services.docai.errors import DocAIError


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ping()
    await create_indexes()
    yield


app = FastAPI(
    title="BhoomiTrust AI",
    description="Evidence-based Document AI for extraction, OCR, retrieval, contradiction detection, and source-cited answers.",
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
app.include_router(audit.router)
app.include_router(document_ai.router)
app.include_router(chat.router)
app.include_router(intelligence.router)


@app.exception_handler(DocAIError)
async def docai_error_handler(request: Request, exc: DocAIError):
    return JSONResponse(status_code=exc.status_code, content={"error": {
        "code": exc.code, "message": exc.message, "details": exc.details,
        "request_id": request.headers.get("x-request-id")}})


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
        "tagline": "Extract. Retrieve. Verify. Explain. — Evidence-based Document Intelligence.",
        "docs": "/docs",
    }

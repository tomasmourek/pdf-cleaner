"""upravpdf-backend — FastAPI entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .api.pdf_router import router as pdf_router
from .api.batch_router import router as batch_router

app = FastAPI(
    title="upravpdf.eu API",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pdf_router)
app.include_router(batch_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "upravpdf-backend"}

"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.rate_limit import AuthRateLimitMiddleware
from app.core.upload_limits import UploadRequestSizeLimitMiddleware
from app.api.v1.router import router as api_router

settings = get_settings()
app = FastAPI(
    title="Rubric-Grounded Essay Feedback",
    version="0.1.0",
    description="Essay feedback API with authentication and secure document processing.",
)

app.add_middleware(
    UploadRequestSizeLimitMiddleware,
    max_file_bytes=settings.max_upload_bytes,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthRateLimitMiddleware)

app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe; deliberately does not require the database."""
    return {"status": "ok"}

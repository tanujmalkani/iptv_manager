from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.performance import router as performance_router
from app.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(performance_router)

_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(_FRONTEND / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

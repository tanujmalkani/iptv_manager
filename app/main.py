from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.export import router as export_router
from app.api.performance import router as performance_router
from app.api.playlists import router as playlists_router
from app.api.profiles import router as profiles_router
from app.api.testing import router as testing_router
from app.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(performance_router)
app.include_router(export_router)
app.include_router(playlists_router)
app.include_router(profiles_router)
app.include_router(testing_router)

_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
app.mount("/frontend", StaticFiles(directory=_FRONTEND), name="frontend")


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(_FRONTEND / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

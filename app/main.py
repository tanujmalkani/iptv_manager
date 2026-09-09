from fastapi import FastAPI

from app.api.performance import router as performance_router
from app.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(performance_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

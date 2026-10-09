from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router
from app.config import Settings
from app.database import Database
from app.services.jobs import AppContext


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    database = Database(Path(settings.database_path))
    database.initialize()
    storage_dir = Path(settings.storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)

    application = FastAPI(
        title="Bulk Certificate Generator",
        version="1.0.0",
        description="Create and retrieve bulk PDF certificate generation jobs.",
    )
    application.state.context = AppContext(
        database=database,
        storage_dir=storage_dir,
        max_recipients_per_job=settings.max_recipients_per_job,
    )
    application.include_router(router)

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()


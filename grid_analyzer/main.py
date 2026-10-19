from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from grid_analyzer import __version__
from grid_analyzer.api.routes import router
from grid_analyzer.config import get_settings
from grid_analyzer.logging import configure_logging

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger("grid_analyzer.http")

    app = FastAPI(title="A股网格交易参数分析器", version=__version__)

    @app.middleware("http")
    async def add_no_cache_headers(request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        logger.info(
            "%s %s -> %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    app.include_router(router)

    @app.get("/", response_class=HTMLResponse)
    def index():
        idx = PROJECT_ROOT / "index.html"
        if idx.exists():
            return HTMLResponse(idx.read_text(encoding="utf-8"))
        return {"message": "A股网格交易参数分析器后端运行中，请将 index.html 放在项目根目录"}

    return app


app = create_app()

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from grid_analyzer import __version__
from grid_analyzer.api.routes import router
from grid_analyzer.config import get_settings
from grid_analyzer.logging import configure_logging

WEB_ROOT = Path(__file__).resolve().parent / "web"


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
    app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        idx = WEB_ROOT / "index.html"
        if idx.exists():
            return HTMLResponse(idx.read_text(encoding="utf-8"))
        return {"message": "A股网格交易参数分析器后端运行中，缺少前端资源"}

    return app


app = create_app()

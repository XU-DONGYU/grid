from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4


class JobManager:
    """Small in-process job registry for long-running research tasks."""

    def __init__(self, max_workers: int = 2, max_jobs: int = 20) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        job_id = uuid4().hex
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._prune_locked()
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "result": None,
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
        self._executor.submit(self._run, job_id, fn, args, kwargs)
        return job_id

    def _run(
        self,
        job_id: str,
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        self._update(job_id, status="running")
        try:
            result = fn(*args, **kwargs)
            self._update(job_id, status="completed", result=result)
        except Exception as exc:
            self._update(
                job_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(changes)
            job["updated_at"] = datetime.now().isoformat(timespec="seconds")

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _prune_locked(self) -> None:
        if len(self._jobs) < self._max_jobs:
            return
        finished = [
            job_id
            for job_id, job in self._jobs.items()
            if job["status"] in {"completed", "failed"}
        ]
        for job_id in finished[: max(0, len(self._jobs) - self._max_jobs + 1)]:
            self._jobs.pop(job_id, None)


job_manager = JobManager()

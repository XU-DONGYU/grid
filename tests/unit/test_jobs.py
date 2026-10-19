from __future__ import annotations

import time

from grid_analyzer.services.jobs import JobManager


def wait_for(manager: JobManager, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = manager.get(job_id)
        if job and job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_job_success() -> None:
    manager = JobManager(max_workers=1, max_jobs=5)
    job_id = manager.submit(lambda value: value * 2, 21)
    job = wait_for(manager, job_id)
    assert job["status"] == "completed"
    assert job["result"] == 42
    assert job["error"] is None


def test_job_failure() -> None:
    def boom() -> None:
        raise RuntimeError("boom")

    manager = JobManager(max_workers=1, max_jobs=5)
    job_id = manager.submit(boom)
    job = wait_for(manager, job_id)
    assert job["status"] == "failed"
    assert "RuntimeError" in job["error"]

"""Public Job HTTP routes."""

from fastapi import APIRouter, HTTPException

from ...schema import JobInfo, Response


def create_jobs_router(app, public_jobs) -> APIRouter:
    """Expose the existing health and public Job contract."""
    router = APIRouter()

    @router.get("/health")
    async def health():
        return {"running": app.is_started}

    @router.get("/jobs", response_model=list[JobInfo])
    async def list_jobs():
        return [job.info for job in public_jobs.values()]

    @router.post("/jobs/{name}", response_model=Response)
    async def run_job(name: str, arguments: dict):
        if name not in public_jobs:
            raise HTTPException(404, "Unknown job")
        try:
            return await app.run_job(name, **arguments)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return router

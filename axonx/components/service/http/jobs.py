"""Public Job HTTP routes."""

from fastapi import APIRouter

from ....schema import JobInfo, Response
from .errors import InvalidArgumentsError, UnknownJobError


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
            raise UnknownJobError("Unknown job")
        try:
            return await app.run_job(name, **arguments)
        except ValueError as exc:
            raise InvalidArgumentsError(str(exc)) from exc

    return router

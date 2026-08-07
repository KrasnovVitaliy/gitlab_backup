"""HTTP surface: health check, last-run status, manual trigger, Swagger UI at /docs."""

from fastapi import BackgroundTasks, FastAPI, status

from ..backup import BackupService
from .schemas import HealthResponse, RunTriggerResponse, StatusResponse


def create_app(service: BackupService) -> FastAPI:
    app = FastAPI(
        title="gitlab-backup",
        description="Daily incremental mirror backup of GitLab groups/projects.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["health"], summary="Liveness check")
    def healthz() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/status", response_model=StatusResponse, tags=["backup"], summary="Last backup run status")
    def get_status() -> StatusResponse:
        return StatusResponse(**service.status())

    @app.post(
        "/backup/run",
        response_model=RunTriggerResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["backup"],
        summary="Trigger a backup run manually",
    )
    def trigger_run(background_tasks: BackgroundTasks) -> RunTriggerResponse:
        # Runs in Starlette's threadpool, so this returns immediately even
        # though a pass over hundreds of repos can take a while; the lock in
        # BackupService keeps it from overlapping a scheduled run.
        background_tasks.add_task(service.run_once)
        return RunTriggerResponse(status="scheduled")

    return app

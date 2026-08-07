"""Response models for the HTTP API, so /docs shows real schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class RunTriggerResponse(BaseModel):
    status: str


class FailureDetail(BaseModel):
    project: str
    error: str | None = None


class LastRunSummary(BaseModel):
    total: int
    succeeded: int
    failed: int
    failures: list[FailureDetail]


class StatusResponse(BaseModel):
    running: bool
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_run: LastRunSummary | None = None

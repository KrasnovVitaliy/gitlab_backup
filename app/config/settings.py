"""Application settings, built on pydantic-settings.

Precedence (highest to lowest): explicit init kwargs -> environment variables
-> config.yml -> defaults. This means every value in config.yml can be
overridden by an env var without touching the file, which is how the GitLab
API token is meant to be supplied (see `AppConfig.gitlab_api_token` below) —
it deliberately has no field in `GitLabConfig`/config.yml at all.
"""

import os
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

DEFAULT_CONFIG_FILE = "/app/config.yml"


class GitLabConfig(BaseModel):
    url: str
    verify_ssl: bool = True


class BackupConfig(BaseModel):
    root_dir: str = "/backups"
    parallel_workers: int = 8
    include_subgroups: bool = True
    include_archived: bool = False
    clone_timeout: int = 600
    retries: int = 2
    prune_removed: bool = False


class ScheduleConfig(BaseModel):
    enabled: bool = True
    type: Literal["cron", "interval"] = "cron"
    cron: str | None = "0 2 * * *"
    interval_minutes: int | None = None
    timezone: str = "UTC"
    run_on_start: bool = True

    @model_validator(mode="after")
    def _check_required_fields(self) -> "ScheduleConfig":
        if self.type == "cron" and not self.cron:
            raise ValueError("schedule.cron is required when schedule.type is 'cron'")
        if self.type == "interval" and not self.interval_minutes:
            raise ValueError("schedule.interval_minutes is required when schedule.type is 'interval'")
        return self


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str | None = None


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AppConfig(BaseSettings):
    """Top-level config, assembled from config.yml with env var overrides."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    gitlab: GitLabConfig
    groups: list[str | int]
    backup: BackupConfig = BackupConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    logging: LoggingConfig = LoggingConfig()
    server: ServerConfig = ServerConfig()

    # GitLab access token, used both for the REST API (listing groups/projects)
    # and, embedded in the HTTPS clone URL, for the actual git clone/fetch -
    # a single secret needs `read_api` + `read_repository` scope. Deliberately
    # not nested under `gitlab` / not settable from config.yml, so it never
    # ends up on disk. Set it via the GITLAB_API_TOKEN environment variable.
    gitlab_api_token: SecretStr = Field(validation_alias="GITLAB_API_TOKEN")

    @field_validator("groups")
    @classmethod
    def _groups_not_empty(cls, v: list[str | int]) -> list[str | int]:
        if not v:
            raise ValueError("'groups' list must not be empty")
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_file = os.environ.get("CONFIG_FILE", DEFAULT_CONFIG_FILE)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_file),
            file_secret_settings,
        )

    @classmethod
    def load(cls, path: str) -> "AppConfig":
        """Load config.yml from `path`, with env vars taking precedence."""
        os.environ["CONFIG_FILE"] = path
        return cls()

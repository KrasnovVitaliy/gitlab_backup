# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A long-running service that mirror-backs-up GitLab projects across one or more groups
(including subgroups, hundreds of repos each) to bare `.git` mirrors on disk. First run per
project is `git clone --mirror`; every later run is `git remote set-url` + `git fetch --prune`
(incremental, no re-clone). Runs as a Docker service with a built-in scheduler and a small
HTTP API — no external cron required.

## Commands

Package manager is `uv`; the project is a virtual (`tool.uv.package = false`) non-installable
app, run as `python -m app.main`, not imported as a library.

```bash
uv sync                                                        # install deps into .venv
GITLAB_API_TOKEN=... uv run python -m app.main --config config.yml --once   # one local run
uv add <package>            # add a runtime dependency (pyproject.toml + uv.lock)
uv add --dev <package>      # add a dev dependency ([dependency-groups].dev)
uv lock --upgrade           # re-resolve within existing constraints
```

Lint/format (ruff config lives in `[tool.ruff]` in `pyproject.toml`, line-length 120,
rules E/F/UP/B/SIM/I):

```bash
make lint      # uv run ruff check app/
make format    # uv run ruff format app/
```

Docker lifecycle (`make help` for the full list):

```bash
make up               # docker compose up --build (foreground)
make run-once          # docker compose run --rm gitlab-backup --once
make down / restart
make logs / shell
make build             # docker build, tags :latest and :<version>
```

Versioning is also `uv`-driven and writes both `pyproject.toml` and `uv.lock`:

```bash
make version | bump-patch-version | bump-minor-version | bump-major-version
```

There is no test suite in this repo yet.

## Architecture

One package per responsibility under `app/`, wired together only in `app/main.py`:

- `config/settings.py` — `AppConfig` (pydantic-settings). Precedence is env vars > `config.yml`
  > defaults, with `env_nested_delimiter="__"` (e.g. `BACKUP__PARALLEL_WORKERS=20`). The yaml
  path isn't fixed at class-definition time: `settings_customise_sources` reads it from the
  `CONFIG_FILE` env var at call time, and `AppConfig.load(path)` sets that env var before
  constructing the instance. `gitlab_api_token` is deliberately a top-level field with
  `validation_alias="GITLAB_API_TOKEN"` (a `SecretStr`), not nested under `gitlab`/settable
  from yaml, so the token can never end up on disk.
- `gitlab_api/client.py` — `GitLabClient` talks to the GitLab REST API only, to resolve
  configured groups (paths or numeric ids) into a deduplicated `ProjectInfo` list
  (`include_subgroups` recurses; projects reachable through more than one configured group are
  only kept once, by project id).
- `backup/mirror.py` — `RepoMirror` does the actual `git` work for one project. There is no SSH
  key anywhere: the same access token used for the API is embedded as HTTP basic auth
  (`oauth2:<token>@host`) into the HTTPS clone URL, so a single secret covers both API and git
  transport. Any git output is passed through `_redact()` before it's logged or raised, since
  git error messages can echo the URL (and thus the token) back verbatim.
- `backup/runner.py` — `BackupRunner` fans the per-project `RepoMirror.sync()` calls out across
  a `ThreadPoolExecutor(max_workers=backup.parallel_workers)` and logs a per-project result plus
  a run summary. `backup.prune_removed` (default off) deletes local mirrors whose project no
  longer shows up in discovery.
- `backup/service.py` — `BackupService` wraps `BackupRunner` with a non-blocking
  `threading.Lock` and last-run bookkeeping. This is the one entry point both the scheduler and
  the HTTP API call, so a manual trigger can never overlap a scheduled run (or another manual
  trigger) — the second caller is skipped rather than queued.
- `scheduler/scheduler.py` — `BackupScheduler` wraps APScheduler's `BackgroundScheduler` (runs
  in its own thread, not the main one) so `start()` returns immediately. `run_on_start` schedules
  an immediate one-off `date` job rather than blocking synchronously before the recurring job is
  added.
- `api/server.py` + `api/schemas.py` — `create_app(service)` builds a FastAPI app:
  `GET /healthz`, `GET /status` (last-run summary), `POST /backup/run` (202, runs in Starlette's
  threadpool via `BackgroundTasks` so it doesn't block the event loop even for a long pass), and
  auto docs at `/docs` (Swagger), `/redoc`, `/openapi.json`.
- `main.py` — wiring plus the process model: if `--once`, run synchronously and exit (no
  scheduler, no HTTP server — pure batch mode for external cron). Otherwise, start
  `BackupScheduler` in the background (only if `schedule.enabled`) and call `uvicorn.run(...)` on
  the main thread — uvicorn is the actual foreground/blocking process, listening on
  `server.host`/`server.port` from config. `log_config=None` keeps uvicorn from overriding the
  stdlib `logging` setup done in `logging_setup.py`.

Docker: runs as a fixed non-root user (uid/gid `10001`, `appuser`) — see `Dockerfile`. The HTTP
port must stay in sync in three places: `config.yml` (`server.port`), `docker-compose.yml`'s
`ports:` mapping, and the `SERVER__PORT` env override — `docker-compose.yml` derives all of them
from a single `SERVER_PORT` value in `.env` so they can't drift apart.

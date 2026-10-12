# gitlab_backup

Сервис ежедневного бэкапа репозиториев из нескольких групп GitLab (включая
подгруппы) в виде bare mirror-репозиториев. Первый запуск по каждому проекту —
`git clone --mirror`, все последующие — `git fetch --prune` (инкрементально,
без переклона).

## Структура

```
app/
  main.py             — точка входа, CLI (--config, --once)
  logging_setup.py    — настройка стандартного logging (только stdout)

  config/
    settings.py       — AppConfig на pydantic-settings: config.yml + env-переменные

  gitlab_api/
    client.py         — GitLabClient: обход групп/подгрупп через python-gitlab
    models.py         — ProjectInfo

  backup/
    mirror.py         — RepoMirror: clone/fetch/remove одного репозитория
    runner.py         — BackupRunner: параллельный прогон всех репозиториев
    models.py         — BackupResult

  backup/
    service.py         — BackupService: единая точка запуска для scheduler и HTTP API
                          (лок от параллельных прогонов, статус последнего запуска)

  scheduler/
    scheduler.py       — BackupScheduler: встроенный планировщик (APScheduler,
                          работает в фоновом потоке)

  api/
    server.py          — create_app(): FastAPI-приложение (healthz/status/run),
                          поднимается через uvicorn в main.py

config.yml            — конфигурация (группы, расписание, параллелизм, http-порт)
pyproject.toml / uv.lock — зависимости и версия сервиса, управляются uv
Makefile               — сборка образа, версии, запуск (make help)
Dockerfile / docker-compose.yml
```

Каждый подпакет — одна зона ответственности: `gitlab_api` знает только про
удалённый GitLab, `backup` — про локальное зеркалирование, `config` — про
настройки, `scheduler` — про тайминг запуска. `main.py` их просто связывает.

## Конфигурация (pydantic-settings)

`AppConfig` (`app/config/settings.py`) собирается из `config.yml` и
переменных окружения, причём **env всегда переопределяет yaml**. Любое
значение можно переопределить env-переменной без правки файла — вложенность
через двойное подчёркивание, например `BACKUP__PARALLEL_WORKERS=20`.

## Аутентификация

Один секрет на всё — Personal/Project/Group Access Token со scope
`read_api` + `read_repository`:

- используется `GitLabClient` для REST API (получить список групп/проектов);
- используется `RepoMirror` для самого `git clone`/`fetch` — встраивается как
  HTTP basic auth (`oauth2:<token>@...`) в HTTPS-адрес клонирования, отдельный
  SSH-ключ не нужен. Перед логированием/исключениями токен вычищается из
  вывода git (`RepoMirror._redact`), чтобы не утёк в логи при ошибке.

Поля в `config.yml` для токена намеренно нет — он читается только из
переменной окружения `GITLAB_API_TOKEN` (`AppConfig.gitlab_api_token`, тип
`SecretStr`, чтобы не засветить его в логах/репрах). Передаётся через `.env`
(см. `.env.example`) — секрет никогда не лежит в файле в открытом виде.

Так как токен теперь используется и для клонирования, при ротации токена
обновление подхватится автоматически на следующем прогоне (`RepoMirror`
каждый раз переустанавливает `remote.origin.url` перед `fetch`).

## Настройка

1. Скопируйте `.env.example` → `.env`, впишите токен.
2. Отредактируйте `config.yml`: URL инстанса, список `groups`,
   `parallel_workers`, `schedule.cron`.

Контейнер работает от непривилегированного пользователя (`appuser`, не
root) — секретов-файлов с bind-mount больше нет, так что никаких
дополнительных прав/UID согласовывать не нужно.

## HTTP API

Сервис — теперь долгоживущий процесс: `main.py` поднимает встроенный
планировщик в фоновом потоке и держит `uvicorn` на переднем плане
(слушает `server.host:server.port` из `config.yml`, по умолчанию
`0.0.0.0:8080`).

- `GET /healthz` — liveness-проверка (`{"status": "ok"}`).
- `GET /status` — статус и итоги последнего прогона (успехи/провалы по
  каждому упавшему проекту).
- `POST /backup/run` — запустить прогон вручную, не дожидаясь расписания
  (202 Accepted, выполняется в фоне; если прогон уже идёт — пропускается,
  `BackupService` не даёт двум прогонам пересечься).
- `GET /docs` — Swagger UI (интерактивная документация всех эндпоинтов выше,
  со схемами ответов из `app/api/schemas.py`); `GET /redoc` — то же в виде
  ReDoc; `GET /openapi.json` — сырая OpenAPI-схема.

Порт наружу пробрасывается в `docker-compose.yml` (`ports:`), значение
берётся из `SERVER_PORT` в `.env` (по умолчанию 8080) и используется сразу
и для публикации порта, и для `server.port` внутри контейнера — поменяли
одну переменную, и хост, и приложение слушают один и тот же порт.
`--once` (разовый прогон, например из внешнего cron) HTTP-сервер вообще не
поднимает — это чисто batch-режим.

## Запуск

Через `make` (`make help` — полный список целей):

```bash
make up          # собрать образ и запустить сервис (на переднем плане, Ctrl+C — стоп)
make run-once    # разовый прогон бэкапа, без ожидания расписания
make down        # остановить и убрать контейнер
```

`make up` запускает `docker compose up --build` без `-d`, то есть в
терминале сразу видны логи; чтобы освободить терминал, добавьте `-d`
(`docker compose up -d --build`) или откройте логи отдельно —
`docker compose logs -f`.

После `make up` (или `docker compose up`) проверка, что сервис поднялся:

```bash
curl http://127.0.0.1:8080/healthz
```

Управление версией (пишет в `pyproject.toml`/`uv.lock`, `make build`
тегирует образ этой версией и `latest`):

```bash
make version              # текущая версия
make bump-patch-version   # 0.1.0 -> 0.1.1
make bump-minor-version   # 0.1.1 -> 0.2.0
make bump-major-version   # 0.2.0 -> 1.0.0
make build                # docker build + tag :latest и :<версия>
```

Эквивалентные команды напрямую через `docker compose`, если `make` не нужен:

```bash
docker compose up -d --build
docker compose logs -f
docker compose run --rm gitlab-backup --once
```

Локально без Docker (для отладки), зависимости ставятся через
[uv](https://docs.astral.sh/uv/):

```bash
uv sync
GITLAB_API_TOKEN=... uv run python -m app.main --config config.yml --once
```

Добавить/обновить зависимость:

```bash
uv add <package>          # обычная зависимость - правит pyproject.toml и uv.lock
uv add --dev <package>    # dev-зависимость (например, линтер) - идёт в [dependency-groups].dev
uv lock --upgrade         # обновить версии в рамках текущих ограничений
```

`uv.lock` закоммичен в репозиторий — им же пользуется `Dockerfile`
(`uv sync --frozen`), так что в контейнере и локально всегда одинаковые версии.

## Линтинг

Правила и настройки — в `[tool.ruff]` в `pyproject.toml`, сам `ruff` — dev-зависимость:

```bash
make lint      # uv run ruff check app/
make format    # uv run ruff format app/
```

## Поведение

- Группы обходятся рекурсивно (`include_subgroups: true`), проекты,
  попавшие в несколько групп сразу, бэкапятся один раз.
- Число одновременных `git clone/fetch` задаётся `backup.parallel_workers`.
- Расписание встроено в сервис (APScheduler), внешний cron не нужен —
  контейнер просто должен работать постоянно (`restart: unless-stopped`).
- `backup.prune_removed: true` удаляет с диска зеркала проектов, которые
  пропали из GitLab (переименованы/удалены/потеряли доступ) — по умолчанию
  выключено, чтобы ничего не удалялось молча.
- Каждый прогон логирует построчный результат и итоговую сводку
  (успех/провал) через стандартный `logging`, вывод идёт только в stdout
  (смотреть через `docker compose logs`).

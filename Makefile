-include .env
export

DOCKER := docker
BUILD := buildx build
COMPOSE := docker compose
UV_RUN := uv run

IMAGE_NAME := gitlab-backup
IMAGE := $(DOCKER_IMAGE_REGISTRY)/$(IMAGE_NAME)
VERSION := $(shell uv version --short)

# Target platform of the built image. Production runs on linux/amd64, so this is
# the default on any host, including Apple Silicon (built via emulation there).
# Override per call, e.g. `make docker-build PLATFORM=linux/arm64`.
PLATFORM ?= linux/amd64

.PHONY: help
help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sed 's/Makefile://' | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[32m%-20s\033[0m %s\n", $$1, $$2}'

## --- Versioning --------------------------------------------------------

.PHONY: version
version: ## Print the current version
	@uv version --short

.PHONY: bump-patch-version
bump-patch-version: ## Bump patch version (x.y.Z++), e.g. bugfixes
	@uv version --bump patch

.PHONY: bump-minor-version
bump-minor-version: ## Bump minor version (x.Y++.0), e.g. new features
	@uv version --bump minor

.PHONY: bump-major-version
bump-major-version: ## Bump major version (X++.0.0), e.g. breaking changes
	@uv version --bump major

## --- Docker image --------------------------------------------------------

.PHONY: docker-build
docker-build: ## Build the docker image (linux/amd64 by default), tagged 'latest' and with the current version
	$(DOCKER) $(BUILD) --platform $(PLATFORM) --load -t $(IMAGE):latest -t $(IMAGE):$(VERSION) .

.PHONY: docker-push
docker-push: docker-build ## Push the image to DOCKER_IMAGE_REGISTRY (run 'docker login' first)
	$(DOCKER) push $(IMAGE):$(VERSION)
	$(DOCKER) push $(IMAGE):latest

## --- Service lifecycle ----------------------------------------------------

.PHONY: up
up: ## Start the service (builds the image first)
	$(COMPOSE) up --build

.PHONY: down
down: ## Stop and remove the service
	$(COMPOSE) down

.PHONY: restart
restart: down up ## Restart the service

.PHONY: run-once
run-once: ## Run a single backup pass and exit, ignoring the built-in scheduler
	$(COMPOSE) run --rm $(IMAGE_NAME) --once

.PHONY: logs
logs: ## Follow service logs
	$(COMPOSE) logs -f

.PHONY: shell
shell: ## Open a shell inside the running container
	$(COMPOSE) exec $(IMAGE_NAME) sh

## --- Code quality ----------------------------------------------------------

.PHONY: lint
lint: ## Run ruff lint checks
	$(UV_RUN) ruff check app/

.PHONY: format
format: ## Format code with ruff
	$(UV_RUN) ruff format app/

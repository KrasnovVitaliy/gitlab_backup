-include .env
export

DOCKER := docker
COMPOSE := docker compose
UV_RUN := uv run

IMAGE_NAME := gitlab-backup
VERSION := $(shell uv version --short)

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

.PHONY: build
build: ## Build the docker image, tagged 'latest' and with the current version
	$(COMPOSE) build
	$(DOCKER) tag $(IMAGE_NAME):latest $(IMAGE_NAME):$(VERSION)

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

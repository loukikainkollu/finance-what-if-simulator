SHELL := /bin/bash

# Project shortcuts for Docker-based deployment

.PHONY: up down logs ps rebuild backend-logs frontend-logs db-logs

up:
	@docker compose up -d --build

down:
	@docker compose down

logs:
	@docker compose logs -f --tail=200

ps:
	@docker compose ps

rebuild:
	@docker compose build --no-cache

backend-logs:
	@docker compose logs -f backend

frontend-logs:
	@docker compose logs -f frontend

db-logs:
	@docker compose logs -f db
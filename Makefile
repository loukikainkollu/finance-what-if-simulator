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

# -----------------------------
# Production/Staging Deployment
# -----------------------------

.PHONY: prod-up prod-down prod-logs prod-ps prod-rebuild prod-nginx-reload prod-certbot-init prod-certbot-renew

# Use .env.deploy for DOMAIN and LETSENCRYPT_EMAIL
prod-up:
	@docker compose --env-file .env.deploy -f docker-compose.prod.yml up -d --build

prod-down:
	@docker compose --env-file .env.deploy -f docker-compose.prod.yml down

prod-logs:
	@docker compose --env-file .env.deploy -f docker-compose.prod.yml logs -f --tail=200

prod-ps:
	@docker compose --env-file .env.deploy -f docker-compose.prod.yml ps

prod-rebuild:
	@docker compose --env-file .env.deploy -f docker-compose.prod.yml build --no-cache

# Reload nginx inside the prod stack
prod-nginx-reload:
	@docker exec -it financehelper-nginx-prod nginx -s reload || true

# Initialize Let's Encrypt certificates for production domain
# Requires HTTP(80) to be reachable for ACME webroot
prod-certbot-init:
	@set -a; source .env.deploy; set +a; \
	docker compose --env-file .env.deploy -f docker-compose.prod.yml run --rm certbot certonly \
	  --webroot -w /var/www/certbot \
	  -d $$DOMAIN -d www.$$DOMAIN \
	  --email $$LETSENCRYPT_EMAIL --agree-tos --non-interactive --rsa-key-size 4096 || true; \
	docker compose --env-file .env.deploy -f docker-compose.prod.yml exec -T nginx nginx -s reload || true

# Renew certificates and reload nginx
prod-certbot-renew:
	@docker compose --env-file .env.deploy -f docker-compose.prod.yml run --rm certbot renew --webroot -w /var/www/certbot || true
	@docker compose --env-file .env.deploy -f docker-compose.prod.yml exec -T nginx nginx -s reload || true

.PHONY: staging-up staging-down staging-logs staging-ps staging-rebuild staging-nginx-reload staging-certbot-init staging-certbot-renew

staging-up:
	@docker compose --env-file .env.deploy -f docker-compose.staging.yml up -d --build

staging-down:
	@docker compose --env-file .env.deploy -f docker-compose.staging.yml down

staging-logs:
	@docker compose --env-file .env.deploy -f docker-compose.staging.yml logs -f --tail=200

staging-ps:
	@docker compose --env-file .env.deploy -f docker-compose.staging.yml ps

staging-rebuild:
	@docker compose --env-file .env.deploy -f docker-compose.staging.yml build --no-cache

staging-nginx-reload:
	@docker exec -it financehelper-nginx-staging nginx -s reload || true

# Initialize Let's Encrypt for staging domain (typically no www for subdomains)
staging-certbot-init:
	@set -a; source .env.deploy; set +a; \
	docker compose --env-file .env.deploy -f docker-compose.staging.yml run --rm certbot certonly \
	  --webroot -w /var/www/certbot \
	  -d $$DOMAIN \
	  --email $$LETSENCRYPT_EMAIL --agree-tos --non-interactive --rsa-key-size 4096 || true; \
	docker compose --env-file .env.deploy -f docker-compose.staging.yml exec -T nginx nginx -s reload || true

staging-certbot-renew:
	@docker compose --env-file .env.deploy -f docker-compose.staging.yml run --rm certbot renew --webroot -w /var/www/certbot || true
	@docker compose --env-file .env.deploy -f docker-compose.staging.yml exec -T nginx nginx -s reload || true

# Convenience: Tail nginx logs
.PHONY: nginx-logs-prod nginx-logs-staging
nginx-logs-prod:
	@docker logs -f financehelper-nginx-prod || true

nginx-logs-staging:
	@docker logs -f financehelper-nginx-staging || true
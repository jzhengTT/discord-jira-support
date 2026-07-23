.PHONY: help setup build up down logs restart status clean test

help:
	@echo "discord-jira-support Docker Compose management"
	@echo ""
	@echo "  setup    - Copy .env.example to .env (then fill in secrets)"
	@echo "  build    - Build the Docker image"
	@echo "  up       - Start the bot (detached)"
	@echo "  down     - Stop the bot"
	@echo "  logs     - Follow bot logs"
	@echo "  restart  - Restart the bot"
	@echo "  status   - Show container status"
	@echo "  test     - Run the unit tests in Docker"
	@echo "  clean    - Remove containers and networks"

setup:
	cp -n .env.example .env && echo "Created .env — fill in the secrets" || echo ".env already exists"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose restart

status:
	docker compose ps

test:
	docker compose run --rm -v $(PWD)/tests:/app/tests -v $(PWD)/pyproject.toml:/app/pyproject.toml bot python -m pytest -q

clean:
	docker compose down --remove-orphans

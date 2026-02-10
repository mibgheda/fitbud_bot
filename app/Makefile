.PHONY: help build up down restart logs logs-bot logs-db shell shell-db backup restore clean

help: ## Показать справку
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Собрать образы
	docker compose build

up: ## Запустить контейнеры
	docker compose up -d

down: ## Остановить контейнеры
	docker compose down

restart: ## Перезапустить контейнеры
	docker compose restart

logs: ## Показать логи всех контейнеров
	docker compose logs -f

logs-bot: ## Показать логи бота
	docker compose logs -f bot

logs-db: ## Показать логи БД
	docker compose logs -f postgres

ps: ## Показать статус контейнеров
	docker compose ps

shell: ## Войти в контейнер бота
	docker compose exec bot /bin/bash

shell-db: ## Войти в контейнер PostgreSQL
	docker compose exec postgres /bin/bash

psql: ## Подключиться к БД через psql
	docker compose exec postgres psql -U fitbud_user -d fitbud_bot

backup: ## Создать бэкап БД
	@echo "Создание бэкапа..."
	@mkdir -p backups
	docker compose exec postgres pg_dump -U fitbud_user fitbud_bot > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Бэкап создан в директории backups/"

restore: ## Восстановить БД из бэкапа (использование: make restore FILE=backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "Укажите файл бэкапа: make restore FILE=backups/backup_20240209.sql"; \
		exit 1; \
	fi
	@echo "Восстановление из $(FILE)..."
	cat $(FILE) | docker compose exec -T postgres psql -U fitbud_user -d fitbud_bot
	@echo "Восстановление завершено"

clean: ## Удалить контейнеры и volumes (УДАЛИТ БД!)
	docker compose down -v

rebuild: ## Пересобрать и перезапустить
	docker compose up -d --build

update: ## Обновить код и перезапустить
	git pull
	docker compose up -d --build

migrate: ## Применить миграции БД
	docker compose exec bot alembic upgrade head

migrate-create: ## Создать новую миграцию (использование: make migrate-create MSG="название")
	@if [ -z "$(MSG)" ]; then \
		echo "Укажите название миграции: make migrate-create MSG='add user settings'"; \
		exit 1; \
	fi
	docker compose exec bot alembic revision --autogenerate -m "$(MSG)"

migrate-downgrade: ## Откатить последнюю миграцию
	docker compose exec bot alembic downgrade -1

migrate-history: ## Показать историю миграций
	docker compose exec bot alembic history

migrate-current: ## Показать текущую версию БД
	docker compose exec bot alembic current

stats: ## Показать использование ресурсов
	docker stats

prune: ## Очистить неиспользуемые ресурсы Docker
	docker system prune -a

dev: ## Запустить в режиме разработки (с выводом логов)
	docker compose up

prod: ## Запустить в production режиме
	docker compose up -d --build

stop-bot: ## Остановить только бота
	docker compose stop bot

start-bot: ## Запустить только бота
	docker compose start bot

restart-bot: ## Перезапустить только бота
	docker compose restart bot

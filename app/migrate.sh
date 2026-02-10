#!/bin/bash

# Скрипт управления миграциями БД через Alembic

set -e

COMMAND=${1:-help}

case "$COMMAND" in
    init)
        echo "🔧 Инициализация Alembic (уже выполнено в проекте)"
        echo "Структура миграций готова к использованию"
        ;;
    
    upgrade)
        echo "⬆️  Применение миграций к БД..."
        docker compose exec bot alembic upgrade head
        echo "✅ Миграции применены"
        ;;
    
    downgrade)
        STEPS=${2:-1}
        echo "⬇️  Откат миграций на $STEPS шаг(ов)..."
        docker compose exec bot alembic downgrade -$STEPS
        echo "✅ Откат выполнен"
        ;;
    
    history)
        echo "📜 История миграций:"
        docker compose exec bot alembic history
        ;;
    
    current)
        echo "📍 Текущая версия БД:"
        docker compose exec bot alembic current
        ;;
    
    create)
        if [ -z "$2" ]; then
            echo "❌ Укажите название миграции"
            echo "Пример: ./migrate.sh create 'add user settings'"
            exit 1
        fi
        echo "📝 Создание новой миграции: $2"
        docker compose exec bot alembic revision --autogenerate -m "$2"
        echo "✅ Миграция создана в alembic/versions/"
        ;;
    
    local-upgrade)
        echo "⬆️  Применение миграций (локально, без Docker)..."
        alembic upgrade head
        echo "✅ Миграции применены"
        ;;
    
    local-create)
        if [ -z "$2" ]; then
            echo "❌ Укажите название миграции"
            echo "Пример: ./migrate.sh local-create 'add user settings'"
            exit 1
        fi
        echo "📝 Создание новой миграции: $2"
        alembic revision --autogenerate -m "$2"
        echo "✅ Миграция создана в alembic/versions/"
        ;;
    
    help|*)
        echo "🔄 Управление миграциями БД через Alembic"
        echo ""
        echo "Использование: ./migrate.sh [команда] [параметры]"
        echo ""
        echo "Команды для Docker:"
        echo "  upgrade           - Применить все миграции"
        echo "  downgrade [N]     - Откатить N миграций (по умолчанию 1)"
        echo "  current           - Показать текущую версию БД"
        echo "  history           - Показать историю миграций"
        echo "  create 'название' - Создать новую миграцию"
        echo ""
        echo "Команды для локальной установки (без Docker):"
        echo "  local-upgrade     - Применить все миграции"
        echo "  local-create      - Создать новую миграцию"
        echo ""
        echo "Примеры:"
        echo "  ./migrate.sh upgrade"
        echo "  ./migrate.sh create 'add user preferences'"
        echo "  ./migrate.sh downgrade 2"
        echo "  ./migrate.sh history"
        ;;
esac

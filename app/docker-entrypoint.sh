#!/bin/bash

# Entrypoint скрипт для контейнера бота
# Применяет миграции перед запуском

set -e

echo "🔍 Проверка подключения к базе данных..."

# Ждем, пока PostgreSQL будет готов
max_tries=30
count=0
until PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; do
  count=$((count + 1))
  if [ $count -ge $max_tries ]; then
    echo "❌ Не удалось подключиться к БД после $max_tries попыток"
    exit 1
  fi
  echo "⏳ Ожидание PostgreSQL... (попытка $count/$max_tries)"
  sleep 2
done

echo "✅ База данных доступна"

echo "🔄 Применение миграций Alembic..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ Миграции применены успешно"
else
    echo "❌ Ошибка применения миграций"
    exit 1
fi

echo "🚀 Запуск бота..."
exec python main.py

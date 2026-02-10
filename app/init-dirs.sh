#!/bin/bash

# Скрипт инициализации структуры проекта

set -e

echo "📁 Создание структуры директорий..."

# Создаем директории для данных
mkdir -p data/postgres
mkdir -p data/media/voice
mkdir -p data/media/photos
mkdir -p backups

# Устанавливаем права
chmod -R 755 data
chmod -R 755 backups

echo "✅ Директории созданы:"
echo "   data/postgres     - База данных PostgreSQL"
echo "   data/media/voice  - Голосовые сообщения"
echo "   data/media/photos - Фотографии еды"
echo "   backups/          - Бэкапы БД"

# Создаем .gitkeep файлы для сохранения структуры в Git
touch data/.gitkeep
touch backups/.gitkeep

echo ""
echo "💡 Совет: Добавьте в Git только структуру:"
echo "   git add data/.gitkeep backups/.gitkeep"
echo ""
echo "Данные в этих папках игнорируются через .gitignore"

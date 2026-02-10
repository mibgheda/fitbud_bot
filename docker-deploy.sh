#!/bin/bash

# Скрипт быстрого развертывания FitBud Bot в Docker

set -e

echo "🐳 Развертывание FitBud Bot в Docker..."

# Цвета
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Проверка Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker не установлен!${NC}"
    echo "Установите Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Проверка Docker Compose
if ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose не установлен!${NC}"
    echo "Установите Docker Compose Plugin"
    exit 1
fi

echo -e "${GREEN}✅ Docker и Docker Compose установлены${NC}"

# Создание структуры директорий
echo -e "${YELLOW}📁 Создание директорий для данных...${NC}"
mkdir -p data/postgres
mkdir -p data/media/voice
mkdir -p data/media/photos
mkdir -p backups
chmod -R 755 data backups

# Проверка .env файла
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Файл .env не найден. Создаю из .env.example...${NC}"
    
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}📝 Отредактируйте файл .env и добавьте BOT_TOKEN, OPENAI_API_KEY и DB_PASSWORD${NC}"
        echo -e "${YELLOW}После редактирования запустите скрипт снова${NC}"
        
        # Открываем редактор
        if command -v nano &> /dev/null; then
            nano .env
        elif command -v vim &> /dev/null; then
            vim .env
        else
            echo "Отредактируйте файл .env вручную"
        fi
        
        exit 0
    else
        echo -e "${RED}❌ Файл .env.example не найден!${NC}"
        exit 1
    fi
fi

# Загружаем переменные из .env
source .env

# Проверка обязательных переменных
if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" = "your_bot_token_here" ]; then
    echo -e "${RED}❌ BOT_TOKEN не установлен в .env файле!${NC}"
    echo "Получите токен у @BotFather в Telegram"
    exit 1
fi

if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your_openai_api_key_here" ]; then
    echo -e "${YELLOW}⚠️  OPENAI_API_KEY не установлен в .env файле${NC}"
    echo "AI функции (голос, фото, консультации) не будут работать"
    echo "Получите ключ на https://platform.openai.com/api-keys"
    read -p "Продолжить без AI? (y/n): " CONTINUE
    if [ "$CONTINUE" != "y" ]; then
        exit 1
    fi
fi

if [ -z "$DB_PASSWORD" ] || [ "$DB_PASSWORD" = "your_strong_password" ]; then
    echo -e "${RED}❌ DB_PASSWORD не установлен в .env файле!${NC}"
    echo "Установите надежный пароль для базы данных"
    exit 1
fi

echo -e "${GREEN}✅ Переменные окружения настроены${NC}"

# Выбор режима запуска
echo ""
echo "Выберите режим запуска:"
echo "1) Development (docker-compose.yml)"
echo "2) Production (docker-compose.prod.yml)"
read -p "Введите номер (1 или 2) [1]: " MODE

MODE=${MODE:-1}

if [ "$MODE" = "2" ]; then
    COMPOSE_FILE="docker-compose.prod.yml"
    echo -e "${YELLOW}🚀 Запуск в Production режиме${NC}"
else
    COMPOSE_FILE="docker-compose.yml"
    echo -e "${YELLOW}🔧 Запуск в Development режиме${NC}"
fi

# Остановка существующих контейнеров
echo -e "${YELLOW}🛑 Остановка существующих контейнеров...${NC}"
docker compose -f $COMPOSE_FILE down 2>/dev/null || true

# Сборка образов
echo -e "${YELLOW}🔨 Сборка образов...${NC}"
docker compose -f $COMPOSE_FILE build

# Запуск контейнеров
echo -e "${YELLOW}🚀 Запуск контейнеров...${NC}"
docker compose -f $COMPOSE_FILE up -d

# Ожидание запуска
echo -e "${YELLOW}⏳ Ожидание запуска сервисов...${NC}"
sleep 5

# Проверка статуса
echo -e "${YELLOW}📊 Статус контейнеров:${NC}"
docker compose -f $COMPOSE_FILE ps

# Проверка логов
echo ""
echo -e "${YELLOW}📋 Последние логи бота:${NC}"
docker compose -f $COMPOSE_FILE logs --tail=20 bot

echo ""
echo -e "${GREEN}✅ Развертывание завершено!${NC}"
echo ""
echo "📂 Структура данных:"
echo "  data/postgres/     - База данных PostgreSQL"
echo "  data/media/        - Голосовые и фото от пользователей"
echo "  backups/           - Бэкапы базы данных"
echo ""
echo "Полезные команды:"
echo "  docker compose -f $COMPOSE_FILE logs -f          # Просмотр логов"
echo "  docker compose -f $COMPOSE_FILE logs -f bot      # Логи бота"
echo "  docker compose -f $COMPOSE_FILE ps               # Статус контейнеров"
echo "  docker compose -f $COMPOSE_FILE restart          # Перезапуск"
echo "  docker compose -f $COMPOSE_FILE down             # Остановка"
echo ""
echo "Или используйте Makefile:"
echo "  make logs       # Просмотр логов"
echo "  make ps         # Статус"
echo "  make restart    # Перезапуск"
echo "  make backup     # Создать бэкап БД"
echo "  make help       # Все доступные команды"
echo ""
echo -e "${GREEN}🤖 Бот запущен! Найдите его в Telegram и отправьте /start${NC}"

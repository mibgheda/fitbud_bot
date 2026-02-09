#!/bin/bash

# Скрипт для деплоя FitBud Bot на сервер

set -e

echo "🚀 Начинаем деплой FitBud Bot..."

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Переменные
PROJECT_DIR="/opt/fitbud_bot"
SERVICE_NAME="fitbud_bot"
USER=$(whoami)

# Создание директории проекта
echo -e "${YELLOW}📁 Создаем директорию проекта...${NC}"
sudo mkdir -p $PROJECT_DIR
sudo chown $USER:$USER $PROJECT_DIR

# Копирование файлов (если запускается из репозитория)
if [ -f "main.py" ]; then
    echo -e "${YELLOW}📋 Копируем файлы проекта...${NC}"
    cp -r * $PROJECT_DIR/
fi

cd $PROJECT_DIR

# Создание виртуального окружения
echo -e "${YELLOW}🐍 Создаем виртуальное окружение...${NC}"
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
echo -e "${YELLOW}📦 Устанавливаем зависимости...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

# Проверка .env файла
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚙️  Создаем .env файл...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✅ Создан .env файл. Не забудьте заполнить его!${NC}"
    echo "Отредактируйте файл: nano $PROJECT_DIR/.env"
else
    echo -e "${GREEN}✅ Файл .env уже существует${NC}"
fi

# Создание директории для логов
echo -e "${YELLOW}📝 Создаем директорию для логов...${NC}"
sudo mkdir -p /var/log/fitbud_bot
sudo chown $USER:$USER /var/log/fitbud_bot

# Установка systemd сервиса
echo -e "${YELLOW}⚙️  Настраиваем systemd сервис...${NC}"
sudo cp fitbud_bot.service /etc/systemd/system/
sudo sed -i "s/your_user/$USER/g" /etc/systemd/system/fitbud_bot.service
sudo sed -i "s/your_group/$USER/g" /etc/systemd/system/fitbud_bot.service

# Перезагрузка systemd и запуск сервиса
echo -e "${YELLOW}🔄 Перезагружаем systemd...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable fitbud_bot

echo -e "${GREEN}✅ Деплой завершен!${NC}"
echo ""
echo "Следующие шаги:"
echo "1. Отредактируйте .env файл: nano $PROJECT_DIR/.env"
echo "2. Убедитесь, что PostgreSQL настроен и база данных создана"
echo "3. Запустите бота: sudo systemctl start fitbud_bot"
echo "4. Проверьте статус: sudo systemctl status fitbud_bot"
echo "5. Просмотр логов: sudo journalctl -u fitbud_bot -f"

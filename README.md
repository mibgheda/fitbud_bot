# FitBud Bot 🏃‍♂️

Telegram-бот для учета калорий и фитнеса с персональными рекомендациями.

## Возможности

- 🤖 Запись еды, напитков и тренировок текстом, фото или голосом — тип сообщения определяет ИИ
- 🥩 Калории, белки, жиры, углеводы, клетчатка и добавленный сахар: что добрать и что не перебрать
- ⚠️ Предупреждение, если за один приём съедено больше 40–60% дневного лимита жиров, углеводов или сахара
- 🔥 Тренировки прибавляются к норме калорий по формуле MET × вес × время
- 💧 Жидкость в мл из любых записей (суп — треть объёма), алкоголь отдельно
- 📋 «Мой день»: отчёт, исправление и удаление записей с отменой
- 🕐 Часовой пояс и время утра пользователя — граница «сегодня»
- ⏳ Лимиты: 60 запросов к ИИ и 20 фото в день на пользователя
- ⚖️ Мониторинг веса с пересчётом норм
- 👤 Профиль с ИМТ, целями и своей нормой белка

## Технологии

- Python 3.10+
- aiogram 3.x (асинхронная библиотека для Telegram Bot API)
- PostgreSQL (база данных)
- SQLAlchemy (ORM)
- asyncpg (асинхронный драйвер PostgreSQL)

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/your-username/fitbud_bot.git
cd fitbud_bot
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка PostgreSQL

```bash
# Войти в PostgreSQL
sudo -u postgres psql

# Выполнить команды:
CREATE DATABASE fitbud_bot;
CREATE USER fitbud_user WITH PASSWORD 'ваш_пароль';
GRANT ALL PRIVILEGES ON DATABASE fitbud_bot TO fitbud_user;
ALTER DATABASE fitbud_bot OWNER TO fitbud_user;
\q
```

### 5. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и заполните:

```bash
cp .env.example .env
nano .env
```

Заполните:
```
BOT_TOKEN=ваш_токен_от_BotFather
DB_NAME=fitbud_bot
DB_USER=fitbud_user
DB_PASSWORD=ваш_пароль
DB_HOST=localhost
DB_PORT=5432
```

AI-провайдер (по умолчанию OpenAI):
```
# OpenAI
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...

# или бесплатный Google Gemini (ключ: https://aistudio.google.com)
AI_PROVIDER=gemini
GEMINI_API_KEY=...

# необязательно: свои модели
# AI_MODEL_FAST=gemini-3.5-flash-lite   # еда, тренировки, голос
# AI_MODEL_SMART=gemini-3.8-flash       # рекомендации
```

### 6. Запуск бота

```bash
python main.py
```

## Структура проекта

```
fitbud_bot/
├── main.py                 # Точка входа
├── requirements.txt        # Зависимости
├── .env.example           # Пример переменных окружения
├── .gitignore             # Игнорируемые файлы
├── README.md              # Документация
├── database/
│   ├── __init__.py
│   └── database.py        # Модели и подключение к БД
├── handlers/
│   ├── __init__.py
│   ├── start.py           # Обработчик /start и настройка профиля
│   ├── calories.py        # Учет калорий
│   ├── fitness.py         # Учет тренировок
│   ├── profile.py         # Управление профилем
│   └── stats.py           # Статистика и вес
├── keyboards/
│   ├── __init__.py
│   └── reply.py           # Клавиатуры для бота
└── utils/
    └── __init__.py        # Вспомогательные функции
```

## Деплой на сервер

### Systemd сервис

Создайте файл `/etc/systemd/system/fitbud_bot.service`:

```ini
[Unit]
Description=FitBud Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/opt/fitbud_bot
Environment="PATH=/opt/fitbud_bot/venv/bin"
ExecStart=/opt/fitbud_bot/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Активация:

```bash
sudo systemctl daemon-reload
sudo systemctl enable fitbud_bot
sudo systemctl start fitbud_bot
sudo systemctl status fitbud_bot
```

## Команды бота

- `/start` - Начать работу / настроить профиль
- `/profile` - Просмотр профиля
- `/help` - Справка

## Функционал

### Добавление калорий
1. Нажмите "📊 Добавить калории"
2. Введите название блюда
3. Введите количество калорий
4. Выберите тип приема пищи

### Добавление тренировки
1. Нажмите "🏃 Добавить тренировку"
2. Выберите тип тренировки
3. Введите длительность в минутах
4. Добавьте заметки (опционально)

### Просмотр статистики
- Дневная калорийность с прогресс-баром
- Статистика по неделям и месяцам
- История тренировок
- Динамика веса

## Разработка

Для разработки рекомендуется:

1. Использовать виртуальное окружение
2. Следовать PEP 8
3. Добавлять docstrings к функциям
4. Тестировать изменения локально

## Лицензия

MIT License

## Контакты

По вопросам и предложениям: fitness_buddy@mail.ru

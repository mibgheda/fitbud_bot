#!/bin/bash

# Быстрое исправление: применение миграций и обновление кода

set -e

echo "🔧 Исправление проблемы с миграциями..."

# Проверка что мы в директории проекта
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Запустите скрипт из директории проекта (где находится docker-compose.yml)"
    exit 1
fi

# 1. Применяем миграции
echo "📊 Применение миграций к базе данных..."
docker compose exec bot alembic upgrade head

if [ $? -ne 0 ]; then
    echo "⚠️  Миграции не применены или уже применены"
    echo "Попробуем применить вручную..."
    
    # Применяем SQL напрямую
    echo "Применяем SQL миграцию..."
    docker compose exec -T postgres psql -U fitbud_user -d fitbud_bot << 'EOF'
-- Добавление новых колонок в calorie_entries (если не существуют)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='calorie_entries' AND column_name='source_type') THEN
        ALTER TABLE calorie_entries ADD COLUMN source_type VARCHAR(20) DEFAULT 'manual';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='calorie_entries' AND column_name='source_data') THEN
        ALTER TABLE calorie_entries ADD COLUMN source_data JSON;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='calorie_entries' AND column_name='ai_confidence') THEN
        ALTER TABLE calorie_entries ADD COLUMN ai_confidence FLOAT;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='calorie_entries' AND column_name='ai_notes') THEN
        ALTER TABLE calorie_entries ADD COLUMN ai_notes TEXT;
    END IF;
END $$;

-- Добавление новых колонок в workout_entries (если не существуют)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='source_type') THEN
        ALTER TABLE workout_entries ADD COLUMN source_type VARCHAR(20) DEFAULT 'manual';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='intensity') THEN
        ALTER TABLE workout_entries ADD COLUMN intensity VARCHAR(20);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='distance') THEN
        ALTER TABLE workout_entries ADD COLUMN distance FLOAT;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='pace') THEN
        ALTER TABLE workout_entries ADD COLUMN pace VARCHAR(50);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='ai_confidence') THEN
        ALTER TABLE workout_entries ADD COLUMN ai_confidence FLOAT;
    END IF;
END $$;

-- Создание таблицы health_data (если не существует)
CREATE TABLE IF NOT EXISTS health_data (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    parameter_name VARCHAR(100) NOT NULL,
    value FLOAT NOT NULL,
    unit VARCHAR(20),
    reference_min FLOAT,
    reference_max FLOAT,
    is_normal BOOLEAN,
    source_type VARCHAR(20) DEFAULT 'manual',
    source_file_path VARCHAR(500),
    notes TEXT,
    test_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы ai_interactions (если не существует)
CREATE TABLE IF NOT EXISTS ai_interactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    interaction_type VARCHAR(50) NOT NULL,
    input_type VARCHAR(20),
    input_data TEXT,
    input_file_path VARCHAR(500),
    ai_response JSON,
    ai_model VARCHAR(50),
    ai_confidence FLOAT,
    created_entry_type VARCHAR(50),
    created_entry_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание индексов (если не существуют)
CREATE INDEX IF NOT EXISTS idx_health_data_user_id ON health_data(user_id);
CREATE INDEX IF NOT EXISTS idx_health_data_test_date ON health_data(test_date);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_user_id ON ai_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_type ON ai_interactions(interaction_type);
CREATE INDEX IF NOT EXISTS idx_calorie_entries_source ON calorie_entries(source_type);

-- Отметить миграцию как примененную в Alembic
INSERT INTO alembic_version (version_num) VALUES ('001_ai_hub')
ON CONFLICT (version_num) DO NOTHING;
EOF
    
    if [ $? -eq 0 ]; then
        echo "✅ SQL миграция применена успешно"
    else
        echo "❌ Ошибка применения SQL миграции"
        exit 1
    fi
fi

# 2. Перезапускаем бота чтобы применились изменения кода
echo "🔄 Перезапуск бота..."
docker compose restart bot

echo ""
echo "✅ Исправление завершено!"
echo ""
echo "Проверьте работу:"
echo "  1. Отправьте фото еды боту 📸"
echo "  2. Проверьте логи: docker compose logs -f bot"
echo ""
echo "Если всё работает - отлично! 🎉"

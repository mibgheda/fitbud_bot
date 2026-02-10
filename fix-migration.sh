#!/bin/bash

# Исправление частично примененной миграции

set -e

echo "🔧 Исправление частичной миграции..."

# Применяем только недостающие изменения
docker compose exec -T postgres psql -U fitbud_user -d fitbud_bot << 'EOF'

-- Добавляем колонки в calorie_entries (если не существуют)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='calorie_entries' AND column_name='source_type') THEN
        ALTER TABLE calorie_entries ADD COLUMN source_type VARCHAR(20) DEFAULT 'manual';
        RAISE NOTICE 'Добавлена колонка source_type в calorie_entries';
    ELSE
        RAISE NOTICE 'Колонка source_type уже существует';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='calorie_entries' AND column_name='source_data') THEN
        ALTER TABLE calorie_entries ADD COLUMN source_data JSON;
        RAISE NOTICE 'Добавлена колонка source_data в calorie_entries';
    ELSE
        RAISE NOTICE 'Колонка source_data уже существует';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='calorie_entries' AND column_name='ai_confidence') THEN
        ALTER TABLE calorie_entries ADD COLUMN ai_confidence FLOAT;
        RAISE NOTICE 'Добавлена колонка ai_confidence в calorie_entries';
    ELSE
        RAISE NOTICE 'Колонка ai_confidence уже существует';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='calorie_entries' AND column_name='ai_notes') THEN
        ALTER TABLE calorie_entries ADD COLUMN ai_notes TEXT;
        RAISE NOTICE 'Добавлена колонка ai_notes в calorie_entries';
    ELSE
        RAISE NOTICE 'Колонка ai_notes уже существует';
    END IF;
END $$;

-- Добавляем колонки в workout_entries (если не существуют)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='source_type') THEN
        ALTER TABLE workout_entries ADD COLUMN source_type VARCHAR(20) DEFAULT 'manual';
        RAISE NOTICE 'Добавлена колонка source_type в workout_entries';
    ELSE
        RAISE NOTICE 'Колонка source_type уже существует';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='intensity') THEN
        ALTER TABLE workout_entries ADD COLUMN intensity VARCHAR(20);
        RAISE NOTICE 'Добавлена колонка intensity в workout_entries';
    ELSE
        RAISE NOTICE 'Колонка intensity уже существует';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='distance') THEN
        ALTER TABLE workout_entries ADD COLUMN distance FLOAT;
        RAISE NOTICE 'Добавлена колонка distance в workout_entries';
    ELSE
        RAISE NOTICE 'Колонка distance уже существует';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='pace') THEN
        ALTER TABLE workout_entries ADD COLUMN pace VARCHAR(50);
        RAISE NOTICE 'Добавлена колонка pace в workout_entries';
    ELSE
        RAISE NOTICE 'Колонка pace уже существует';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='workout_entries' AND column_name='ai_confidence') THEN
        ALTER TABLE workout_entries ADD COLUMN ai_confidence FLOAT;
        RAISE NOTICE 'Добавлена колонка ai_confidence в workout_entries';
    ELSE
        RAISE NOTICE 'Колонка ai_confidence уже существует';
    END IF;
END $$;

-- Создаем таблицу ai_interactions если не существует
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

-- Создаем индексы если не существуют
CREATE INDEX IF NOT EXISTS idx_health_data_user_id ON health_data(user_id);
CREATE INDEX IF NOT EXISTS idx_health_data_test_date ON health_data(test_date);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_user_id ON ai_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_type ON ai_interactions(interaction_type);
CREATE INDEX IF NOT EXISTS idx_calorie_entries_source ON calorie_entries(source_type);

-- Отмечаем миграцию как примененную в Alembic
INSERT INTO alembic_version (version_num) VALUES ('001_ai_hub')
ON CONFLICT (version_num) DO NOTHING;

-- Проверяем результат
SELECT 'Миграция завершена!' as status;

EOF

if [ $? -eq 0 ]; then
    echo "✅ База данных обновлена успешно"
    
    # Проверяем что колонки созданы
    echo ""
    echo "🔍 Проверка структуры calorie_entries:"
    docker compose exec postgres psql -U fitbud_user -d fitbud_bot -c "\d calorie_entries" | grep -E "source_|ai_"
    
    echo ""
    echo "🔄 Перезапуск бота..."
    docker compose restart bot
    
    echo ""
    echo "✅ Всё готово!"
    echo ""
    echo "Теперь можете отправить фото еды боту 📸"
else
    echo "❌ Ошибка обновления базы данных"
    exit 1
fi

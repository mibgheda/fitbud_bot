"""add ai hub features

Revision ID: 001_ai_hub
Revises: 
Create Date: 2025-02-10 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_ai_hub'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавление колонок в calorie_entries для AI Hub
    op.add_column('calorie_entries', 
        sa.Column('source_type', sa.String(length=20), server_default='manual', nullable=True))
    op.add_column('calorie_entries', 
        sa.Column('source_data', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('calorie_entries', 
        sa.Column('ai_confidence', sa.Float(), nullable=True))
    op.add_column('calorie_entries', 
        sa.Column('ai_notes', sa.Text(), nullable=True))
    
    # Добавление колонок в workout_entries для AI Hub
    op.add_column('workout_entries', 
        sa.Column('source_type', sa.String(length=20), server_default='manual', nullable=True))
    op.add_column('workout_entries', 
        sa.Column('intensity', sa.String(length=20), nullable=True))
    op.add_column('workout_entries', 
        sa.Column('distance', sa.Float(), nullable=True))
    op.add_column('workout_entries', 
        sa.Column('pace', sa.String(length=50), nullable=True))
    op.add_column('workout_entries', 
        sa.Column('ai_confidence', sa.Float(), nullable=True))
    
    # Создание таблицы health_data
    op.create_table('health_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('data_type', sa.String(length=50), nullable=False),
        sa.Column('parameter_name', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(length=20), nullable=True),
        sa.Column('reference_min', sa.Float(), nullable=True),
        sa.Column('reference_max', sa.Float(), nullable=True),
        sa.Column('is_normal', sa.Boolean(), nullable=True),
        sa.Column('source_type', sa.String(length=20), server_default='manual', nullable=True),
        sa.Column('source_file_path', sa.String(length=500), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('test_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_health_data_user_id', 'health_data', ['user_id'], unique=False)
    op.create_index('idx_health_data_test_date', 'health_data', ['test_date'], unique=False)
    
    # Создание таблицы ai_interactions
    op.create_table('ai_interactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('interaction_type', sa.String(length=50), nullable=False),
        sa.Column('input_type', sa.String(length=20), nullable=True),
        sa.Column('input_data', sa.Text(), nullable=True),
        sa.Column('input_file_path', sa.String(length=500), nullable=True),
        sa.Column('ai_response', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ai_model', sa.String(length=50), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('created_entry_type', sa.String(length=50), nullable=True),
        sa.Column('created_entry_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ai_interactions_user_id', 'ai_interactions', ['user_id'], unique=False)
    op.create_index('idx_ai_interactions_type', 'ai_interactions', ['interaction_type'], unique=False)
    
    # Индекс для source_type в calorie_entries
    op.create_index('idx_calorie_entries_source', 'calorie_entries', ['source_type'], unique=False)


def downgrade() -> None:
    # Удаление индексов
    op.drop_index('idx_calorie_entries_source', table_name='calorie_entries')
    op.drop_index('idx_ai_interactions_type', table_name='ai_interactions')
    op.drop_index('idx_ai_interactions_user_id', table_name='ai_interactions')
    op.drop_index('idx_health_data_test_date', table_name='health_data')
    op.drop_index('idx_health_data_user_id', table_name='health_data')
    
    # Удаление таблиц
    op.drop_table('ai_interactions')
    op.drop_table('health_data')
    
    # Удаление колонок из workout_entries
    op.drop_column('workout_entries', 'ai_confidence')
    op.drop_column('workout_entries', 'pace')
    op.drop_column('workout_entries', 'distance')
    op.drop_column('workout_entries', 'intensity')
    op.drop_column('workout_entries', 'source_type')
    
    # Удаление колонок из calorie_entries
    op.drop_column('calorie_entries', 'ai_notes')
    op.drop_column('calorie_entries', 'ai_confidence')
    op.drop_column('calorie_entries', 'source_data')
    op.drop_column('calorie_entries', 'source_type')

"""add query_template_log table

Revision ID: c4d8e2f19a67
Revises: b7e2a1f4c9d3
Create Date: 2026-08-27 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4d8e2f19a67'
down_revision: Union[str, Sequence[str], None] = 'b7e2a1f4c9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'query_template_log',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('matched_template', sa.String(length=64), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('params_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('declined', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('result_summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_query_template_log_user_id'), 'query_template_log', ['user_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_query_template_log_user_id'), table_name='query_template_log')
    op.drop_table('query_template_log')

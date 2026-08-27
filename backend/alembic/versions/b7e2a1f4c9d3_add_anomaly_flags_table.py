"""add anomaly_flags table

Revision ID: b7e2a1f4c9d3
Revises: 27e97f6a3b7f
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7e2a1f4c9d3'
down_revision: Union[str, Sequence[str], None] = '27e97f6a3b7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'anomaly_flags',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('transaction_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('driving_features_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('dismissed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('dismissal_reason', sa.String(length=255), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_id', name='uq_anomaly_flags_transaction_id'),
    )
    op.create_index(
        op.f('ix_anomaly_flags_transaction_id'), 'anomaly_flags', ['transaction_id'], unique=False
    )
    op.create_index(op.f('ix_anomaly_flags_user_id'), 'anomaly_flags', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_anomaly_flags_user_id'), table_name='anomaly_flags')
    op.drop_index(op.f('ix_anomaly_flags_transaction_id'), table_name='anomaly_flags')
    op.drop_table('anomaly_flags')

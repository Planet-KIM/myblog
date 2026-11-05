"""spellcheck_requests, users.created_at

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-05 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the spell-check access request table and ``users.created_at``.

    ``spellcheck_requests`` keeps every request with its decision; a partial
    unique index allows one pending request per user. ``users.created_at``
    stays NULL for existing accounts (they count as established when the
    request rules check the account age).
    """
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))

    op.create_table(
        'spellcheck_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('requested_level', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('granted_level', sa.Integer(), nullable=True),
        sa.Column('decided_by_user_id', sa.Integer(), nullable=True),
        sa.Column('decision_note', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('spellcheck_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_spellcheck_requests_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_spellcheck_requests_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_spellcheck_requests_status'), ['status'], unique=False)
    op.create_index(
        'uq_spellcheck_requests_one_pending', 'spellcheck_requests', ['user_id'], unique=True,
        sqlite_where=sa.text("status = 'pending'"), postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Drop the request table and ``users.created_at``."""
    op.drop_index('uq_spellcheck_requests_one_pending', table_name='spellcheck_requests')
    with op.batch_alter_table('spellcheck_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_spellcheck_requests_status'))
        batch_op.drop_index(batch_op.f('ix_spellcheck_requests_user_id'))
        batch_op.drop_index(batch_op.f('ix_spellcheck_requests_id'))
    op.drop_table('spellcheck_requests')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('created_at')

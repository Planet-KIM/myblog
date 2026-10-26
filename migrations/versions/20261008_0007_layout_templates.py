"""layout templates

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``layout_templates`` table for users' saved magazine layouts.

    Each row stores an owner ``user_id``, a ``name`` and the layout's
    ``content_blocks`` JSON. Indexed by id and ``user_id``.
    """
    op.create_table(
        'layout_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('content_blocks', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('layout_templates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_layout_templates_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_layout_templates_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    """Drop the ``layout_templates`` table and its indexes."""
    with op.batch_alter_table('layout_templates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_layout_templates_user_id'))
        batch_op.drop_index(batch_op.f('ix_layout_templates_id'))
    op.drop_table('layout_templates')

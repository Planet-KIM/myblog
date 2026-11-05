"""users.spellcheck_level

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-05 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``users.spellcheck_level`` (0 for every existing account).

    Spell check becomes opt-in: an admin grants level 1 (fast models) or 2
    (large models too). Admins are always treated as level 2 by the code, so
    they need no value here.
    """
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('spellcheck_level', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Drop ``users.spellcheck_level``."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('spellcheck_level')

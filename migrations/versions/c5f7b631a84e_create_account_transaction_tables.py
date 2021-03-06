"""Create account, transaction tables

Revision ID: c5f7b631a84e
Revises: 
Create Date: 2020-08-07 10:49:03.719474

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5f7b631a84e'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('account',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=30), nullable=False),
    sa.Column('description', sa.String(length=140), nullable=True),
    sa.Column('balance', sa.Float(), nullable=True),
    sa.Column('currency', sa.String(length=5), nullable=True),
    sa.Column('is_category', sa.Boolean(), nullable=True),
    sa.Column('icon', sa.String(length=140), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('transaction',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('expense', 'income', 'transfer', name='transactiontype'), nullable=False),
    sa.Column('datetime', sa.DateTime(), nullable=True),
    sa.Column('src_account_id', sa.Integer(), nullable=True),
    sa.Column('dest_account_id', sa.Integer(), nullable=True),
    sa.Column('value_src', sa.Float(), nullable=False),
    sa.Column('currency_src', sa.String(length=5), nullable=True),
    sa.Column('value_dest', sa.Float(), nullable=False),
    sa.Column('currency_dest', sa.String(length=5), nullable=True),
    sa.Column('where', sa.String(length=50), nullable=True),
    sa.Column('description', sa.String(length=140), nullable=True),
    sa.ForeignKeyConstraint(['dest_account_id'], ['account.id'], ),
    sa.ForeignKeyConstraint(['src_account_id'], ['account.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_transaction_datetime'), 'transaction', ['datetime'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_transaction_datetime'), table_name='transaction')
    op.drop_table('transaction')
    op.drop_table('account')
    # ### end Alembic commands ###

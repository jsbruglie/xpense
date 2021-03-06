import enum
from datetime import datetime, date, timedelta
from hashlib import md5

from app import db
from app.search import add_to_index, remove_from_index, query_index


class TransactionType(enum.Enum):
    expense = 1
    income = 2
    transfer = 3

    @staticmethod
    def from_str(label):
        if label in ('expense', 'Expenses'):
            return TransactionType.expense
        elif label in ('income', 'Income'):
            return TransactionType.income
        elif label in ('transfer', 'Transfer'):
            return TransactionType.transfer
        else:
            raise NotImplementedError


class SearchableMixin:
    """Mixin for handling indexing and querying"""
    @classmethod
    def search(cls, expression, page, per_page, fields=None):
        """TODO"""
        ids, total = query_index(cls.__tablename__, expression, page, per_page, fields=fields)
        if total == 0:
            return cls.query.filter_by(id=0), 0
        when = [(id, idx) for idx, id in enumerate(ids)]
        return cls.query.filter(cls.id.in_(ids)).order_by(db.case(when, value=cls.id)), total

    @classmethod
    def before_commit(cls, session):
        session._changes = {
            'add': list(session.new),
            'update': list(session.dirty),
            'delete': list(session.deleted)
        }

    @classmethod
    def after_commit(cls, session):
        for obj in session._changes['add']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['update']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['delete']:
            if isinstance(obj, SearchableMixin):
                remove_from_index(obj.__tablename__, obj)
        session._changes = None

    @classmethod
    def reindex(cls):
        for obj in cls.query:
            add_to_index(cls.__tablename__, obj)


db.event.listen(db.session, 'before_commit', SearchableMixin.before_commit)
db.event.listen(db.session, 'after_commit', SearchableMixin.after_commit)


class Transaction(db.Model, SearchableMixin):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.Enum(TransactionType), nullable=False)
    datetime = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    src_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    dest_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    # Value in source account currency
    value_src = db.Column(db.Float, nullable=False)
    currency_src = db.Column(db.String(5), default="EUR")
    # Value in destination account currency
    value_dest = db.Column(db.Float, nullable=False)
    currency_dest = db.Column(db.String(5), default="EUR")
    # TODO Maybe convert to generic tags?
    where = db.Column(db.String(50))
    description = db.Column(db.String(140))

    __searchable__ = ['description', 'where', "src_account.name", "dest_account.name"]

    def __repr__(self):
        if self.type != TransactionType.income:
            return f"<{self.type.name} {self.datetime} " \
                   f"{self.value_src} {self.currency_src} as {self.value_dest} {self.currency_dest} " \
                   f"from {self.src_account} to {self.dest_account}: {self.description}>"
        return f"<{self.type.name} {self.datetime} {self.value_src} {self.currency_src}:" \
               f"{self.description} @ {self.where}>"


class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)
    description = db.Column(db.String(140))
    balance = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(5), default="EUR")
    is_category = db.Column(db.Boolean, default=False)
    icon = db.Column(db.String(140))

    # Transactions from this account
    transactions_from =\
        db.relationship('Transaction', backref='src_account', lazy='dynamic',
                        foreign_keys='Transaction.src_account_id')
    # Transactions to this account
    transactions_to =\
        db.relationship('Transaction', backref='dest_account', lazy='dynamic',
                        foreign_keys='Transaction.dest_account_id')

    def __repr__(self):
        return f'<Account {self.name}: {self.balance:.2f} {self.currency}>'

    def check_valid_currency(self, transaction: Transaction, dest_account: "Account" = None):
        """Checks if transaction has the correct currency"""
        if transaction.type == TransactionType.income:
            if transaction.currency_dest != self.currency:
                raise RuntimeError(f"Incorrect currency at destination: "
                                   f"{transaction.currency_dest}, expected {self.currency}")
        elif transaction.type in (TransactionType.expense, TransactionType.transfer):
            if dest_account is None:
                raise RuntimeError("No destination account provided")
            if transaction.currency_dest != dest_account.currency:
                raise RuntimeError(f"Incorrect currency at destination: "
                                   f"{transaction.currency_dest}, expected {dest_account.currency}")
            if transaction.currency_src != self.currency:
                raise RuntimeError(f"Incorrect currency at source: "
                                   f"{transaction.currency_src}, expected {self.currency}")

    def add_transaction(self, transaction: Transaction, dest_account: "Account" = None):
        """Associates a transaction with respective accounts

        Should be used as follows
        `src_account.add_transaction(expense, dest_category)`
        `src_account.add_transaction(transfer, dest_account)`
        `dest_account.add_transaction(income)`
        """
        self.check_valid_currency(transaction, dest_account)
        if transaction.type == TransactionType.income:
            self.balance += transaction.value_dest
            self.transactions_to.append(transaction)
        elif transaction.type in (TransactionType.expense, TransactionType.transfer):
            self.balance -= transaction.value_src
            dest_account.balance += transaction.value_dest
            dest_account.transactions_to.append(transaction)
            self.transactions_from.append(transaction)
        db.session.add(transaction)
        db.session.commit()

    def remove_transaction(self, transaction: Transaction):
        """Removes the association of a transaction with respective accounts

        Should be used as follows
        `src_account.remove_transaction(expense/transfer)`
        `dest_account.remove_transaction(income)`
        """
        dest_account = transaction.dest_account
        self.check_valid_currency(transaction, dest_account)
        if transaction.type == TransactionType.income:
            self.balance -= transaction.value_dest
            self.transactions_to.remove(transaction)
        elif transaction.type in (TransactionType.expense, TransactionType.transfer):
            self.balance += transaction.value_src
            dest_account.balance -= transaction.value_dest
            dest_account.transactions_to.remove(transaction)
            self.transactions_from.remove(transaction)
        db.session.delete(transaction)
        db.session.commit()

    def transactions_cur_month(self):
        today = date.today()
        first = today.replace(day=1)
        last_month = first - timedelta(days=1)
        transactions_to = self.transactions_to.filter(Transaction.datetime >= last_month)
        transactions_from = self.transactions_from.filter(Transaction.datetime >= last_month)
        return transactions_to.union(transactions_from).order_by(Transaction.datetime.desc()).all()

    def sum_cur_month(self):
        today = date.today()
        first = today.replace(day=1)
        last_month = first - timedelta(days=1)
        transactions_to = self.transactions_to.filter(Transaction.datetime >= last_month).all()
        transactions_from = self.transactions_from.filter(Transaction.datetime >= last_month).all()
        sum_cur_month = sum([t.value_dest for t in transactions_to])
        sum_cur_month += sum([-t.value_src for t in transactions_from])
        return sum_cur_month

    def generate_icon(self, size: int = 50):
        digest = md5(self.name.lower().encode('utf-8')).hexdigest()
        self.icon = f'https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}'
        db.session.commit()

    def get_icon(self):
        if not self.icon:
            self.generate_icon()
        return self.icon

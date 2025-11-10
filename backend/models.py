"""
Database models for the accounting system
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class Config(db.Model):
    __tablename__ = 'config'
    id = db.Column(db.Integer, primary_key=True)
    functional_currency = db.Column(db.String(10), default='SAR')
    vat_rate = db.Column(db.Float, default=0.15)
    costing = db.Column(db.String(20), default='FIFO')

class Branch(db.Model):
    __tablename__ = 'branches'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class CostCenter(db.Model):
    __tablename__ = 'cost_centers'
    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class Currency(db.Model):
    __tablename__ = 'currencies'
    code = db.Column(db.String(10), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    functional = db.Column(db.Boolean, default=False)

class Item(db.Model):
    __tablename__ = 'items'
    sku = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    uom = db.Column(db.String(20), nullable=False)
    cat4 = db.Column(db.String(100))
    cat5 = db.Column(db.String(100))

class Price(db.Model):
    __tablename__ = 'prices'
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), db.ForeignKey('items.sku'), nullable=False)
    price = db.Column(db.Float, nullable=False)

class ItemGLMapping(db.Model):
    __tablename__ = 'item_gl_mapping'
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False, unique=True)
    inv_account = db.Column(db.String(50), nullable=False)
    sales_account = db.Column(db.String(50), nullable=False)
    cogs_account = db.Column(db.String(50), nullable=False)

class ChartOfAccount(db.Model):
    __tablename__ = 'chart_of_accounts'
    code = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    side = db.Column(db.String(1), nullable=False)  # D or C

class TaxCode(db.Model):
    __tablename__ = 'tax_codes'
    code = db.Column(db.String(20), primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    rate = db.Column(db.Float, nullable=False)
    gl = db.Column(db.String(50))
    gl_out = db.Column(db.String(50))
    gl_in = db.Column(db.String(50))

class JournalEntry(db.Model):
    __tablename__ = 'journal_entries'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    doc_date = db.Column(db.String(10), nullable=False)
    doc_no = db.Column(db.String(50), nullable=False)
    acc = db.Column(db.String(50), nullable=False)
    debit = db.Column(db.Float, default=0)
    credit = db.Column(db.Float, default=0)
    branch = db.Column(db.String(100), default='')
    cc = db.Column(db.String(20), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    no = db.Column(db.String(50), nullable=False, unique=True)
    type = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    branch = db.Column(db.String(100), default='')
    cc = db.Column(db.String(20), default='')
    currency = db.Column(db.String(10), default='SAR')
    base = db.Column(db.Float, default=0)
    vat = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DocumentLine(db.Model):
    __tablename__ = 'document_lines'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    doc_no = db.Column(db.String(50), db.ForeignKey('documents.no'), nullable=False)
    sku = db.Column(db.String(50))
    acc = db.Column(db.String(50))
    desc = db.Column(db.String(500))
    qty = db.Column(db.Float)
    price = db.Column(db.Float)
    net = db.Column(db.Float)

class StockBatch(db.Model):
    __tablename__ = 'stock_batches'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sku = db.Column(db.String(50), db.ForeignKey('items.sku'), nullable=False)
    qty = db.Column(db.Float, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DocumentSequence(db.Model):
    __tablename__ = 'document_sequences'
    id = db.Column(db.Integer, primary_key=True)
    prefix = db.Column(db.String(20), unique=True, nullable=False)
    next_number = db.Column(db.Integer, default=1)

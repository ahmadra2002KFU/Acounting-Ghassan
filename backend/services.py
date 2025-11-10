"""
Business logic for accounting operations
"""
from models import db, JournalEntry, StockBatch, DocumentSequence, Item, ItemGLMapping, ChartOfAccount
from datetime import datetime

class AccountingService:

    @staticmethod
    def get_next_doc_number(prefix):
        """Generate next document number with auto-increment"""
        seq = DocumentSequence.query.filter_by(prefix=prefix).first()
        if not seq:
            seq = DocumentSequence(prefix=prefix, next_number=1)
            db.session.add(seq)

        doc_no = f"{prefix}-{seq.next_number:06d}"
        seq.next_number += 1
        db.session.commit()
        return doc_no

    @staticmethod
    def post_line(doc_date, doc_no, acc, debit, credit, branch='', cc=''):
        """Post a journal entry line"""
        entry = JournalEntry(
            doc_date=doc_date,
            doc_no=doc_no,
            acc=acc,
            debit=float(debit or 0),
            credit=float(credit or 0),
            branch=branch or '',
            cc=cc or ''
        )
        db.session.add(entry)

    @staticmethod
    def fifo_add(sku, qty, unit_cost):
        """Add inventory batch for FIFO costing"""
        batch = StockBatch(
            sku=sku,
            qty=float(qty),
            unit_cost=float(unit_cost)
        )
        db.session.add(batch)

    @staticmethod
    def fifo_consume(sku, qty):
        """Consume inventory using FIFO and return total cost"""
        need = float(qty)
        cost = 0

        # Get batches ordered by creation date (FIFO)
        batches = StockBatch.query.filter_by(sku=sku).order_by(StockBatch.created_at).all()

        for batch in batches:
            if need <= 0:
                break

            take = min(need, batch.qty)
            cost += take * batch.unit_cost
            batch.qty -= take
            need -= take

            if batch.qty <= 0:
                db.session.delete(batch)

        if need > 0:
            raise ValueError(f"كمية غير كافية للصنف: {sku}")

        return cost

    @staticmethod
    def get_gl_mapping(cat5):
        """Get GL accounts for an item category"""
        mapping = ItemGLMapping.query.filter_by(category=cat5).first()
        if not mapping:
            # Fallback to default
            mapping = ItemGLMapping.query.filter_by(category="أجهزة صغيرة").first()

        if mapping:
            return {
                'inv': mapping.inv_account,
                'sales': mapping.sales_account,
                'cogs': mapping.cogs_account
            }
        else:
            # Hard fallback
            return {
                'inv': '1-03-02-010-000',
                'sales': '4-01-02-001-000',
                'cogs': '5-01-02-001-000'
            }

class VoucherService:

    @staticmethod
    def post_sale(date, branch, cc, sku, qty, price, cash_or_ar, currency, vat_rate):
        """Post a sales invoice with FIFO COGS calculation"""
        # Get item details
        item = Item.query.filter_by(sku=sku).first()
        if not item:
            raise ValueError("صنف غير معروف")

        # Get GL mapping
        gl_map = AccountingService.get_gl_mapping(item.cat5)

        # Generate document number
        doc_no = AccountingService.get_next_doc_number('AR')

        # Calculate amounts
        base = round(float(qty) * float(price), 2)
        vat = round(base * float(vat_rate), 2)
        total = base + vat

        # Account codes
        cash_acc = "1-01-01-001-001"
        ar_acc = "1-02-01-000-000"
        vat_output_acc = "2-02-01-001-000"

        # Post revenue entries
        debit_acc = cash_acc if cash_or_ar == "نقدي" else ar_acc
        AccountingService.post_line(date, doc_no, debit_acc, total, 0, branch, cc)
        AccountingService.post_line(date, doc_no, gl_map['sales'], 0, base, branch, cc)
        AccountingService.post_line(date, doc_no, vat_output_acc, 0, vat, branch, cc)

        # Calculate and post COGS
        cogs_cost = AccountingService.fifo_consume(sku, qty)
        AccountingService.post_line(date, doc_no, gl_map['cogs'], cogs_cost, 0, branch, cc)
        AccountingService.post_line(date, doc_no, gl_map['inv'], 0, cogs_cost, branch, cc)

        return {
            'doc_no': doc_no,
            'base': base,
            'vat': vat,
            'total': total,
            'cogs': cogs_cost,
            'item_name': item.name
        }

    @staticmethod
    def post_purchase(date, branch, cc, sku, qty, price, payment_type, supplier_acc, vat_rate):
        """Post a purchase invoice"""
        # Get item details
        item = Item.query.filter_by(sku=sku).first()
        if not item:
            raise ValueError("صنف غير معروف")

        # Get GL mapping
        gl_map = AccountingService.get_gl_mapping(item.cat5)

        # Generate document number
        doc_no = AccountingService.get_next_doc_number('AP')

        # Calculate amounts
        base = round(float(qty) * float(price), 2)
        vat = round(base * float(vat_rate), 2)
        total = base + vat

        # Account codes
        bank_acc = "1-01-02-001-001"
        vat_input_acc = "2-03-01-001-000"

        # Post entries
        AccountingService.post_line(date, doc_no, gl_map['inv'], base, 0, branch, cc)
        AccountingService.post_line(date, doc_no, vat_input_acc, vat, 0, branch, cc)

        credit_acc = bank_acc if payment_type == "نقدي" else (supplier_acc or "2-01-01-000-000")
        AccountingService.post_line(date, doc_no, credit_acc, 0, total, branch, cc)

        # Add to FIFO inventory
        AccountingService.fifo_add(sku, qty, price)

        return {
            'doc_no': doc_no,
            'base': base,
            'vat': vat,
            'total': total,
            'item_name': item.name
        }

    @staticmethod
    def post_receipt(date, from_acc, to_acc, amount, branch='', cc=''):
        """Post a receipt voucher"""
        doc_no = AccountingService.get_next_doc_number('RC')

        AccountingService.post_line(date, doc_no, to_acc, amount, 0, branch, cc)
        AccountingService.post_line(date, doc_no, from_acc, 0, amount, branch, cc)

        return {'doc_no': doc_no, 'amount': amount}

    @staticmethod
    def post_payment(date, from_acc, to_acc, amount, branch='', cc=''):
        """Post a payment voucher"""
        doc_no = AccountingService.get_next_doc_number('PY')

        AccountingService.post_line(date, doc_no, to_acc, amount, 0, branch, cc)
        AccountingService.post_line(date, doc_no, from_acc, 0, amount, branch, cc)

        return {'doc_no': doc_no, 'amount': amount}

    @staticmethod
    def post_journal(date, debit_acc, credit_acc, amount, branch='', cc=''):
        """Post a manual journal entry"""
        doc_no = AccountingService.get_next_doc_number('JV')

        AccountingService.post_line(date, doc_no, debit_acc, amount, 0, branch, cc)
        AccountingService.post_line(date, doc_no, credit_acc, 0, amount, branch, cc)

        return {'doc_no': doc_no, 'amount': amount}

    @staticmethod
    def post_sales_return(date, sku, qty, price, refund_type, vat_rate, branch='', cc=''):
        """Post a sales return (credit note)"""
        # Get item details
        item = Item.query.filter_by(sku=sku).first()
        if not item:
            item = Item(sku=sku, name="", uom="قطعة", cat5="أجهزة صغيرة")

        # Get GL mapping
        gl_map = AccountingService.get_gl_mapping(item.cat5)

        # Generate document number
        doc_no = AccountingService.get_next_doc_number('CRN')

        # Calculate amounts
        base = round(float(qty) * float(price), 2)
        vat = round(base * float(vat_rate), 2)
        total = base + vat

        # Account codes
        returns_acc = "4-02-01-000-000"
        vat_output_acc = "2-02-01-001-000"
        cash_acc = "1-01-01-001-001"
        ar_acc = "1-02-01-000-000"

        # Post return entries (reverse of sales)
        AccountingService.post_line(date, doc_no, returns_acc, base, 0, branch, cc)
        AccountingService.post_line(date, doc_no, vat_output_acc, vat, 0, branch, cc)

        credit_acc = cash_acc if refund_type == "نقدي" else ar_acc
        AccountingService.post_line(date, doc_no, credit_acc, 0, total, branch, cc)

        # Return inventory to stock
        AccountingService.fifo_add(sku, qty, price)

        # Reverse COGS
        AccountingService.post_line(date, doc_no, gl_map['inv'], base, 0, branch, cc)
        AccountingService.post_line(date, doc_no, gl_map['cogs'], 0, base, branch, cc)

        return {
            'doc_no': doc_no,
            'base': base,
            'vat': vat,
            'total': total
        }

    @staticmethod
    def post_purchase_return(date, sku, qty, price, supplier_acc, vat_rate, branch='', cc=''):
        """Post a purchase return (debit note)"""
        # Get item details
        item = Item.query.filter_by(sku=sku).first()
        if not item:
            item = Item(sku=sku, name="", uom="قطعة", cat5="أجهزة صغيرة")

        # Get GL mapping
        gl_map = AccountingService.get_gl_mapping(item.cat5)

        # Generate document number
        doc_no = AccountingService.get_next_doc_number('DRN')

        # Calculate amounts
        base = round(float(qty) * float(price), 2)
        vat = round(base * float(vat_rate), 2)
        total = base + vat

        # Account codes
        vat_input_acc = "2-03-01-001-000"

        # Post return entries (reverse of purchase)
        AccountingService.post_line(date, doc_no, gl_map['inv'], 0, base, branch, cc)
        AccountingService.post_line(date, doc_no, vat_input_acc, 0, vat, branch, cc)
        AccountingService.post_line(date, doc_no, supplier_acc or "2-01-01-000-000", total, 0, branch, cc)

        # Try to consume from FIFO (but don't fail if not available)
        try:
            AccountingService.fifo_consume(sku, qty)
        except ValueError:
            pass  # Ignore if insufficient stock

        return {
            'doc_no': doc_no,
            'base': base,
            'vat': vat,
            'total': total
        }

class ReportService:

    @staticmethod
    def get_journal(from_date=None, to_date=None, branch=None, cc=None, limit=100):
        """Get journal entries with optional filters"""
        query = JournalEntry.query

        if from_date:
            query = query.filter(JournalEntry.doc_date >= from_date)
        if to_date:
            query = query.filter(JournalEntry.doc_date <= to_date)
        if branch:
            query = query.filter(JournalEntry.branch == branch)
        if cc:
            query = query.filter(JournalEntry.cc == cc)

        return query.order_by(JournalEntry.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_ledger(account_code, from_date=None, to_date=None):
        """Get ledger for a specific account"""
        query = JournalEntry.query.filter_by(acc=account_code)

        if from_date:
            query = query.filter(JournalEntry.doc_date >= from_date)
        if to_date:
            query = query.filter(JournalEntry.doc_date <= to_date)

        entries = query.order_by(JournalEntry.doc_date, JournalEntry.created_at).all()

        # Calculate running balance
        balance = 0
        result = []
        for entry in entries:
            balance += entry.debit - entry.credit
            result.append({
                'doc_date': entry.doc_date,
                'doc_no': entry.doc_no,
                'debit': entry.debit,
                'credit': entry.credit,
                'balance': balance
            })

        return result

    @staticmethod
    def get_trial_balance():
        """Generate trial balance"""
        accounts = ChartOfAccount.query.all()
        result = []

        for account in accounts:
            entries = JournalEntry.query.filter_by(acc=account.code).all()

            total_debit = sum(e.debit for e in entries)
            total_credit = sum(e.credit for e in entries)

            # Calculate balance based on account side
            if account.side == 'D':
                balance = total_debit - total_credit
            else:
                balance = total_credit - total_debit

            result.append({
                'code': account.code,
                'name': account.name,
                'debit': total_debit,
                'credit': total_credit,
                'balance': balance
            })

        return result

    @staticmethod
    def get_income_statement():
        """Generate income statement"""
        all_entries = JournalEntry.query.all()

        revenue = sum(e.credit - e.debit for e in all_entries if e.acc.startswith('4-01-'))
        returns = sum(e.debit - e.credit for e in all_entries if e.acc.startswith('4-02-'))
        cogs = sum(e.debit - e.credit for e in all_entries if e.acc.startswith('5-'))
        opex = sum(e.debit - e.credit for e in all_entries if e.acc.startswith('6-'))
        other_income = sum(e.credit - e.debit for e in all_entries if e.acc.startswith('7-01-'))
        other_expense = sum(e.debit - e.credit for e in all_entries if e.acc.startswith('7-02-'))

        net_revenue = revenue - returns
        gross_profit = net_revenue - cogs
        operating_income = gross_profit - opex
        net_profit = operating_income + other_income - other_expense

        return {
            'revenue': revenue,
            'returns': returns,
            'net_revenue': net_revenue,
            'cogs': cogs,
            'gross_profit': gross_profit,
            'opex': opex,
            'operating_income': operating_income,
            'other_income': other_income,
            'other_expense': other_expense,
            'net_profit': net_profit
        }

    @staticmethod
    def get_balance_sheet():
        """Generate balance sheet"""
        accounts = ChartOfAccount.query.all()
        all_entries = JournalEntry.query.all()

        assets = 0
        liabilities = 0
        equity = 0

        for account in accounts:
            entries = [e for e in all_entries if e.acc == account.code]

            if account.side == 'D':
                balance = sum(e.debit - e.credit for e in entries)
            else:
                balance = sum(e.credit - e.debit for e in entries)

            if account.code.startswith('1-'):
                assets += balance
            elif account.code.startswith('2-'):
                liabilities += balance
            elif account.code.startswith('3-'):
                equity += balance

        # Add net profit to equity
        is_data = ReportService.get_income_statement()
        equity_total = equity + is_data['net_profit']

        difference = assets - (liabilities + equity_total)
        balanced = abs(difference) < 0.01

        return {
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity_total,
            'difference': difference,
            'balanced': balanced
        }

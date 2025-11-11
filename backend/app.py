"""
Flask application for accounting system backend
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from models import *
from services import AccountingService, VoucherService, ReportService
import json
import os

app = Flask(__name__, static_folder='../.')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///accounting.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Enable CORS
CORS(app)

# ============= STATIC FILE SERVING =============

@app.route('/')
def serve_frontend():
    """Serve the main HTML file"""
    return send_from_directory('..', 'accounting_app_offline_v2.html')

# ============= CONFIG API =============

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get system configuration"""
    config = Config.query.first()
    if not config:
        return jsonify({'error': 'Config not found'}), 404

    return jsonify({
        'functionalCurrency': config.functional_currency,
        'vatRate': config.vat_rate,
        'costing': config.costing
    })

# ============= MASTER DATA APIs =============

@app.route('/api/branches', methods=['GET'])
def get_branches():
    """Get all branches"""
    branches = Branch.query.all()
    return jsonify([{'id': b.id, 'name': b.name} for b in branches])

@app.route('/api/cost-centers', methods=['GET'])
def get_cost_centers():
    """Get all cost centers"""
    centers = CostCenter.query.all()
    return jsonify([{'id': c.id, 'name': c.name} for c in centers])

@app.route('/api/currencies', methods=['GET'])
def get_currencies():
    """Get all currencies"""
    currencies = Currency.query.all()
    return jsonify([{'code': c.code, 'name': c.name, 'functional': c.functional} for c in currencies])

@app.route('/api/items', methods=['GET'])
def get_items():
    """Get all items"""
    items = Item.query.all()
    return jsonify([{
        'sku': i.sku,
        'name': i.name,
        'uom': i.uom,
        'cat4': i.cat4,
        'cat5': i.cat5
    } for i in items])

@app.route('/api/prices', methods=['GET'])
def get_prices():
    """Get all prices as a dictionary"""
    prices = Price.query.all()
    return jsonify({p.sku: p.price for p in prices})

@app.route('/api/item-mapping', methods=['GET'])
def get_item_mapping():
    """Get item GL mappings"""
    mappings = ItemGLMapping.query.all()
    result = {}
    for m in mappings:
        result[m.category] = {
            'inv': m.inv_account,
            'sales': m.sales_account,
            'cogs': m.cogs_account
        }
    return jsonify(result)

@app.route('/api/coa', methods=['GET'])
def get_coa():
    """Get chart of accounts"""
    accounts = ChartOfAccount.query.all()
    return jsonify([{
        'code': a.code,
        'name': a.name,
        'side': a.side
    } for a in accounts])

@app.route('/api/tax-codes', methods=['GET'])
def get_tax_codes():
    """Get tax codes"""
    taxes = TaxCode.query.all()
    result = []
    for t in taxes:
        tax_dict = {
            'code': t.code,
            'type': t.type,
            'rate': t.rate
        }
        if t.gl:
            tax_dict['gl'] = t.gl
        if t.gl_out:
            tax_dict['glOut'] = t.gl_out
        if t.gl_in:
            tax_dict['glIn'] = t.gl_in
        result.append(tax_dict)
    return jsonify(result)

# ============= JOURNAL ENTRIES API =============

@app.route('/api/journal', methods=['GET'])
def get_journal():
    """Get journal entries with optional filters"""
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    branch = request.args.get('branch')
    cc = request.args.get('cc')
    limit = int(request.args.get('limit', 100))

    entries = ReportService.get_journal(from_date, to_date, branch, cc, limit)

    return jsonify([{
        'docDate': e.doc_date,
        'docNo': e.doc_no,
        'acc': e.acc,
        'debit': e.debit,
        'credit': e.credit,
        'branch': e.branch,
        'cc': e.cc
    } for e in entries])

# ============= DOCUMENTS API =============

@app.route('/api/documents', methods=['GET'])
def get_documents():
    """Get all documents"""
    limit = int(request.args.get('limit', 50))
    docs = Document.query.order_by(Document.created_at.desc()).limit(limit).all()

    result = []
    for doc in docs:
        lines = DocumentLine.query.filter_by(doc_no=doc.no).all()
        result.append({
            'no': doc.no,
            'type': doc.type,
            'date': doc.date,
            'branch': doc.branch,
            'cc': doc.cc,
            'currency': doc.currency,
            'base': doc.base,
            'vat': doc.vat,
            'total': doc.total,
            'lines': [{
                'sku': l.sku,
                'acc': l.acc,
                'desc': l.desc,
                'qty': l.qty,
                'price': l.price,
                'net': l.net
            } for l in lines]
        })

    return jsonify(result)

# ============= VOUCHER POSTING APIs =============

@app.route('/api/vouchers/sale', methods=['POST'])
def post_sale():
    """Post a sales invoice"""
    try:
        data = request.json
        config = Config.query.first()

        result = VoucherService.post_sale(
            date=data['date'],
            branch=data['branch'],
            cc=data['cc'],
            sku=data['sku'],
            qty=data['qty'],
            price=data['price'],
            cash_or_ar=data['cashOrAR'],
            currency=data.get('currency', 'SAR'),
            vat_rate=config.vat_rate
        )

        # Save document
        doc = Document(
            no=result['doc_no'],
            type='فاتورة مبيعات',
            date=data['date'],
            branch=data['branch'],
            cc=data['cc'],
            currency=data.get('currency', 'SAR'),
            base=result['base'],
            vat=result['vat'],
            total=result['total']
        )
        db.session.add(doc)

        # Save document line
        line = DocumentLine(
            doc_no=result['doc_no'],
            sku=data['sku'],
            desc=result['item_name'],
            qty=data['qty'],
            price=data['price'],
            net=result['base']
        )
        db.session.add(line)

        db.session.commit()

        return jsonify({
            'success': True,
            'doc_no': result['doc_no'],
            'cogs': result['cogs'],
            'message': f"تم الترحيل (COGS={result['cogs']:.2f})"
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vouchers/purchase', methods=['POST'])
def post_purchase():
    """Post a purchase invoice"""
    try:
        data = request.json
        config = Config.query.first()

        result = VoucherService.post_purchase(
            date=data['date'],
            branch=data['branch'],
            cc=data['cc'],
            sku=data['sku'],
            qty=data['qty'],
            price=data['price'],
            payment_type=data['paymentType'],
            supplier_acc=data.get('supplierAcc'),
            vat_rate=config.vat_rate
        )

        # Save document
        doc = Document(
            no=result['doc_no'],
            type='فاتورة مشتريات',
            date=data['date'],
            branch=data['branch'],
            cc=data['cc'],
            currency='SAR',
            base=result['base'],
            vat=result['vat'],
            total=result['total']
        )
        db.session.add(doc)

        # Save document line
        line = DocumentLine(
            doc_no=result['doc_no'],
            sku=data['sku'],
            desc=result['item_name'],
            qty=data['qty'],
            price=data['price'],
            net=result['base']
        )
        db.session.add(line)

        db.session.commit()

        return jsonify({
            'success': True,
            'doc_no': result['doc_no'],
            'message': 'تم الترحيل وإضافة دفعة FIFO'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vouchers/receipt', methods=['POST'])
def post_receipt():
    """Post a receipt voucher"""
    try:
        data = request.json

        result = VoucherService.post_receipt(
            date=data['date'],
            from_acc=data['fromAcc'],
            to_acc=data['toAcc'],
            amount=data['amount'],
            branch=data.get('branch', ''),
            cc=data.get('cc', '')
        )

        # Save document
        doc = Document(
            no=result['doc_no'],
            type='سند قبض',
            date=data['date'],
            base=result['amount'],
            vat=0,
            total=result['amount']
        )
        db.session.add(doc)

        # Save document line
        line = DocumentLine(
            doc_no=result['doc_no'],
            acc=data['toAcc'],
            desc='تحصيل نقدي/بنكي',
            net=result['amount']
        )
        db.session.add(line)

        db.session.commit()

        return jsonify({
            'success': True,
            'doc_no': result['doc_no'],
            'message': 'تم الترحيل'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vouchers/payment', methods=['POST'])
def post_payment():
    """Post a payment voucher"""
    try:
        data = request.json

        result = VoucherService.post_payment(
            date=data['date'],
            from_acc=data['fromAcc'],
            to_acc=data['toAcc'],
            amount=data['amount'],
            branch=data.get('branch', ''),
            cc=data.get('cc', '')
        )

        # Save document
        doc = Document(
            no=result['doc_no'],
            type='سند صرف',
            date=data['date'],
            base=result['amount'],
            vat=0,
            total=result['amount']
        )
        db.session.add(doc)

        # Save document line
        line = DocumentLine(
            doc_no=result['doc_no'],
            acc=data['toAcc'],
            desc='صرف نقدي/بنكي',
            net=result['amount']
        )
        db.session.add(line)

        db.session.commit()

        return jsonify({
            'success': True,
            'doc_no': result['doc_no'],
            'message': 'تم الترحيل'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vouchers/journal', methods=['POST'])
def post_journal():
    """Post a journal entry"""
    try:
        data = request.json

        result = VoucherService.post_journal(
            date=data['date'],
            debit_acc=data['debitAcc'],
            credit_acc=data['creditAcc'],
            amount=data['amount'],
            branch=data.get('branch', ''),
            cc=data.get('cc', '')
        )

        # Save document
        doc = Document(
            no=result['doc_no'],
            type='قيد يومية',
            date=data['date'],
            base=result['amount'],
            vat=0,
            total=result['amount']
        )
        db.session.add(doc)

        # Save document lines
        line1 = DocumentLine(
            doc_no=result['doc_no'],
            acc=data['debitAcc'],
            desc='',
            net=result['amount']
        )
        line2 = DocumentLine(
            doc_no=result['doc_no'],
            acc=data['creditAcc'],
            desc='',
            net=-result['amount']
        )
        db.session.add(line1)
        db.session.add(line2)

        db.session.commit()

        return jsonify({
            'success': True,
            'doc_no': result['doc_no'],
            'message': 'تم الترحيل'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vouchers/return-sale', methods=['POST'])
def post_return_sale():
    """Post a sales return"""
    try:
        data = request.json
        config = Config.query.first()

        result = VoucherService.post_sales_return(
            date=data['date'],
            sku=data['sku'],
            qty=data['qty'],
            price=data['price'],
            refund_type=data['refundType'],
            vat_rate=config.vat_rate,
            branch=data.get('branch', ''),
            cc=data.get('cc', '')
        )

        # Save document
        doc = Document(
            no=result['doc_no'],
            type='مرتجع مبيعات',
            date=data['date'],
            base=result['base'],
            vat=result['vat'],
            total=result['total']
        )
        db.session.add(doc)

        # Save document line
        item = Item.query.filter_by(sku=data['sku']).first()
        line = DocumentLine(
            doc_no=result['doc_no'],
            sku=data['sku'],
            desc=item.name if item else '',
            qty=data['qty'],
            price=data['price'],
            net=result['base']
        )
        db.session.add(line)

        db.session.commit()

        return jsonify({
            'success': True,
            'doc_no': result['doc_no'],
            'message': 'تم الترحيل'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vouchers/return-purchase', methods=['POST'])
def post_return_purchase():
    """Post a purchase return"""
    try:
        data = request.json
        config = Config.query.first()

        result = VoucherService.post_purchase_return(
            date=data['date'],
            sku=data['sku'],
            qty=data['qty'],
            price=data['price'],
            supplier_acc=data.get('supplierAcc'),
            vat_rate=config.vat_rate,
            branch=data.get('branch', ''),
            cc=data.get('cc', '')
        )

        # Save document
        doc = Document(
            no=result['doc_no'],
            type='مرتجع مشتريات',
            date=data['date'],
            base=result['base'],
            vat=result['vat'],
            total=result['total']
        )
        db.session.add(doc)

        # Save document line
        item = Item.query.filter_by(sku=data['sku']).first()
        line = DocumentLine(
            doc_no=result['doc_no'],
            sku=data['sku'],
            desc=item.name if item else '',
            qty=data['qty'],
            price=data['price'],
            net=result['base']
        )
        db.session.add(line)

        db.session.commit()

        return jsonify({
            'success': True,
            'doc_no': result['doc_no'],
            'message': 'تم الترحيل'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ============= REPORTS APIs =============

@app.route('/api/reports/journal', methods=['GET'])
def report_journal():
    """Journal report with filters"""
    return get_journal()  # Reuse the same endpoint

@app.route('/api/reports/ledger', methods=['GET'])
def report_ledger():
    """Ledger report for a specific account"""
    account = request.args.get('account')
    from_date = request.args.get('from')
    to_date = request.args.get('to')

    if not account:
        return jsonify({'error': 'Account code required'}), 400

    ledger = ReportService.get_ledger(account, from_date, to_date)
    return jsonify(ledger)

@app.route('/api/reports/trial-balance', methods=['GET'])
def report_trial_balance():
    """Trial balance report"""
    tb = ReportService.get_trial_balance()
    return jsonify(tb)

@app.route('/api/reports/income-statement', methods=['GET'])
def report_income_statement():
    """Income statement report"""
    is_data = ReportService.get_income_statement()
    return jsonify(is_data)

@app.route('/api/reports/balance-sheet', methods=['GET'])
def report_balance_sheet():
    """Balance sheet report"""
    bs = ReportService.get_balance_sheet()
    return jsonify(bs)

# ============= BACKUP/RESTORE APIs =============

@app.route('/api/backup/export', methods=['GET'])
def export_backup():
    """Export all data as JSON"""
    data = {
        'config': {
            'functionalCurrency': Config.query.first().functional_currency,
            'vatRate': Config.query.first().vat_rate,
            'costing': Config.query.first().costing
        },
        'branches': [{'id': b.id, 'name': b.name} for b in Branch.query.all()],
        'costCenters': [{'id': c.id, 'name': c.name} for c in CostCenter.query.all()],
        'currencies': [{'code': c.code, 'name': c.name, 'functional': c.functional} for c in Currency.query.all()],
        'items': [{
            'sku': i.sku, 'name': i.name, 'uom': i.uom, 'cat4': i.cat4, 'cat5': i.cat5
        } for i in Item.query.all()],
        'prices': {p.sku: p.price for p in Price.query.all()},
        'itemMap': {
            m.category: {
                'inv': m.inv_account,
                'sales': m.sales_account,
                'cogs': m.cogs_account
            } for m in ItemGLMapping.query.all()
        },
        'coa': [{'code': a.code, 'name': a.name, 'side': a.side} for a in ChartOfAccount.query.all()],
        'taxes': [{'code': t.code, 'type': t.type, 'rate': t.rate} for t in TaxCode.query.all()],
        'journal': [{
            'docDate': j.doc_date,
            'docNo': j.doc_no,
            'acc': j.acc,
            'debit': j.debit,
            'credit': j.credit,
            'branch': j.branch,
            'cc': j.cc
        } for j in JournalEntry.query.all()],
        'stockBatches': {}
    }

    # Group stock batches by SKU
    batches = StockBatch.query.all()
    for batch in batches:
        if batch.sku not in data['stockBatches']:
            data['stockBatches'][batch.sku] = []
        data['stockBatches'][batch.sku].append({
            'qty': batch.qty,
            'unitCost': batch.unit_cost
        })

    return jsonify(data)

@app.route('/api/backup/import', methods=['POST'])
def import_backup():
    """Import data from JSON (WARNING: This will clear existing data!)"""
    try:
        data = request.json

        # Clear existing data
        db.session.query(DocumentLine).delete()
        db.session.query(Document).delete()
        db.session.query(JournalEntry).delete()
        db.session.query(StockBatch).delete()
        db.session.commit()

        # Import journal entries
        if 'journal' in data:
            for j in data['journal']:
                entry = JournalEntry(
                    doc_date=j['docDate'],
                    doc_no=j['docNo'],
                    acc=j['acc'],
                    debit=j['debit'],
                    credit=j['credit'],
                    branch=j.get('branch', ''),
                    cc=j.get('cc', '')
                )
                db.session.add(entry)

        # Import stock batches
        if 'stockBatches' in data:
            for sku, batches in data['stockBatches'].items():
                for batch in batches:
                    stock_batch = StockBatch(
                        sku=sku,
                        qty=batch['qty'],
                        unit_cost=batch['unitCost']
                    )
                    db.session.add(stock_batch)

        db.session.commit()

        return jsonify({'success': True, 'message': 'تم الاستيراد بنجاح'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/reset', methods=['POST'])
def reset_data():
    """Reset all transactional data (keep master data)"""
    try:
        db.session.query(DocumentLine).delete()
        db.session.query(Document).delete()
        db.session.query(JournalEntry).delete()
        db.session.query(StockBatch).delete()
        db.session.query(DocumentSequence).delete()
        db.session.commit()

        return jsonify({'success': True, 'message': 'تم إعادة التعيين'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ============= ERROR HANDLERS =============

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# ============= MAIN =============

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Database initialized!")
        print("Starting Flask server on http://localhost:5000")

    app.run(debug=True, host='0.0.0.0', port=5000)

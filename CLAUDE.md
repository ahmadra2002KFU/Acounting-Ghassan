# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Saudi Arabian accounting system** (نظام محاسبي) with a Flask backend and HTML/JavaScript frontend. It implements double-entry bookkeeping with FIFO inventory costing, 15% VAT calculation, and supports multi-branch operations. The application is primarily in Arabic with English code.

**Status**: Proof of Concept (PoC) - no authentication or production-level security features.

## Development Commands

### Initial Setup
```bash
cd backend
pip install -r requirements.txt
python seed_data.py  # Creates database and seeds test data
```

### Running the Application
```bash
cd backend
python app.py
```
Server runs on `http://localhost:5000`

### Database Management
```bash
# Reset database (clear all transactional data, keep master data)
# Call POST /api/reset via the frontend or curl

# Reseed from scratch
python seed_data.py  # This recreates the entire database
```

## Architecture

### Backend Structure (Flask + SQLite)

**Key Files**:
- `backend/app.py` - Flask application with all API endpoints (REST API)
- `backend/models.py` - SQLAlchemy ORM models for 14 database tables
- `backend/services.py` - Business logic layer with 3 service classes
- `backend/seed_data.py` - Database initialization and test data generation
- `backend/accounting.db` - SQLite database (auto-created)

**Service Layer Pattern**:
- `AccountingService` - Core operations (FIFO, GL mapping, document numbering, journal posting)
- `VoucherService` - Document posting (sales, purchases, receipts, payments, returns)
- `ReportService` - Financial reports (journal, ledger, trial balance, income statement, balance sheet)

### Frontend
- `index.html` - Main application (connects to Flask backend via fetch API)
- `accounting_app_offline_v2.html` - Legacy standalone version (localStorage only)

### Database Schema

14 tables organized by purpose:
1. **Master Data**: config, branches, cost_centers, currencies, items, prices, item_gl_mapping
2. **Chart of Accounts**: chart_of_accounts (70+ accounts), tax_codes
3. **Transactions**: journal_entries, documents, document_lines
4. **Inventory**: stock_batches (FIFO tracking)
5. **Sequences**: document_sequences (auto-numbering)

## Core Accounting Logic

### FIFO Inventory Costing
- Implemented in `AccountingService.fifo_add()` and `AccountingService.fifo_consume()` (services.py:37-70)
- Each purchase creates a `StockBatch` with qty and unit_cost
- Sales consume from oldest batches first
- COGS calculated automatically during sales posting

### Document Numbering
- Auto-increment with prefixes: AR-000001 (sales), AP-000001 (purchases), RC-000001 (receipts), PY-000001 (payments), JV-000001 (journal), CRN-000001 (sales returns), DRN-000001 (purchase returns)
- Managed by `AccountingService.get_next_doc_number()` (services.py:10-20)

### GL Account Mapping
- Items mapped to GL accounts via `cat5` category
- Mapping stored in `item_gl_mapping` table
- Each category has: inventory account, sales account, COGS account
- See `AccountingService.get_gl_mapping()` (services.py:73-92)

### VAT Calculation
- Fixed 15% rate (Saudi Arabia standard)
- Separate GL accounts for VAT Output (2-02-01-001-000) and VAT Input (2-03-01-001-000)
- Automatically calculated on all sales/purchase vouchers

### Chart of Accounts Structure
- **1-xxx**: Assets (نقدية، مخزون، مدينون)
- **2-xxx**: Liabilities (دائنون، ضرائب)
- **3-xxx**: Equity (رأس المال)
- **4-xxx**: Revenue (مبيعات، مرتجعات)
- **5-xxx**: Cost of Goods Sold
- **6-xxx**: Operating Expenses
- **7-xxx**: Other Income/Expenses

## API Structure

All endpoints follow pattern `/api/{category}/{action}`

### Master Data (GET)
`/api/config`, `/api/branches`, `/api/cost-centers`, `/api/currencies`, `/api/items`, `/api/prices`, `/api/item-mapping`, `/api/coa`, `/api/tax-codes`

### Voucher Posting (POST)
`/api/vouchers/sale`, `/api/vouchers/purchase`, `/api/vouchers/receipt`, `/api/vouchers/payment`, `/api/vouchers/journal`, `/api/vouchers/return-sale`, `/api/vouchers/return-purchase`

**Important**: All vouchers return `{'success': True/False}` with error messages in Arabic.

### Reports (GET)
- `/api/reports/journal?from=&to=&branch=&cc=&limit=` - Journal entries with filters
- `/api/reports/ledger?account=XXX&from=&to=` - Account ledger with running balance
- `/api/reports/trial-balance` - All accounts with debit/credit totals
- `/api/reports/income-statement` - P&L calculation
- `/api/reports/balance-sheet` - Assets = Liabilities + Equity validation

### Data Management (POST)
- `/api/backup/export` - Export all data as JSON
- `/api/backup/import` - Import data (WARNING: clears existing)
- `/api/reset` - Clear transactional data only

## Important Implementation Details

### Double-Entry Validation
- Every journal entry must balance (debit = credit)
- Enforced at service layer, not database level
- Sales vouchers create 5 journal lines: DR Cash/AR, CR Sales, CR VAT Output, DR COGS, CR Inventory

### Sales Invoice Flow (services.py:96-138)
1. Validate item exists
2. Get GL mapping for item category
3. Generate AR document number
4. Calculate base, VAT, total
5. Post revenue entries (debit cash/AR, credit sales + VAT output)
6. Call `fifo_consume()` to calculate COGS
7. Post COGS entries (debit COGS, credit inventory)
8. Create document and line records

### Purchase Invoice Flow (services.py:140-179)
1. Validate item exists
2. Get GL mapping
3. Generate AP document number
4. Calculate base, VAT, total
5. Post purchase entries (debit inventory + VAT input, credit bank/supplier)
6. Call `fifo_add()` to create stock batch
7. Create document and line records

### Error Handling
- Services raise `ValueError` with Arabic messages
- Flask routes catch exceptions, rollback transactions, return 400 status
- Common errors: insufficient stock, unknown items, missing accounts

## Testing Workflow

1. Reset database: `python seed_data.py`
2. Start server: `python app.py`
3. Open `http://localhost:5000`
4. Post test vouchers through frontend
5. Verify reports for correct balances

**Validation Checks**:
- Trial balance should have equal debit/credit totals
- Balance sheet should balance (difference < 0.01)
- Ledger running balances should match trial balance

## Code Style Notes

- Mixed Arabic/English: UI text in Arabic, code in English
- Flask route functions are simple wrappers around service methods
- Service methods use static methods (no state)
- Database sessions managed with Flask-SQLAlchemy context
- Dates stored as strings in YYYY-MM-DD format
- All amounts rounded to 2 decimal places

## Common Development Tasks

### Adding a New Voucher Type
1. Add service method in `VoucherService` (services.py)
2. Add POST route in app.py following existing pattern
3. Add document prefix to `get_next_doc_number()` if needed
4. Update frontend to call new endpoint

### Adding a New Report
1. Add static method in `ReportService` (services.py)
2. Add GET route in app.py
3. Query `JournalEntry` with appropriate filters
4. Return JSON with calculated totals

### Modifying GL Accounts
1. Update `seed_data.py` to add accounts to chart_of_accounts
2. Update `item_gl_mapping` if item-related
3. Update hardcoded account codes in services.py if system accounts (cash, VAT, etc.)

### Database Schema Changes
1. Modify models in `models.py`
2. Delete `accounting.db`
3. Run `python seed_data.py` to recreate
4. **Note**: No migration framework (Alembic) is configured

## Known Limitations

- No user authentication or authorization
- No audit trail or modification history
- No multi-currency support (functional currency only)
- No period closing or fiscal year management
- FIFO implementation doesn't handle negative inventory gracefully
- No database migrations (schema changes require recreation)
- Reports not cached (recalculated on every request)
- No pagination on journal/ledger reports (memory issues possible)

## Security Warnings

This is a PoC system. Before production use:
- Add authentication (Flask-Login or JWT)
- Add authorization/role-based access
- Validate all inputs
- Use parameterized queries (already done via SQLAlchemy)
- Add HTTPS/TLS
- Encrypt sensitive data
- Add rate limiting
- Implement audit logging

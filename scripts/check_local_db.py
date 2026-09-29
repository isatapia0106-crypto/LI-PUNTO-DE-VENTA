"""Verify a local SQLite demo before the Windows launcher starts it."""
import sqlite3
import sys
from pathlib import Path

db_path = Path(__file__).resolve().parents[1] / 'pos.db'
if not db_path.is_file():
    print('Falta pos.db')
    sys.exit(1)

required = {
    'users': {'id', 'password_hash', 'role'},
    'branches': {'id', 'empresa_id'},
    'customers': {'id', 'empresa_id'},
    'sales': {'id', 'customer_id', 'customer_name', 'cash_session_id'},
    'stock_transfers': {'id', 'request_key'},
}
with sqlite3.connect(db_path) as db:
    for table, columns in required.items():
        actual = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
        if not columns <= actual:
            print(f'La base local necesita una migración: {table} ({", ".join(sorted(columns - actual))}).')
            sys.exit(2)
    print(db.execute('SELECT COUNT(*) FROM users').fetchone()[0])

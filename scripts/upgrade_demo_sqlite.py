"""Preserve an existing second-generation SQLite demo DB while adding auth tables.

This is only for demo data. Use Alembic for a new PostgreSQL deployment.
"""
import argparse
import os
import secrets
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('database', type=Path, help='Ruta al archivo pos.db existente')
args = parser.parse_args()
source = args.database.resolve()
if not source.is_file():
    raise SystemExit('No existe el archivo de base de datos')
backup = source.with_name(source.name + '.backup-before-auth')
if backup.exists():
    raise SystemExit(f'Ya existe un respaldo: {backup}. No se sobrescribe.')
with sqlite3.connect(source) as db:
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {'branches','products','stock','sales','sale_items','audit_logs','cash_sessions','cash_movements','stock_movements'}
    if not expected <= names:
        raise SystemExit('Esquema no reconocido. No se modificó la base de datos.')
    sale_cols = {row[1] for row in db.execute('PRAGMA table_info(sales)')}
    if not {'cash_session_id','request_key'} <= sale_cols:
        raise SystemExit('Esta base es una demo anterior incompatible. No se modificó la base de datos.')
    if 'alembic_version' in names:
        raise SystemExit('Esta base ya está versionada; usa Alembic.')
    with sqlite3.connect(backup) as target:
        db.backup(target)

# Import only after the backup, with the automatic demo bootstrap disabled.
os.environ['APP_ENV'] = 'production'
os.environ.setdefault('JWT_SECRET', secrets.token_urlsafe(48))
os.environ['DATABASE_URL'] = f'sqlite:///{source}'
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.main import User, UserBranch, engine
from sqlalchemy import inspect, text

with engine.begin() as db:
    if 'actor_id' not in {c['name'] for c in inspect(db).get_columns('audit_logs')}:
        db.execute(text('ALTER TABLE audit_logs ADD COLUMN actor_id INTEGER'))
# Create only the tables of the revision being stamped; later revisions create their own tables.
User.__table__.create(engine, checkfirst=True)
UserBranch.__table__.create(engine, checkfirst=True)
with engine.begin() as db:
    db.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
    db.execute(text("INSERT INTO alembic_version (version_num) VALUES ('77f0a8ca18aa')"))
print(f'Migración de demo terminada. Respaldo: {backup}')


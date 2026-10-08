"""Back up and migrate the recognized local SQLite installation, without importing demo bootstrap."""
import argparse
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

def migrate(path):
    path = path.resolve()
    if not path.is_file():
        raise SystemExit('No existe la base local. Inicia la aplicación para crear una nueva.')
    os.environ['APP_ENV'] = 'production'
    os.environ.setdefault('JWT_SECRET', secrets.token_urlsafe(48))
    os.environ['DATABASE_URL'] = f'sqlite:///{path.as_posix()}'
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(root / 'alembic.ini'))
    cfg.set_main_option('script_location', str(root / 'backend/alembic'))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with sqlite3.connect(path) as db:
        names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'alembic_version' in names:
            versions = [x[0] for x in db.execute('SELECT version_num FROM alembic_version')]
            if len(versions) != 1:
                raise SystemExit('La versión de la base no es válida. No se modificó.')
            version = versions[0]
            if version == head:
                print('Base local actualizada.')
                return
            if version not in {r.revision for r in ScriptDirectory.from_config(cfg).walk_revisions()}:
                raise SystemExit('Versión desconocida. No se modificó la base.')
        else:
            required = {'branches', 'users', 'user_branches', 'products', 'stock', 'sales', 'sale_items',
                        'cash_sessions', 'cash_movements', 'stock_movements', 'stock_transfers', 'customers', 'audit_logs'}
            if not required <= names or 'customer_name' not in {x[1] for x in db.execute('PRAGMA table_info(sales)')}:
                raise SystemExit('Demo antigua no reconocida: consulta SEGURIDAD_Y_MIGRACIONES.md. No se modificó la base.')
            modern = 'barcode' in {x[1] for x in db.execute('PRAGMA table_info(products)')}
            if modern and not {'cash_registers', 'suppliers', 'purchases', 'purchase_items', 'purchase_receipts', 'inventory_counts'} <= names:
                raise SystemExit('Base parcialmente migrada. No se modificó.')
            version = None
            baseline = 'a3d7e910c624' if {'sale_returns', 'sale_return_items'} <= names else 'f2b3409ac871' if modern else 'e1a59c0d35f4'
            if baseline == 'a3d7e910c624' and 'kind' in {x[1] for x in db.execute('PRAGMA table_info(sale_returns)')} and 'close_snapshot' in {x[1] for x in db.execute('PRAGMA table_info(cash_sessions)')}:
                baseline = 'b4e812c9a530'
            if baseline == 'b4e812c9a530' and 'minimum' in {x[1] for x in db.execute('PRAGMA table_info(stock)')} and 'token_version' in {x[1] for x in db.execute('PRAGMA table_info(users)')}:
                baseline = 'c5f902ad6718'
            if baseline == 'c5f902ad6718' and 'payment_intents' in names:
                baseline = 'd6a013be7829'
            if baseline == 'd6a013be7829' and 'reservation_active' in {x[1] for x in db.execute('PRAGMA table_info(payment_intents)')}:
                baseline = 'e7b124cf8930'
            if baseline == 'e7b124cf8930' and 'cancel_requested_at' in {x[1] for x in db.execute('PRAGMA table_info(payment_intents)')}:
                baseline = 'f8c235da9041'
            if baseline == 'f8c235da9041' and 'delivery_cash_session_id' in {x[1] for x in db.execute('PRAGMA table_info(payment_intents)')}:
                baseline = '09d346eb0152'
            if baseline == '09d346eb0152' and {'payment_refunds','payment_observations'} <= names:
                baseline = '1ae457fc1263'
            if baseline == '1ae457fc1263' and 'status' in {x[1] for x in db.execute('PRAGMA table_info(sale_returns)')}:
                baseline = '2bf5680d2374'
            if baseline == '2bf5680d2374' and 'cancel_reason' in {x[1] for x in db.execute('PRAGMA table_info(purchases)')}:
                baseline = '3c06791e3485'
            if baseline == '3c06791e3485' and 'tax_rate' in {x[1] for x in db.execute('PRAGMA table_info(purchase_items)')}:
                baseline = '4d178a2f4596'
            if baseline == '4d178a2f4596' and {'supplier_payables','supplier_payments'} <= names:
                baseline = '5e289b3056a7'
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('La base tiene errores de integridad. No se modificó.')
        backup = path.with_name(path.name + '.backup-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
        with sqlite3.connect(backup) as target:
            db.backup(target)
    print(f'Respaldo: {backup}')
    if version is None:
        command.stamp(cfg, baseline)
    command.upgrade(cfg, 'head')
    with sqlite3.connect(path) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit(f'Revisa la integridad después de migrar. Conserva el respaldo {backup}.')
    print('Migración terminada. Las ventas y existencias se conservaron.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('database', type=Path, nargs='?', default=root / 'pos.db')
    migrate(parser.parse_args().database)


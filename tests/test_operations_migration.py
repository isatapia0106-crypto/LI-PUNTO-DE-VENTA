import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_upgrade_preserves_old_sale_stock_and_backup(tmp_path):
    path = tmp_path / 'old.db'
    env = {**os.environ, 'APP_ENV':'production', 'JWT_SECRET':'migration-test-secret', 'DATABASE_URL':f'sqlite:///{path}'}
    def command(*args):
        result = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return result
    command('-m','alembic','upgrade','e1a59c0d35f4')
    with sqlite3.connect(path) as db:
        db.executescript("""
        INSERT INTO branches VALUES (1,1,'Sucursal conservada');
        INSERT INTO users VALUES (1,1,'legacy','unused-hash','admin_general',1);
        INSERT INTO products VALUES (1,1,'SKU-OLD','Producto conservado',100);
        INSERT INTO stock VALUES (1,1,1,8);
        INSERT INTO cash_sessions VALUES (1,1,1,100,NULL,'open','2026-09-29',NULL);
        INSERT INTO sales (id,empresa_id,branch_id,created_at,subtotal,tax,total,payment_method,cash_session_id,request_key,paid,customer_id,customer_name)
        VALUES (1,1,1,'2026-09-29',200,32,232,'cash',1,'legacy-sale-001',250,NULL,NULL);
        INSERT INTO sale_items VALUES (1,1,1,'Producto conservado',2,100);
        INSERT INTO stock_movements VALUES (1,1,1,1,-2,'sale',1,'2026-09-29');
        """)
    result = command('scripts/migrate_local.py',str(path))
    assert 'Respaldo:' in result.stdout
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT subtotal,tax,total,paid,folio FROM sales').fetchone() == (200,32,232,250,'LI-B1-00000001')
        assert db.execute('SELECT quantity,average_cost FROM stock').fetchone() == (8,0)
        assert db.execute('SELECT name,price,tax_rate FROM products').fetchone() == ('Producto conservado',100,.16)
        assert db.execute('SELECT cashier_id,register_id FROM cash_sessions').fetchone() == (None,1)
        assert db.execute('SELECT name FROM cash_registers').fetchone()[0] == 'Caja 1'
        # Do not redistribute the old tax and change the old ticket's historical rounding.
        assert db.execute('SELECT net_amount,tax_amount FROM sale_items').fetchone() == (None,None)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    backups = list(tmp_path.glob('old.db.backup-*'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup, sqlite3.connect(tmp_path/'restored.db') as restored:
        backup.backup(restored)
        assert restored.execute('SELECT quantity FROM stock').fetchone()[0] == 8
        assert 'folio' not in {x[1] for x in restored.execute('PRAGMA table_info(sales)')}
        assert restored.execute('SELECT version_num FROM alembic_version').fetchone()[0] == 'e1a59c0d35f4'
    command('scripts/migrate_local.py',str(path))
    assert len(list(tmp_path.glob('old.db.backup-*'))) == 1


def test_returns_upgrade_unstamped_modern_demo(tmp_path):
    path=tmp_path/'modern.db'
    env={**os.environ,'APP_ENV':'production','JWT_SECRET':'migration-test-secret','DATABASE_URL':f'sqlite:///{path}'}
    def run(*args):
        r=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,capture_output=True,text=True)
        assert r.returncode==0,r.stdout+r.stderr
    run('-m','alembic','upgrade','f2b3409ac871')
    with sqlite3.connect(path) as db:db.execute('DROP TABLE alembic_version')
    run('scripts/migrate_local.py',str(path))
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='a3d7e910c624'
        assert db.execute('SELECT COUNT(*) FROM sale_returns').fetchone()[0]==0
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]

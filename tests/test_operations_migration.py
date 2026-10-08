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
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='704abd5278c9'
        assert db.execute('SELECT COUNT(*) FROM sale_returns').fetchone()[0]==0
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_upgrade_returns_preserves_record_and_adds_cut_snapshot(tmp_path):
    path=tmp_path/'returns.db'
    env={**os.environ,'APP_ENV':'production','JWT_SECRET':'migration-test-secret','DATABASE_URL':f'sqlite:///{path}'}
    def run(*args):
        r=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,capture_output=True,text=True)
        assert r.returncode==0,r.stdout+r.stderr
    run('-m','alembic','upgrade','a3d7e910c624')
    run('scripts/migrate_local.py',str(path))
    with sqlite3.connect(path) as db:
        assert 'kind' in {x[1] for x in db.execute('PRAGMA table_info(sale_returns)')}
        assert 'close_snapshot' in {x[1] for x in db.execute('PRAGMA table_info(cash_sessions)')}
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert len(list(tmp_path.glob('returns.db.backup-*')))==1

def test_high_priority_migration_preserves_user_stock(tmp_path):
    path=tmp_path/'high.db'
    env={**os.environ,'APP_ENV':'production','JWT_SECRET':'migration-test-secret','DATABASE_URL':f'sqlite:///{path}'}
    def run(*args):
        r=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,capture_output=True,text=True)
        assert r.returncode==0,r.stdout+r.stderr
    run('-m','alembic','upgrade','b4e812c9a530')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO branches (id,empresa_id,name) VALUES (1,1,'Sucursal')")
        db.execute("INSERT INTO users (id,empresa_id,username,password_hash,role,active) VALUES (1,1,'anterior','hash-conservado','admin_general',1)")
        db.execute("INSERT INTO products (id,empresa_id,sku,name,price) VALUES (1,1,'OLD','Producto',100)")
        db.execute('INSERT INTO stock (id,product_id,branch_id,quantity,average_cost) VALUES (1,1,1,8,15)')
    run('scripts/migrate_local.py',str(path))
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT quantity,average_cost,minimum FROM stock').fetchone()==(8,15,0)
        assert db.execute('SELECT password_hash,token_version FROM users').fetchone()==('hash-conservado',0)
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_payment_delivery_migration_recovers_existing_sale(tmp_path):
    path=tmp_path/'delivered.db'
    env={**os.environ,'APP_ENV':'production','JWT_SECRET':'migration-test-secret','DATABASE_URL':f'sqlite:///{path}'}
    def run(*args):
        r=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,capture_output=True,text=True)
        assert r.returncode==0,r.stdout+r.stderr
    run('-m','alembic','upgrade','f8c235da9041')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO branches (id,empresa_id,name) VALUES (1,1,'Sucursal')")
        db.execute("INSERT INTO users (id,empresa_id,username,password_hash,role,active) VALUES (1,1,'cajero','hash-conservado','cajero',1)")
        db.execute("INSERT INTO cash_sessions (id,empresa_id,branch_id,cashier_id,opening,status,opened_at) VALUES (1,1,1,1,100,'closed','2026-10-01 09:00:00')")
        db.execute("INSERT INTO sales (id,empresa_id,branch_id,created_at,subtotal,tax,total,payment_method,cash_session_id,request_key,paid,actor_id) VALUES (1,1,1,'2026-10-01 09:30:00',100,16,116,'mercado_pago',1,'mp-sale-delivered-1',116,1)")
        db.execute("INSERT INTO payment_intents (id,empresa_id,branch_id,actor_id,payload,amount,status,request_key,created_at) VALUES ('delivered-1',1,1,1,'{}',116,'completed','original-checkout','2026-10-01 09:20:00')")
    run('scripts/migrate_local.py',str(path))
    with sqlite3.connect(path) as db:
        row=db.execute('SELECT delivery_cash_session_id,delivered_at,amount,status FROM payment_intents').fetchone()
        assert row==(1,'2026-10-01 09:30:00',116,'completed')
        assert db.execute('SELECT cash_session_id,total FROM sales').fetchone()==(1,116)
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_integrated_return_migration_keeps_legacy_financial_record(tmp_path):
    path=tmp_path/'legacy-return.db'
    env={**os.environ,'APP_ENV':'production','JWT_SECRET':'migration-test-secret','DATABASE_URL':f'sqlite:///{path}'}
    def run(*args):
        r=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,capture_output=True,text=True)
        assert r.returncode==0,r.stdout+r.stderr
    run('-m','alembic','upgrade','1ae457fc1263')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO branches (id,empresa_id,name) VALUES (1,1,'Sucursal')")
        db.execute("INSERT INTO users (id,empresa_id,username,password_hash,role,active) VALUES (1,1,'admin','hash','admin_general',1)")
        db.execute("INSERT INTO products (id,empresa_id,sku,name,price) VALUES (1,1,'OLD','Conservado',.05)")
        db.execute("INSERT INTO cash_sessions (id,empresa_id,branch_id,cashier_id,opening,status,opened_at) VALUES (1,1,1,1,100,'closed','2026-10-01 09:00:00')")
        db.execute("INSERT INTO sales (id,empresa_id,branch_id,created_at,subtotal,tax,total,payment_method,cash_session_id,request_key,paid,actor_id) VALUES (1,1,1,'2026-10-01 09:30:00',.1,0,.1,'cash',1,'legacy-sale',.1,1)")
        db.execute("INSERT INTO sale_items (id,sale_id,product_id,name,quantity,unit_price) VALUES (1,1,1,'Conservado',2,.05)")
        db.execute("INSERT INTO sale_returns (id,empresa_id,sale_id,actor_id,cash_session_id,reason,payload,total,request_key,created_at) VALUES (1,1,1,1,1,'Conservada','{}',.05,'legacy-return','2026-10-01 10:00:00')")
        db.execute('INSERT INTO sale_return_items (id,return_id,sale_item_id,quantity,restock,total) VALUES (1,1,1,1,1,.05)')
    run('scripts/migrate_local.py',str(path))
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status,total,created_at,finalized_at FROM sale_returns').fetchone()==('completed',.05,'2026-10-01 10:00:00','2026-10-01 10:00:00')
        assert db.execute('SELECT return_id,quantity,total FROM sale_return_items').fetchone()==(1,1,.05)
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]

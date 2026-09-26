import os
import tempfile
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(tempfile.mkdtemp()) / 'test.db')
os.environ['JWT_SECRET'] = 'test-only-secret-key-not-for-production-123456789'
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.app.main import app, engine, User, UserBranch, Branch, password_hash

client = TestClient(app)
with Session(engine) as db:
    admin = User(username='owner', empresa_id=1, role='admin_general', password_hash=password_hash.hash('admin-password-123'))
    cashier = User(username='cashier', empresa_id=1, role='cajero', password_hash=password_hash.hash('cashier-password-123'))
    outsider = User(username='outsider', empresa_id=2, role='admin_general', password_hash=password_hash.hash('outsider-password-123'))
    db.add_all([admin, cashier, outsider])
    db.flush()
    db.add(UserBranch(user_id=cashier.id, branch_id=1))
    db.add(Branch(empresa_id=2, name='Sucursal ajena'))
    db.commit()

def auth(username, password):
    r = client.post('/api/auth/login', json={'username':username,'password':password})
    assert r.status_code == 200, r.text
    return {'Authorization': f"Bearer {r.json()['access_token']}"}

ADMIN = auth('owner','admin-password-123')
CASHIER = auth('cashier','cashier-password-123')
OUTSIDER = auth('outsider','outsider-password-123')

def test_auth_roles_and_branch_scope():
    assert client.get('/api/branches').status_code == 401
    assert client.post('/api/auth/login', json={'username':'owner','password':'wrong'}).status_code == 401
    assert len(client.get('/api/branches', headers=ADMIN).json()) == 6
    assert [b['id'] for b in client.get('/api/branches', headers=CASHIER).json()] == [1]
    assert client.get('/api/products?branch_id=2', headers=CASHIER).status_code == 403
    assert client.get('/api/products?branch_id=1', headers=OUTSIDER).status_code == 404
    assert client.post('/api/products', headers=CASHIER, json={'sku':'X','name':'X','price':1,'branch_id':1,'stock':1}).status_code == 403
    assert client.post('/api/users', headers=CASHIER, json={'username':'newbie','password':'password-12345','role':'cajero','branch_ids':[1]}).status_code == 403
    r = client.post('/api/users', headers=ADMIN, json={'username':'newbie','password':'password-12345','role':'cajero','branch_ids':[2]})
    assert r.status_code == 201, r.text
    assert client.post('/api/users', headers=ADMIN, json={'username':'bad','password':'password-12345','role':'cajero','branch_ids':[7]}).status_code == 422

def test_branch_cash_sale_and_stock_ledger():
    product = client.post('/api/products', headers=ADMIN, json={'sku':'ABC-01','name':'Artículo prueba','price':'100.00','branch_id':1,'stock':2})
    assert product.status_code == 201, product.text
    product_id = product.json()['id']
    payload = {'branch_id':1,'items':[{'product_id':product_id,'quantity':2}],'payment_method':'cash','paid':'250.00'}
    key = {'Idempotency-Key':'checkout-unique-0001'}
    assert client.post('/api/sales', json=payload, headers={**CASHIER,**key}).status_code == 409
    assert client.post('/api/sales', json=payload, headers={**OUTSIDER,**key}).status_code == 404
    assert client.get('/api/products?branch_id=2', headers=ADMIN).json() == []
    opened = client.post('/api/cash/open', headers=CASHIER, json={'branch_id':1,'opening':'100.00'})
    assert opened.status_code == 201, opened.text
    assert client.post('/api/cash/open', headers=CASHIER, json={'branch_id':1,'opening':'0'}).status_code == 409
    assert client.post('/api/sales', json={**payload,'paid':'10.00'}, headers={**CASHIER,**key}).status_code == 422
    assert client.get('/api/products?branch_id=1', headers=ADMIN).json()[0]['stock'] == 2
    sale = client.post('/api/sales', json=payload, headers={**CASHIER,**key})
    assert sale.status_code == 201, sale.text
    assert sale.json()['total'] == '232.00' and sale.json()['change'] == '18.00'
    replay = client.post('/api/sales', json=payload, headers={**CASHIER,**key})
    assert replay.status_code == 201 and replay.json()['replayed']
    assert client.post('/api/sales', json={**payload,'paid':'233.00'}, headers={**CASHIER,**key}).status_code == 409
    assert client.get('/api/products?branch_id=1', headers=ADMIN).json()[0]['stock'] == 0
    assert client.post('/api/sales', json=payload, headers={**CASHIER,'Idempotency-Key':'checkout-unique-0002'}).status_code == 409
    assert len(client.get('/api/sales?branch_id=1', headers=CASHIER).json()) == 1
    assert client.get('/api/stock/movements?branch_id=1', headers=ADMIN).json()[0]['change'] == -2
    assert client.get('/api/stock/movements?branch_id=1', headers=CASHIER).status_code == 403
    assert client.get('/api/cash/current?branch_id=1', headers=CASHIER).json()['expected'] == '332.00'
    assert client.get('/api/reports/summary?branch_id=1', headers=ADMIN).json()['by_method']['cash'] == '232.00'
    assert client.get('/api/reports/summary?branch_id=1', headers=CASHIER).status_code == 403
    url = f"/api/cash/{opened.json()['id']}/withdraw"
    assert client.post(url, headers=CASHIER,json={'amount':'20','reason':'sin permiso'}).status_code == 403
    assert client.post(url, headers=ADMIN,json={'amount':'500','reason':'retiro imposible'}).status_code == 409
    withdrawal = client.post(url, headers=ADMIN,json={'amount':'20','reason':'retiro autorizado'})
    assert withdrawal.status_code == 201 and withdrawal.json()['expected_after'] == '312.00'
    close = client.post(f"/api/cash/{opened.json()['id']}/close",headers=CASHIER,json={'counted':'330.00'})
    assert close.status_code == 200 and close.json()['difference'] == '18.00'
    assert client.post('/api/sales', json=payload, headers={**CASHIER,'Idempotency-Key':'checkout-unique-0003'}).status_code == 409
    assert client.get('/api/sales?branch_id=1',headers=OUTSIDER).status_code == 404

def test_stock_adjustments_are_scoped_and_traced():
    product = client.post('/api/products',headers=ADMIN,json={'sku':'ABC-02','name':'Otro','price':'10','branch_id':2,'stock':0}).json()['id']
    assert client.post(f'/api/products/{product}/stock',headers=ADMIN,json={'branch_id':2,'change':-1,'reason':'conteo'}).status_code == 409
    assert client.post(f'/api/products/{product}/stock',headers=ADMIN,json={'branch_id':2,'change':3,'reason':'recepción'}).json()['stock'] == 3
    assert client.post(f'/api/products/{product}/stock',headers=CASHIER,json={'branch_id':2,'change':1,'reason':'fraude'}).status_code == 403
    assert client.post(f'/api/products/{product}/stock',headers=OUTSIDER,json={'branch_id':2,'change':1,'reason':'fraude'}).status_code == 404
    assert client.get('/api/stock/movements?branch_id=2',headers=ADMIN).json()[0]['reason'] == 'recepción'

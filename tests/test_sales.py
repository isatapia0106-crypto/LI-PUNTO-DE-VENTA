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
    detail = client.get(f"/api/sales/{sale.json()['id']}", headers=CASHIER)
    assert detail.status_code == 200, detail.text
    assert detail.json()['branch_name'] == 'Zamora'
    assert detail.json()['items'][0]['line_total'] == '200.00'
    assert detail.json()['change'] == '18.00'
    assert client.get(f"/api/sales/{sale.json()['id']}", headers=OUTSIDER).status_code == 404
    assert client.get('/api/sales/999999', headers=CASHIER).status_code == 404
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

def test_sale_receipt_respects_branch_assignment():
    created = client.post('/api/products', headers=ADMIN, json={'sku':'TICKET-02','name':'Producto ticket','price':'10.00','branch_id':2,'stock':1})
    assert created.status_code == 201, created.text
    opened = client.post('/api/cash/open', headers=ADMIN, json={'branch_id':2,'opening':'0'})
    assert opened.status_code == 201, opened.text
    sale = client.post('/api/sales', headers={**ADMIN,'Idempotency-Key':'ticket-branch-02'}, json={
        'branch_id':2,'items':[{'product_id':created.json()['id'],'quantity':1}],
        'payment_method':'cash','paid':'11.60'})
    assert sale.status_code == 201, sale.text
    url = f"/api/sales/{sale.json()['id']}"
    assert client.get(url, headers=ADMIN).json()['total'] == '11.60'
    assert client.get(url, headers=CASHIER).status_code == 403
    assert client.get(url, headers=OUTSIDER).status_code == 404

def test_stock_transfer_is_atomic_scoped_and_idempotent():
    created = client.post('/api/products', headers=ADMIN, json={
        'sku':'TRANSFER-01','name':'Traspasable','price':'20.00','branch_id':1,'stock':5})
    assert created.status_code == 201, created.text
    product_id = created.json()['id']
    data = {'source_branch_id':1,'target_branch_id':2,'product_id':product_id,'quantity':3}
    headers = {**ADMIN, 'Idempotency-Key':'transfer-unique-001'}
    assert client.post('/api/stock/transfers', headers={**CASHIER,'Idempotency-Key':'transfer-cashier-001'}, json=data).status_code == 403
    warehouse = client.post('/api/users', headers=ADMIN, json={
        'username':'warehouse-transfer','password':'warehouse-password-123','role':'almacenista','branch_ids':[1]})
    assert warehouse.status_code == 201, warehouse.text
    restricted = auth('warehouse-transfer','warehouse-password-123')
    assert client.post('/api/stock/transfers', headers={**restricted,'Idempotency-Key':'transfer-warehouse-001'}, json=data).status_code == 403
    assert client.post('/api/stock/transfers', headers={**OUTSIDER,'Idempotency-Key':'transfer-outsider-001'}, json=data).status_code == 404
    assert client.post('/api/stock/transfers', headers=headers, json={**data,'target_branch_id':1}).status_code == 422
    transfer = client.post('/api/stock/transfers', headers=headers, json=data)
    assert transfer.status_code == 201, transfer.text
    assert transfer.json()['replayed'] is False
    again = client.post('/api/stock/transfers', headers=headers, json=data)
    assert again.status_code == 201 and again.json()['replayed'] is True
    assert client.post('/api/stock/transfers', headers=headers, json={**data,'quantity':1}).status_code == 409
    source = next(x for x in client.get('/api/products?branch_id=1', headers=ADMIN).json() if x['id']==product_id)
    target = next(x for x in client.get('/api/products?branch_id=2', headers=ADMIN).json() if x['id']==product_id)
    assert (source['stock'], target['stock']) == (2, 3)
    ref = transfer.json()['id']
    outgoing = client.get('/api/stock/movements?branch_id=1', headers=ADMIN).json()
    incoming = client.get('/api/stock/movements?branch_id=2', headers=ADMIN).json()
    assert any(x['reason']=='transfer_out' and x['change']==-3 and x['reference_id']==ref for x in outgoing)
    assert any(x['reason']=='transfer_in' and x['change']==3 and x['reference_id']==ref for x in incoming)
    insufficient = client.post('/api/stock/transfers', headers={**ADMIN,'Idempotency-Key':'transfer-unique-002'}, json=data)
    assert insufficient.status_code == 409
    assert next(x for x in client.get('/api/products?branch_id=2', headers=ADMIN).json() if x['id']==product_id)['stock'] == 3

def test_customer_isolation_search_and_sale_link():
    assert client.get('/api/customers?branch_id=1').status_code == 401
    assert client.post('/api/customers', headers=ADMIN, json={
        'branch_id':1,'name':'   ','phone':''}).status_code == 422
    customer = client.post('/api/customers', headers=ADMIN, json={
        'branch_id':1,'name':'María Cliente','phone':'4431234567'})
    assert customer.status_code == 201, customer.text
    customer_id = customer.json()['id']
    assert any(x['id']==customer_id for x in client.get('/api/customers?branch_id=1&q=443', headers=CASHIER).json())
    assert client.get('/api/customers?branch_id=1', headers=OUTSIDER).status_code == 404
    assert client.post('/api/customers', headers=CASHIER, json={
        'branch_id':2,'name':'Sin permiso'}).status_code == 403

    other_branch = client.get('/api/branches', headers=OUTSIDER).json()[0]['id']
    other = client.post('/api/customers', headers=OUTSIDER, json={
        'branch_id':other_branch,'name':'Cliente ajeno'})
    assert other.status_code == 201
    assert all(x['id']!=other.json()['id'] for x in client.get('/api/customers?branch_id=1', headers=ADMIN).json())

    product = client.post('/api/products', headers=ADMIN, json={
        'sku':'CUSTOMER-01','name':'Producto cliente','price':'10','branch_id':3,'stock':2})
    assert product.status_code == 201
    assert client.post('/api/cash/open', headers=ADMIN, json={'branch_id':3,'opening':'0'}).status_code == 201
    payload = {'branch_id':3,'customer_id':customer_id,'items':[{'product_id':product.json()['id'],'quantity':1}],
               'payment_method':'cash','paid':'11.60'}
    key = {**ADMIN,'Idempotency-Key':'customer-sale-001'}
    assert client.post('/api/sales', headers={**ADMIN,'Idempotency-Key':'customer-sale-bad'},
                       json={**payload,'customer_id':other.json()['id']}).status_code == 404
    sold = client.post('/api/sales', headers=key, json=payload)
    assert sold.status_code == 201, sold.text
    detail = client.get(f"/api/sales/{sold.json()['id']}", headers=ADMIN).json()
    assert detail['customer_id'] == customer_id and detail['customer_name'] == 'María Cliente'
    assert client.post('/api/sales', headers=key, json={**payload,'customer_id':None}).status_code == 409
    assert client.post('/api/sales', headers=key, json=payload).json()['replayed'] is True
    history_url = f'/api/customers/{customer_id}/sales?branch_id=3'
    assert [x['id'] for x in client.get(history_url, headers=ADMIN).json()] == [sold.json()['id']]
    assert client.get(history_url, headers=CASHIER).status_code == 403
    assert client.get(history_url, headers=OUTSIDER).status_code == 404
    assert client.get(f'/api/customers/{customer_id}/sales?branch_id=1', headers=ADMIN).json() == []

    changed = client.put(f'/api/customers/{customer_id}', headers=CASHIER, json={
        'branch_id':1,'name':'María Actualizada','phone':'4439998888'})
    assert changed.status_code == 200, changed.text
    assert changed.json()['name'] == 'María Actualizada'
    assert client.get(f"/api/sales/{sold.json()['id']}", headers=ADMIN).json()['customer_name'] == 'María Cliente'
    assert client.put(f'/api/customers/{customer_id}', headers=OUTSIDER, json={
        'branch_id':other_branch,'name':'Intento ajeno'}).status_code == 404
    assert client.put(f'/api/customers/{customer_id}', headers=CASHIER, json={
        'branch_id':2,'name':'Sin sucursal'}).status_code == 403

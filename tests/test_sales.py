import os
import tempfile
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(tempfile.mkdtemp()) / 'test.db')
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_branch_cash_sale_and_stock_ledger():
    branches = client.get('/api/branches').json()
    assert [b['name'] for b in branches] == ['Zamora','Zacapu','Uruapan','20 de Noviembre','Maravatío','CDMX']
    assert client.get('/api/branches', headers={'x-demo-empresa': '2'}).json() == []
    product = client.post('/api/products', json={'sku':'ABC-01','name':'Artículo prueba','price':'100.00','branch_id':1,'stock':2})
    assert product.status_code == 201, product.text
    product_id = product.json()['id']
    payload = {'branch_id':1,'items':[{'product_id':product_id,'quantity':2}],'payment_method':'cash','paid':'250.00'}
    key = {'Idempotency-Key':'checkout-unique-0001'}
    assert client.post('/api/sales', json=payload, headers=key).status_code == 409
    assert client.post('/api/sales', json=payload, headers={**key,'x-demo-empresa':'2'}).status_code == 404
    assert client.get('/api/products?branch_id=2').json() == []
    opened = client.post('/api/cash/open', json={'branch_id':1,'opening':'100.00'})
    assert opened.status_code == 201, opened.text
    assert client.post('/api/cash/open', json={'branch_id':1,'opening':'0'}).status_code == 409
    assert client.post('/api/sales', json={**payload,'paid':'10.00'}, headers=key).status_code == 422
    assert client.get('/api/products?branch_id=1').json()[0]['stock'] == 2
    sale = client.post('/api/sales', json=payload, headers=key)
    assert sale.status_code == 201, sale.text
    assert sale.json()['total'] == '232.00' and sale.json()['change'] == '18.00'
    replay = client.post('/api/sales', json=payload, headers=key)
    assert replay.status_code == 201 and replay.json()['replayed']
    assert client.post('/api/sales', json={**payload,'paid':'233.00'}, headers=key).status_code == 409
    assert client.get('/api/products?branch_id=1').json()[0]['stock'] == 0
    assert client.post('/api/sales', json=payload, headers={'Idempotency-Key':'checkout-unique-0002'}).status_code == 409
    assert len(client.get('/api/sales?branch_id=1').json()) == 1
    assert client.get('/api/stock/movements?branch_id=1').json()[0]['change'] == -2
    assert client.get('/api/cash/current?branch_id=1').json()['expected'] == '332.00'
    assert client.get('/api/reports/summary?branch_id=1').json()['by_method']['cash'] == '232.00'
    assert client.post(f"/api/cash/{opened.json()['id']}/withdraw",json={'amount':'500','reason':'retiro imposible'}).status_code == 409
    withdrawal = client.post(f"/api/cash/{opened.json()['id']}/withdraw",json={'amount':'20','reason':'retiro autorizado'})
    assert withdrawal.status_code == 201 and withdrawal.json()['expected_after'] == '312.00'
    close = client.post(f"/api/cash/{opened.json()['id']}/close",json={'counted':'330.00'})
    assert close.status_code == 200 and close.json()['difference'] == '18.00'
    assert client.post('/api/sales', json=payload, headers={'Idempotency-Key':'checkout-unique-0003'}).status_code == 409
    assert client.get('/api/sales?branch_id=1',headers={'x-demo-empresa':'2'}).status_code == 404

def test_stock_adjustments_are_scoped_and_traced():
    product = client.post('/api/products',json={'sku':'ABC-02','name':'Otro','price':'10','branch_id':2,'stock':0}).json()['id']
    assert client.post(f'/api/products/{product}/stock',json={'branch_id':2,'change':-1,'reason':'conteo'}).status_code == 409
    assert client.post(f'/api/products/{product}/stock',json={'branch_id':2,'change':3,'reason':'recepción'}).json()['stock'] == 3
    assert client.post(f'/api/products/{product}/stock',json={'branch_id':2,'change':1,'reason':'fraude'},headers={'x-demo-empresa':'2'}).status_code == 404
    assert client.get('/api/stock/movements?branch_id=2').json()[0]['reason'] == 'recepción'

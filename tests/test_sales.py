import os
import tempfile
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(tempfile.mkdtemp()) / 'test.db')
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_sale_stock_and_isolation():
    p = client.post('/api/products', json={'sku':'ABC-01','name':'Artículo prueba','price':'100.00','branch_id':1,'stock':2})
    assert p.status_code == 201, p.text
    product_id = p.json()['id']
    payload = {'branch_id':1,'items':[{'product_id':product_id,'quantity':2}],'payment_method':'cash','paid':'232.00'}
    wrong_company = client.post('/api/sales', json=payload, headers={'x-demo-empresa':'2'})
    assert wrong_company.status_code == 404
    assert client.get('/api/products?branch_id=2').json() == []
    insufficient = client.post('/api/sales', json={**payload,'paid':'10.00'})
    assert insufficient.status_code == 422
    assert client.get('/api/products?branch_id=1').json()[0]['stock'] == 2
    result = client.post('/api/sales', json=payload)
    assert result.status_code == 201, result.text
    assert result.json()['total'] == '232.00'
    assert client.get('/api/products?branch_id=1').json()[0]['stock'] == 0
    assert client.post('/api/sales', json=payload).status_code == 409
    assert len(client.get('/api/sales?branch_id=1').json()) == 1
    assert client.get('/api/sales?branch_id=1',headers={'x-demo-empresa':'2'}).json() == []

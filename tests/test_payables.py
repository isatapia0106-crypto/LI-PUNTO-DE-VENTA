import uuid
from concurrent.futures import ThreadPoolExecutor
from test_sales import client,ADMIN,CASHIER,OUTSIDER
from test_purchase_cancel import order


def register():
    pid,oid=order()
    data={'purchase_id':oid,'invoice':uuid.uuid4().hex,'due_date':'2020-01-01'}
    assert client.post('/api/payables',headers=ADMIN,json=data).status_code==409
    assert client.post(f'/api/purchases/{oid}/receive',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':pid,'quantity':4}]}).status_code==201
    r=client.post('/api/payables',headers=ADMIN,json=data);assert r.status_code==201,r.text
    assert client.post('/api/payables',headers=ADMIN,json=data).json()['replayed']
    return r.json()


def test_payable_permissions_partial_payments_balance_and_idempotency():
    row=register();assert row['balance']=='80.00' and row['status']=='overdue'
    url=f"/api/payables/{row['id']}/payments";data={'amount':'30','method':'transfer','reference':'Banco 001'};key=uuid.uuid4().hex
    assert client.post(url,headers={**CASHIER,'Idempotency-Key':key},json=data).status_code==403
    assert client.post(url,headers={**OUTSIDER,'Idempotency-Key':key},json=data).status_code==404
    r=client.post(url,headers={**ADMIN,'Idempotency-Key':key},json=data);assert r.status_code==201,r.text
    assert r.json()['balance']=='50.00'
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':key},json=data).json()['replayed']
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':key},json={**data,'amount':'31'}).status_code==409
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={**data,'amount':'51'}).status_code==409
    final=client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={**data,'amount':'50'}).json()
    assert final['balance']=='0.00' and final['status']=='paid' and len(final['payments'])==2
    assert client.get('/api/payables?branch_id=6',headers=CASHIER).status_code==403
    assert client.get('/api/payables?branch_id=6',headers=OUTSIDER).status_code==404


def test_concurrent_payments_never_exceed_balance():
    row=register();url=f"/api/payables/{row['id']}/payments"
    def pay(_):return client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'amount':'60','method':'transfer','reference':'Comprobante concurrente'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(pay,range(2)))
    assert sorted(codes)==[201,409]

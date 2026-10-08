import uuid
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_sales import client,ADMIN,CASHIER,OUTSIDER
from test_payables import register
from backend.app.main import engine,Purchase,Stock,PaymentIntent,Audit


def account(oid):
    return next(x for x in client.get('/api/payables?branch_id=6',headers=ADMIN).json()['items'] if x['purchase_id']==oid)


def test_reversal_reopens_balance_retains_payment_and_replay():
    row=register();key=uuid.uuid4().hex
    paid=client.post(f"/api/payables/{row['id']}/payments",headers={**ADMIN,'Idempotency-Key':key},json={'amount':'80','method':'transfer','reference':'Comprobante original'}).json()
    pid=paid['payments'][0]['id'];url=f'/api/payables/payments/{pid}/reverse';data={'reason':'Captura duplicada'}
    assert client.post(url,headers=CASHIER,json=data).status_code==403
    assert client.post(url,headers=OUTSIDER,json=data).status_code==404
    r=client.post(url,headers=ADMIN,json=data);assert r.status_code==200,r.text
    result=r.json();assert result['balance']=='80.00' and result['paid']=='0.00'
    assert result['payments'][0]['reversal_reason']==data['reason']
    assert client.post(url,headers=ADMIN,json=data).json()['replayed']
    assert client.post(url,headers=ADMIN,json={'reason':'Otro motivo'}).status_code==409
    assert client.post(f"/api/payables/{row['id']}/payments",headers={**ADMIN,'Idempotency-Key':key},json={'amount':'80','method':'transfer','reference':'Comprobante original'}).json()['balance']=='80.00'


def test_supplier_returns_stock_debt_credit_and_limits():
    row=register();oid=row['purchase_id']
    with Session(engine) as db:pid=db.get(Purchase,oid).items[0].product_id
    url=f'/api/purchases/{oid}/supplier-returns';data={'reason':'Mercancía defectuosa','credit_reference':'Credito 001','items':[{'product_id':pid,'quantity':2}]};headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex}
    assert client.post(url,headers={**OUTSIDER,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==404
    assert client.post(url,headers={**CASHIER,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==403
    result=client.post(url,headers=headers,json=data);assert result.status_code==201,result.text
    assert result.json()['total']=='40.00' and account(oid)['balance']=='40.00'
    assert client.post(url,headers=headers,json=data).json()['replayed']
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={**data,'items':[{'product_id':pid,'quantity':3}]}).status_code==409
    with Session(engine) as db:assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==2
    assert client.post(f"/api/payables/{row['id']}/payments",headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'amount':'40','method':'transfer','reference':'Pago neto'}).status_code==201
    second=client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={**data,'credit_reference':'Credito 002'});assert second.status_code==201
    now=account(oid);assert now['balance']=='0.00' and now['supplier_credit']=='40.00' and now['status']=='credit'
    assert len(client.get(url,headers=ADMIN).json())==2


def test_supplier_return_cannot_consume_reserved_stock():
    import json
    row=register();oid=row['purchase_id']
    with Session(engine) as db:
        pid=db.get(Purchase,oid).items[0].product_id
        db.add(PaymentIntent(id=uuid.uuid4().hex,empresa_id=1,branch_id=6,actor_id=1,amount=1,payload=json.dumps({'items':[{'product_id':pid,'quantity':4}]}),request_key=uuid.uuid4().hex,reservation_active=True))
        db.commit()
    r=client.post(f'/api/purchases/{oid}/supplier-returns',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'reason':'Devolver producto','credit_reference':'Crédito reservado','items':[{'product_id':pid,'quantity':1}]})
    assert r.status_code==409 and account(oid)['credits']=='0.00'


def test_partial_supplier_credits_conserve_cents():
    from test_operations import product
    pid=product(stock=0)
    sid=client.post('/api/suppliers',headers=ADMIN,json={'branch_id':6,'name':'Proveedor centavos'}).json()['id']
    order=client.post('/api/purchases',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'branch_id':6,'supplier_id':sid,'reference':'Centavos','items':[{'product_id':pid,'quantity':3,'unit_cost':'.08','tax_rate':'.16'}]}).json()
    oid=order['id']
    assert client.post(f'/api/purchases/{oid}/receive',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':pid,'quantity':3}]}).status_code==201
    assert client.post('/api/payables',headers=ADMIN,json={'purchase_id':oid,'invoice':uuid.uuid4().hex,'due_date':'2030-01-01'}).status_code==201
    totals=[]
    for index in range(3):
        r=client.post(f'/api/purchases/{oid}/supplier-returns',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'reason':'Devolución parcial','credit_reference':f'Credito parcial {index}','items':[{'product_id':pid,'quantity':1}]})
        assert r.status_code==201,r.text
        totals.append(Decimal(r.json()['total']))
    assert totals==[Decimal('.09'),Decimal('.10'),Decimal('.09')]
    assert account(oid)['credits']=='0.28' and account(oid)['balance']=='0.00'


def test_concurrent_supplier_returns_cannot_duplicate_quantities():
    from concurrent.futures import ThreadPoolExecutor
    row=register();oid=row['purchase_id']
    with Session(engine) as db:pid=db.get(Purchase,oid).items[0].product_id
    def submit(index):return client.post(f'/api/purchases/{oid}/supplier-returns',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'reason':'Devolución concurrente','credit_reference':f'Crédito {index}','items':[{'product_id':pid,'quantity':3}]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(submit,range(2)))
    assert sorted(codes)==[201,409] and account(oid)['balance']=='20.00'

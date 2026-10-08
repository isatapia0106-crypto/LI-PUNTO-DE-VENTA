import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_sales import client,ADMIN,CASHIER,OUTSIDER
from test_operations import product
from backend.app.main import engine,Stock,InventoryCountBatch


def test_batch_atomic_conflict_replay_and_scope():
    a=product(stock=10);b=product(stock=10)
    data={'branch_id':6,'reason':'Conteo de almacén','items':[{'product_id':a,'expected':10,'counted':8},{'product_id':b,'expected':9,'counted':12}]}
    headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex};url='/api/stock/counts/batch'
    assert client.post(url,headers={**CASHIER,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==403
    assert client.post(url,headers={**OUTSIDER,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==404
    assert client.post(url,headers=headers,json=data).status_code==409
    with Session(engine) as db:assert db.scalar(select(Stock).where(Stock.product_id==a,Stock.branch_id==6)).quantity==10
    data['items'][1]['expected']=10
    r=client.post(url,headers=headers,json=data);assert r.status_code==201,r.text
    assert client.post(url,headers=headers,json={**data,'items':list(reversed(data['items']))}).json()['replayed']
    assert client.post(url,headers=headers,json={**data,'items':data['items'][:1]}).status_code==409
    with Session(engine) as db:
        assert db.scalar(select(Stock).where(Stock.product_id==a,Stock.branch_id==6)).quantity==8
        assert db.scalar(select(Stock).where(Stock.product_id==b,Stock.branch_id==6)).quantity==12
        assert len(db.scalars(select(InventoryCountBatch).where(InventoryCountBatch.request_key==headers['Idempotency-Key'])).all())==1


def test_batch_rejects_duplicates_and_unknown_product():
    pid=product(stock=3);line={'product_id':pid,'expected':3,'counted':1};base={'branch_id':6,'reason':'Conteo validado'}
    headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex}
    assert client.post('/api/stock/counts/batch',headers=headers,json={**base,'items':[line,line]}).status_code==422
    assert client.post('/api/stock/counts/batch',headers=headers,json={**base,'items':[line,{**line,'product_id':999999999}]}).status_code==404
    with Session(engine) as db:assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==3


def test_batch_reservations_block_whole_transaction():
    import json
    from backend.app.main import PaymentIntent
    a=product(stock=10);b=product(stock=10)
    with Session(engine) as db:
        db.add(PaymentIntent(id=uuid.uuid4().hex,empresa_id=1,branch_id=6,actor_id=1,amount=1,payload=json.dumps({'items':[{'product_id':b,'quantity':10}]}),request_key=uuid.uuid4().hex,reservation_active=True));db.commit()
    data={'branch_id':6,'reason':'Conteo con reservas','items':[{'product_id':a,'expected':10,'counted':8},{'product_id':b,'expected':10,'counted':9}]}
    assert client.post('/api/stock/counts/batch',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==409
    with Session(engine) as db:assert db.scalar(select(Stock).where(Stock.product_id==a,Stock.branch_id==6)).quantity==10


def test_simultaneous_batch_counts_cannot_overwrite_new_stock():
    from concurrent.futures import ThreadPoolExecutor
    pid=product(stock=10)
    def submit(qty):return client.post('/api/stock/counts/batch',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'branch_id':6,'reason':'Conteo concurrente','items':[{'product_id':pid,'expected':10,'counted':qty}]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(submit,[8,12]))
    assert sorted(codes)==[201,409]

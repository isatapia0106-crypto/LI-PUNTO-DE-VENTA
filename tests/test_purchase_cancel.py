import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_sales import client,ADMIN,CASHIER,OUTSIDER
from test_operations import product,actor
from backend.app.main import engine,Stock,Audit


def order():
    pid=product(stock=0)
    sid=client.post('/api/suppliers',headers=ADMIN,json={'branch_id':6,'name':'Proveedor cancelación'}).json()['id']
    r=client.post('/api/purchases',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'branch_id':6,'supplier_id':sid,'reference':'Cancelación prueba','items':[{'product_id':pid,'quantity':4,'unit_cost':'20'}]})
    assert r.status_code==201,r.text
    return pid,r.json()['id']

@pytest.mark.parametrize('received',[0,2])
def test_cancel_preserves_received_stock_and_replay(received):
    pid,oid=order();receipt_key=uuid.uuid4().hex
    if received:
        assert client.post(f'/api/purchases/{oid}/receive',headers={**ADMIN,'Idempotency-Key':receipt_key},json={'items':[{'product_id':pid,'quantity':received}]}).status_code==201
    url=f'/api/purchases/{oid}/cancel';data={'reason':'Proveedor sin disponibilidad'}
    for headers,expected in [(CASHIER,403),(OUTSIDER,404)]:assert client.post(url,headers=headers,json=data).status_code==expected
    r=client.post(url,headers=ADMIN,json=data);assert r.status_code==200,r.text
    row=r.json();assert row['status']=='cancelled' and row['cancel_reason']==data['reason'] and row['cancelled_by']
    assert row['items'][0]['pending']==0 and row['items'][0]['cancelled']==4-received
    assert client.post(url,headers=ADMIN,json=data).json()['replayed']
    assert client.post(url,headers=ADMIN,json={'reason':'Otro motivo'}).status_code==409
    assert client.post(f'/api/purchases/{oid}/receive',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':pid,'quantity':1}]}).status_code==409
    if received:
        assert client.post(f'/api/purchases/{oid}/receive',headers={**ADMIN,'Idempotency-Key':receipt_key},json={'items':[{'product_id':pid,'quantity':received}]}).json()['replayed']
    with Session(engine) as db:
        assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==received
        assert len(db.scalars(select(Audit).where(Audit.action=='purchase_cancelled',Audit.record_id==oid)).all())==1


def test_completed_purchase_cannot_be_cancelled_and_reason_required():
    pid,oid=order();url=f'/api/purchases/{oid}/cancel'
    assert client.post(url,headers=ADMIN,json={'reason':'  '}).status_code==422
    assert client.post(f'/api/purchases/{oid}/receive',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':pid,'quantity':4}]}).status_code==201
    assert client.post(url,headers=ADMIN,json={'reason':'Cancelar completa'}).status_code==409

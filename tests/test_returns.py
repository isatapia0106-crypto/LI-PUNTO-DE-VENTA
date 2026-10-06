"""Regresiones de devoluciones parciales, efectivo y aislamiento."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_operations import actor, opened, product, payload
from test_sales import client, ADMIN, OUTSIDER
from backend.app.main import engine, Stock, SaleReturn, CashMovement

def setup_sale(**extra):
    cashier, _ = actor(); turn = opened(cashier)
    pid = product(stock=5, price='0.05', tax_exempt=True, initial_cost='2')
    data = payload(pid,turn,items=[{'product_id':pid,'quantity':3}],**extra)
    if data['payment_method'] != 'cash': data['paid']='0.15'
    r=client.post('/api/sales',headers={**cashier,'Idempotency-Key':uuid.uuid4().hex},json=data)
    assert r.status_code == 201,r.text
    detail=client.get(f"/api/sales/{r.json()['id']}",headers=ADMIN).json()
    return cashier,turn,pid,detail

def refund(sale,turn,quantity=1,**extra):
    return {'reason':'Devolución de prueba','cash_session_id':turn['id'],'items':[{'sale_item_id':sale['items'][0]['id'],'quantity':quantity,'restock':True}],**extra}

def test_partial_full_idempotency_stock_cash_reports():
    cashier,turn,pid,sale=setup_sale()
    url=f"/api/sales/{sale['id']}/returns";data=refund(sale,turn)
    key={**ADMIN,'Idempotency-Key':uuid.uuid4().hex}
    assert client.post(url,headers={**cashier,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==403
    assert client.post(url,headers={**OUTSIDER,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==404
    before=client.get('/api/reports/summary?branch_id=6',headers=ADMIN).json()
    r=client.post(url,headers=key,json=data); assert r.status_code==201,r.text
    assert Decimal(r.json()['total'])==Decimal('.05')
    assert client.post(url,headers=key,json=data).json()['replayed']
    assert client.post(url,headers=key,json={**data,'reason':'Otra devolución'}).status_code==409
    r=client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=refund(sale,turn,2))
    assert r.status_code==201 and Decimal(r.json()['total'])==Decimal('.10'),r.text
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==409
    with Session(engine) as db:
        assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==5
        assert len(db.scalars(select(SaleReturn).where(SaleReturn.sale_id==sale['id'])).all())==2
        assert len(db.scalars(select(CashMovement).where(CashMovement.session_id==turn['id'],CashMovement.kind=='refund')).all())==2
    session=next(x for x in client.get('/api/cash/sessions?branch_id=6',headers=ADMIN).json() if x['id']==turn['id'])
    assert Decimal(session['expected'])==Decimal('100')
    after=client.get('/api/reports/summary?branch_id=6',headers=ADMIN).json()
    assert Decimal(before['total'])-Decimal(after['total'])==Decimal('.15')
    assert client.get(f"/api/sales/{sale['id']}",headers=ADMIN).json()['items'][0]['returned_quantity']==3

def test_external_reference_and_non_restock():
    _,turn,pid,sale=setup_sale(payment_method='card');url=f"/api/sales/{sale['id']}/returns"
    data=refund(sale,turn,cash_session_id=None)
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==422
    data.update(payment_reference='Proveedor-ref-123',items=[{**data['items'][0],'restock':False}])
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==201
    with Session(engine) as db:
        assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==2
        assert not db.scalars(select(CashMovement).where(CashMovement.session_id==turn['id'],CashMovement.kind=='refund')).all()

def test_closed_cash_invalid_lines_atomic_and_parallel_limits():
    cashier,turn,pid,sale=setup_sale();url=f"/api/sales/{sale['id']}/returns";data=refund(sale,turn)
    invalid={**data,'items':data['items']+[{'sale_item_id':999999,'quantity':1}]}
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=invalid).status_code==422
    assert client.get(url,headers=ADMIN).json()==[]
    def submit(_):return client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=refund(sale,turn,2)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: assert sorted(pool.map(submit,range(2)))==[201,409]
    assert client.post(f"/api/cash/{turn['id']}/close",headers=cashier,json={'counted':'100.05'}).status_code==200
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==409

def test_discount_tax_cumulative_rounding_uses_original_ticket():
    cashier,_=actor();turn=opened(cashier)
    pid=product(stock=3,price='0.07',tax_rate='.16')
    data=payload(pid,turn,items=[{'product_id':pid,'quantity':3}],discount_percent='10',discount_reason='Prueba de centavos',approval={'username':'owner','password':'admin-password-123'})
    sale=client.post('/api/sales',headers={**cashier,'Idempotency-Key':uuid.uuid4().hex},json=data).json()
    detail=client.get(f"/api/sales/{sale['id']}",headers=ADMIN).json()
    amounts=[]
    for _ in range(3):
        r=client.post(f"/api/sales/{sale['id']}/returns",headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=refund(detail,turn))
        assert r.status_code==201,r.text
        amounts.append(Decimal(r.json()['total']))
    assert sum(amounts)==Decimal(sale['total'])
    assert len(set(amounts))>1


def test_insufficient_cash_and_wrong_branch_leave_no_return():
    cashier,turn,pid,sale=setup_sale()
    url=f"/api/sales/{sale['id']}/returns"
    assert client.post(f"/api/cash/{turn['id']}/withdraw",headers=ADMIN,json={'amount':'100.15','reason':'Retiro de todo el efectivo'}).status_code==201
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=refund(sale,turn)).status_code==409
    assert client.get(url,headers=ADMIN).json()==[]
    with Session(engine) as db:
        assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==2
    other,_=actor('admin_sucursal',branch=5)
    assert client.post(url,headers={**other,'Idempotency-Key':uuid.uuid4().hex},json=refund(sale,turn)).status_code==403

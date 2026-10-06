"""Cancelación y corte: atomicidad, permisos, concurrencia e historial."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_returns import setup_sale, refund
from test_operations import actor, opened, product, payload
from test_sales import client, ADMIN, OUTSIDER
from backend.app.main import engine, Stock, SaleReturn

def cancel_data(turn):return {'reason':'Venta registrada por error','cash_session_id':turn['id']}
def key(headers=ADMIN):return {**headers,'Idempotency-Key':uuid.uuid4().hex}

def test_cancel_full_replay_and_closed_cut_immutable():
    cashier,turn,pid,sale=setup_sale()
    url=f"/api/sales/{sale['id']}/cancel";headers=key();data=cancel_data(turn)
    assert client.post(url,headers=key(cashier),json=data).status_code==403
    assert client.post(url,headers=key(OUTSIDER),json=data).status_code==404
    r=client.post(url,headers=headers,json=data);assert r.status_code==201,r.text
    assert r.json()['kind']=='cancellation' and Decimal(r.json()['total'])==Decimal('.15')
    assert client.post(url,headers=headers,json=data).json()['replayed']
    assert client.post(url,headers=headers,json={**data,'reason':'Otro motivo'}).status_code==409
    assert client.post(url,headers=key(),json=data).status_code==409
    assert client.post(f"/api/sales/{sale['id']}/returns",headers=key(),json=refund(sale,turn)).status_code==409
    assert client.get(f"/api/sales/{sale['id']}",headers=ADMIN).json()['status']=='cancelled'
    with Session(engine) as db:assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==5
    close=client.post(f"/api/cash/{turn['id']}/close",headers=cashier,json={'counted':'99'})
    assert close.json()['difference']=='-1.00'
    cut=client.get(f"/api/cash/{turn['id']}/cut",headers=cashier).json()['cut']
    assert cut['snapshot'] and cut['expected']=='100.00' and cut['refunded']=='0.15'
    assert cut['payments']['cash']['gross']=='0.15' and cut['payments']['cash']['ticket_refunds']=='0.15'
    assert client.get(f"/api/cash/{turn['id']}/cut",headers=OUTSIDER).status_code==404


def test_partial_return_blocks_cancel_and_parallel_cancel_once():
    _,turn,pid,sale=setup_sale();base=f"/api/sales/{sale['id']}"
    assert client.post(base+'/returns',headers=key(),json=refund(sale,turn)).status_code==201
    assert client.post(base+'/cancel',headers=key(),json=cancel_data(turn)).status_code==409
    _,turn,pid,sale=setup_sale();url=f"/api/sales/{sale['id']}/cancel"
    def submit(_):return client.post(url,headers=key(),json=cancel_data(turn)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(submit,range(2)))==[201,409]
    with Session(engine) as db:assert len(db.scalars(select(SaleReturn).where(SaleReturn.sale_id==sale['id'])).all())==1


def test_mixed_payment_cut_and_refund_from_later_shift():
    cashier,turn,pid,sale=setup_sale()
    for method in ('card','transfer'):
        r=client.post('/api/sales',headers=key(cashier),json=payload(pid,turn,payment_method=method,paid='.05'))
        assert r.status_code==201,r.text
    cut_url=f"/api/cash/{turn['id']}/cut"
    provisional=client.get(cut_url,headers=cashier).json()['cut']
    assert provisional['payments']['card']['gross']=='0.05'
    assert provisional['payments']['transfer']['gross']=='0.05'
    assert provisional['expected']=='100.15' and provisional['sales_count']==3
    assert client.post(f"/api/cash/{turn['id']}/close",headers=cashier,json={'counted':'100.15'}).status_code==200
    frozen=client.get(cut_url,headers=cashier).json()['cut']
    later=opened(cashier)
    r=client.post(f"/api/sales/{sale['id']}/cancel",headers=key(),json=cancel_data(later))
    assert r.status_code==201,r.text
    assert client.get(cut_url,headers=cashier).json()['cut']==frozen
    later_cut=client.get(f"/api/cash/{later['id']}/cut",headers=cashier).json()['cut']
    assert later_cut['gross_sales']=='0.00' and later_cut['refunded']=='0.15' and later_cut['expected']=='99.85'


def test_external_cancel_reference_and_cash_failure_atomic():
    _,turn,pid,sale=setup_sale(payment_method='card');url=f"/api/sales/{sale['id']}/cancel"
    assert client.post(url,headers=key(),json={'reason':'Error de captura'}).status_code==422
    r=client.post(url,headers=key(),json={'reason':'Error de captura','payment_reference':'refund-terminal-99'})
    assert r.status_code==201,r.text
    _,turn,pid,sale=setup_sale()
    assert client.post(f"/api/cash/{turn['id']}/withdraw",headers=ADMIN,json={'amount':'100.15','reason':'Retiro autorizado'}).status_code==201
    assert client.post(f"/api/sales/{sale['id']}/cancel",headers=key(),json=cancel_data(turn)).status_code==409
    assert client.get(f"/api/sales/{sale['id']}",headers=ADMIN).json()['status']=='completed'
    with Session(engine) as db:assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==2

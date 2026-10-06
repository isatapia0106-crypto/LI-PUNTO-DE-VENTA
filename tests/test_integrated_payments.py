import hashlib
import hmac
import json
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
import pytest
from test_sales import client, ADMIN, OUTSIDER
from test_operations import actor, opened, product, payload
from backend.app.main import engine, PaymentIntent
from backend.app import mercado_pago as mp
from scripts.check_production import validate

@pytest.fixture
def provider(monkeypatch):
    for key,value in {'MP_ACCESS_TOKEN':'test-token','MP_WEBHOOK_SECRET':'test-secret','PUBLIC_BASE_URL':'https://pos.example.com','MP_COLLECTOR_ID':'123','MP_EMPRESA_ID':'1','MP_MODE':'test'}.items():monkeypatch.setenv(key,value)
    payments={}
    def call(method,path,payload=None,key=None):
        if path=='/checkout/preferences':return {'id':'pref-1','sandbox_init_point':'https://sandbox.mercadopago.com/checkout/'+key}
        return payments[path.split('/')[-1]]
    monkeypatch.setattr(mp,'call',call)
    return payments

def setup_intent():
    headers,_=actor();turn=opened(headers);pid=product()
    data=payload(pid,turn)
    r=client.post('/api/payments/checkout',headers={**headers,'Idempotency-Key':'payment-'+str(pid)},json=data)
    assert r.status_code==201,r.text
    return headers,turn,pid,r.json(),data

def payment(intent,**extra):return {'id':str(int.from_bytes(intent['id'].encode(),'big')),'external_reference':intent['id'],'collector_id':123,'currency_id':'MXN','transaction_amount':intent['amount'],'live_mode':False,'status':'approved',**extra}

def notify(pay,signature=True):
    pid=str(pay['id']);manifest=f'id:{pid};request-id:request-1;ts:1704908010;'
    sha=hmac.new(b'test-secret',manifest.encode(),hashlib.sha256).hexdigest()
    return client.post('/api/payments/webhook?data.id='+pid,headers={'x-request-id':'request-1','x-signature':'ts=1704908010,v1='+ (sha if signature else '0'*64)},json={'type':'payment','data':{'id':pid}})

def test_provider_approval_signature_and_single_sale(provider):
    headers,turn,pid,intent,data=setup_intent();pay=payment(intent);provider[str(pay['id'])]=pay
    assert notify(pay,False).status_code==401
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).status_code==409
    assert notify(pay).status_code==200
    r=client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={});assert r.status_code==200,r.text
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).json()['id']==r.json()['id']
    assert client.get(f"/api/sales/{r.json()['id']}",headers=headers).json()['payment_method']=='mercado_pago'
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=OUTSIDER,json={}).status_code==404

@pytest.mark.parametrize('mismatch',[{'currency_id':'USD'},{'collector_id':999},{'transaction_amount':'1'},{'live_mode':True}])
def test_provider_mismatch_rejected(provider,mismatch):
    _,_,_,intent,_=setup_intent();pay=payment(intent,**mismatch);provider[str(pay['id'])]=pay
    assert notify(pay).status_code==409


def test_pending_rejected_and_price_change_preserves_record(provider):
    headers,turn,pid,intent,_=setup_intent();pay=payment(intent,status='pending');provider[str(pay['id'])]=pay
    assert notify(pay).status_code==200
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).status_code==409
    pay['status']='approved';notify(pay)
    from backend.app.main import Product
    with Session(engine) as db:db.get(Product,pid).price=Decimal('150');db.commit()
    r=client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={})
    assert r.status_code==200,r.text
    assert r.json()['total']==intent['amount']
    with Session(engine) as db:
        saved=db.get(PaymentIntent,intent['id'])
        assert saved.status=='completed' and not saved.reservation_active


def test_disabled_and_production_config(monkeypatch):
    monkeypatch.delenv('MP_ACCESS_TOKEN',raising=False)
    with pytest.raises(Exception):mp.settings()
    env={'APP_ENV':'production','DATABASE_URL':'postgresql+psycopg://db','JWT_SECRET':'x'*64,'PUBLIC_BASE_URL':'https://pos.example.com','MP_MODE':'test'}
    assert validate(env)
    with pytest.raises(ValueError):validate({**env,'JWT_SECRET':'weak'})
    with pytest.raises(ValueError):validate({**env,'MP_MODE':'live','MP_LIVE_ENABLED':'false'})

def test_reservation_blocks_manual_stock_changes_and_releases_on_sale(provider):
    from backend.app.main import Stock, reserved_quantity
    headers,turn,pid,intent,data=setup_intent()
    with Session(engine) as db:
        stock=db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6))
        stock.quantity=data['items'][0]['quantity'];db.commit()
        assert reserved_quantity(db,6,pid)==stock.quantity
    assert client.post('/api/sales',headers={**headers,'Idempotency-Key':'manual-'+str(pid)},json=data).status_code==409
    assert client.post(f'/api/products/{pid}/stock',headers=ADMIN,json={'branch_id':6,'change':-1,'reason':'ajuste'}).status_code==409
    assert client.post('/api/stock/transfers',headers={**ADMIN,'Idempotency-Key':'transfer-'+str(pid)},json={'source_branch_id':6,'target_branch_id':2,'product_id':pid,'quantity':1}).status_code==409
    assert client.post('/api/stock/counts',headers={**ADMIN,'Idempotency-Key':'reserved-count-'+str(pid)},json={'branch_id':6,'product_id':pid,'expected':1,'counted':0,'reason':'conteo físico'}).status_code==409
    pay=payment(intent);provider[str(pay['id'])]=pay;assert notify(pay).status_code==200
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).status_code==200
    with Session(engine) as db:assert reserved_quantity(db,6,pid)==0


def test_reconcile_missing_webhook_and_persist_chargeback(provider,monkeypatch):
    headers,_,_,intent,_=setup_intent();pay=payment(intent)
    def call(method,path,payload=None,key=None):
        if path.startswith('/v1/payments/search?'):return {'results':[{'id':pay['id'],'external_reference':intent['id']}],'paging':{'total':1}}
        return pay
    monkeypatch.setattr(mp,'call',call)
    r=client.post(f"/api/payments/{intent['id']}/reconcile",headers=headers,json={})
    assert r.status_code==200,r.text
    assert r.json()['status']=='approved'
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).status_code==200
    pay['status']='charged_back'
    r=client.post(f"/api/payments/{intent['id']}/reconcile",headers=headers,json={})
    assert r.status_code==200 and 'charged_back' in r.json()['review_reason']
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).status_code==409
    assert client.post(f"/api/payments/{intent['id']}/reconcile",headers=OUTSIDER,json={}).status_code==404

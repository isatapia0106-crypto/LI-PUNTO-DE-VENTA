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

@pytest.fixture
def cancellation_provider(provider,monkeypatch):
    state={'payments':{},'expires':False,'expiration_date_to':None,'calls':[], 'fail':None,'late':False}
    def install(intent):
        state['intent']=intent
        def call(method,path,payload=None,key=None):
            state['calls'].append((method,path))
            if state['fail'] and method==state['fail'][0] and path.startswith(state['fail'][1]):
                from fastapi import HTTPException
                raise HTTPException(502,'Proveedor temporalmente no disponible')
            if path.startswith('/v1/payments/search?'):
                return {'results':list(state['payments'].values()),'paging':{'total':len(state['payments'])}}
            if path.startswith('/checkout/preferences/search?'):
                return {'elements':[{'id':'pref-1'}],'total':1}
            if path=='/checkout/preferences/pref-1':
                if method=='PUT':
                    state.update(payload)
                return {'id':'pref-1','external_reference':intent['id'],'collector_id':123,
                        'expires':state['expires'],'expiration_date_to':state['expiration_date_to']}
            pid=path.split('/')[-1]
            pay=state['payments'][pid]
            if method=='PUT':pay['status']='approved' if state['late'] else 'cancelled'
            return pay
        monkeypatch.setattr(mp,'call',call)
        return state
    return install


def cancel(intent,headers,reason='Cliente abandonó el cobro'):
    return client.post(f"/api/payments/{intent['id']}/cancel",headers=headers,json={'reason':reason})


def test_cancel_unused_checkout_release_replay_and_late_payment(cancellation_provider):
    from backend.app.main import reserved_quantity
    headers,_,pid,intent,_=setup_intent();state=cancellation_provider(intent)
    assert cancel(intent,OUTSIDER).status_code==404
    r=cancel(intent,headers);assert r.status_code==200,r.text
    assert r.json()['status']=='cancelled' and not r.json()['reserved'] and r.json()['checkout_url'] is None
    with Session(engine) as db:assert reserved_quantity(db,6,pid)==0
    before=len(state['calls']);assert cancel(intent,headers).status_code==200
    assert len(state['calls'])==before
    pay=payment(intent);state['payments'][str(pay['id'])]=pay
    assert notify(pay).status_code==200
    with Session(engine) as db:
        saved=db.get(PaymentIntent,intent['id'])
        assert saved.status=='cancelled' and not saved.reservation_active
        assert 'después de cancelación' in saved.review_reason
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).status_code==409


def test_cancel_pending_payment_verified_before_release(cancellation_provider):
    headers,_,_,intent,_=setup_intent();state=cancellation_provider(intent)
    pay=payment(intent,status='pending');state['payments'][str(pay['id'])]=pay
    assert notify(pay).status_code==200
    r=cancel(intent,headers);assert r.status_code==200,r.text
    assert pay['status']=='cancelled' and not r.json()['reserved']


def test_cancel_timeout_retains_reservation_and_retry_completes(cancellation_provider):
    headers,_,_,intent,_=setup_intent();state=cancellation_provider(intent)
    state['fail']=('PUT','/checkout/preferences/')
    assert cancel(intent,headers).status_code==502
    with Session(engine) as db:
        saved=db.get(PaymentIntent,intent['id'])
        assert saved.reservation_active and saved.cancel_requested_at and not saved.cancelled_at
        assert saved.status=='cancel_pending'
    state['fail']=None
    assert cancel(intent,headers).json()['reserved'] is False


def test_approval_races_pending_cancellation_retains_stock(cancellation_provider):
    headers,_,_,intent,_=setup_intent();state=cancellation_provider(intent)
    pay=payment(intent,status='pending');state['payments'][str(pay['id'])]=pay;state['late']=True
    assert cancel(intent,headers).status_code==409
    with Session(engine) as db:
        saved=db.get(PaymentIntent,intent['id'])
        assert saved.reservation_active and not saved.cancelled_at and saved.review_reason
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).status_code==409


def test_approved_checkout_cannot_be_cancelled(cancellation_provider):
    headers,_,_,intent,_=setup_intent();state=cancellation_provider(intent)
    pay=payment(intent);state['payments'][str(pay['id'])]=pay;assert notify(pay).status_code==200
    before=len(state['calls']);assert cancel(intent,headers).status_code==409
    assert len(state['calls'])==before
    with Session(engine) as db:assert db.get(PaymentIntent,intent['id']).cancel_requested_at is None


def test_cancel_unverified_expiry_and_missing_preference_keep_reservation(cancellation_provider,monkeypatch):
    headers,_,_,intent,_=setup_intent();state=cancellation_provider(intent)
    original=mp.call
    def unconfirmed(method,path,payload=None,key=None):
        result=original(method,path,payload,key)
        if method=='GET' and path=='/checkout/preferences/pref-1':result['expires']=False
        return result
    monkeypatch.setattr(mp,'call',unconfirmed)
    assert cancel(intent,headers).status_code==409
    with Session(engine) as db:
        saved=db.get(PaymentIntent,intent['id']);assert saved.reservation_active
        saved.preference_id=None;db.commit()
    def missing(method,path,payload=None,key=None):
        if path.startswith('/checkout/preferences/search?'):return {'elements':[],'total':0}
        return original(method,path,payload,key)
    monkeypatch.setattr(mp,'call',missing)
    assert cancel(intent,headers).status_code==409
    with Session(engine) as db:assert db.get(PaymentIntent,intent['id']).reservation_active


def test_cancel_recovers_preference_after_lost_creation_response(cancellation_provider):
    headers,_,_,intent,_=setup_intent();state=cancellation_provider(intent)
    with Session(engine) as db:
        saved=db.get(PaymentIntent,intent['id']);saved.preference_id=None;saved.checkout_url=None;saved.status='creating';db.commit()
    r=cancel(intent,headers);assert r.status_code==200,r.text
    assert not r.json()['reserved']
    with Session(engine) as db:assert db.get(PaymentIntent,intent['id']).preference_id=='pref-1'


def test_approved_payment_delivery_after_closed_shift_preserves_cut_and_replay(provider):
    from backend.app.main import Stock, Audit
    headers,old,pid,intent,_=setup_intent()
    assert client.post(f"/api/cash/{old['id']}/close",headers=headers,json={'counted':'100'}).status_code==200
    frozen=client.get(f"/api/cash/{old['id']}/cut",headers=headers).json()['cut']
    pay=payment(intent);provider[str(pay['id'])]=pay;assert notify(pay).status_code==200
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).status_code==409
    new=opened(headers)
    r=client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={'cash_session_id':new['id']})
    assert r.status_code==200,r.text
    sale=r.json()
    assert client.get(f"/api/cash/{old['id']}/cut",headers=headers).json()['cut']==frozen
    current=client.get(f"/api/cash/{new['id']}/cut",headers=headers).json()['cut']
    assert current['payments']['mercado_pago']['gross']==intent['amount']
    assert current['expected']=='100.00' and current['sales_count']==1
    with Session(engine) as db:
        stored=db.get(PaymentIntent,intent['id'])
        assert json.loads(stored.payload)['cash_session_id']==old['id']
        assert stored.delivery_cash_session_id==new['id'] and stored.delivered_at
        assert not stored.reservation_active
        assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==9
        assert db.scalar(select(Audit).where(Audit.action=='payment_delivered_new_shift',Audit.record_id==sale['id']))
    assert client.post(f"/api/cash/{new['id']}/close",headers=headers,json={'counted':'100'}).status_code==200
    # Even a retry with the original shift returns the existing ticket.
    repeated=client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={'cash_session_id':old['id']})
    assert repeated.status_code==200 and repeated.json()['id']==sale['id'] and repeated.json()['replayed']
    with Session(engine) as db:assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity==9


def test_delivery_rejects_other_cashier_branch_and_closed_destination(provider):
    from backend.app.main import CashSession, CashRegister
    headers,old,_,intent,_=setup_intent();pay=payment(intent);provider[str(pay['id'])]=pay;notify(pay)
    other,_=actor();other_turn=opened(other)
    # Original open shift must not be rerouted, even to another open register.
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={'cash_session_id':other_turn['id']}).status_code==409
    client.post(f"/api/cash/{old['id']}/close",headers=headers,json={'counted':'100'})
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={'cash_session_id':other_turn['id']}).status_code==403
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=other,json={'cash_session_id':other_turn['id']}).status_code==404
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={'cash_session_id':old['id']}).status_code==409
    # A shift in a different branch is never eligible, even for the same cashier.
    with Session(engine) as db:
        uid=db.get(PaymentIntent,intent['id']).actor_id
        register=db.scalar(select(CashRegister).where(CashRegister.branch_id==1))
        foreign=CashSession(empresa_id=1,branch_id=1,cashier_id=uid,register_id=register.id,opening=Decimal('100'))
        db.add(foreign);db.commit();foreign_id=foreign.id
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={'cash_session_id':foreign_id}).status_code==409
    with Session(engine) as db:
        db.get(CashSession,foreign_id).status='closed';db.commit()
    with Session(engine) as db:
        stored=db.get(PaymentIntent,intent['id'])
        assert stored.reservation_active and stored.delivery_cash_session_id is None

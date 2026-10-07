from datetime import datetime, timezone
import uuid
from sqlalchemy.orm import Session
from test_sales import client, ADMIN, CASHIER, OUTSIDER
from test_integrated_payments import provider, setup_intent, payment, notify
from backend.app.main import engine, Audit, PaymentObservation, User


def query(path, headers=ADMIN, **extra):
    return client.get(path, headers=headers, params={'branch_id':6,'start':'2020-01-01','end':'2020-12-31',**extra})


def test_control_permissions_dates_and_company_scope():
    for path in ['/api/audit','/api/reports/payments/reconciliation']:
        assert query(path,{}).status_code==401
        assert query(path,CASHIER).status_code==403
        assert query(path,OUTSIDER).status_code==404
        assert query(path,start='2026-10-07',end='2026-10-06').status_code==422
        assert query(path,end='2022-12-31').status_code==422


def test_audit_filters_pagination_and_hidden_company_events():
    action='control-'+uuid.uuid4().hex[:15]
    with Session(engine) as db:
        owner=db.query(User).filter_by(username='owner').one()
        for x in range(103):db.add(Audit(empresa_id=1,branch_id=6,action=action,record_id=x,actor_id=owner.id,created_at=datetime(2020,6,1,tzinfo=timezone.utc)))
        db.add(Audit(empresa_id=2,branch_id=6,action=action,record_id=999,created_at=datetime(2020,6,1,tzinfo=timezone.utc)))
        db.commit();uid=owner.id
    first=query('/api/audit',action=action,actor_id=uid).json()
    assert len(first['items'])==100 and first['next_cursor']
    second=query('/api/audit',action=action,actor_id=uid,before_id=first['next_cursor']).json()
    assert len(second['items'])==3 and second['next_cursor'] is None
    assert not set(r['id'] for r in first['items'])&set(r['id'] for r in second['items'])
    assert all(r['actor']=='owner' and r['record_id']!=999 for r in first['items']+second['items'])


def test_reconciliation_tracks_verified_difference_without_provider_calls(provider,monkeypatch):
    from backend.app import mercado_pago as mp
    headers,_,_,intent,_=setup_intent();pay=payment(intent);provider[str(pay['id'])]=pay
    assert notify(pay).status_code==200
    assert client.post(f"/api/payments/{intent['id']}/confirm",headers=headers,json={}).status_code==200
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo('America/Mexico_City')).date().isoformat()
    def read():
        r=query('/api/reports/payments/reconciliation',start=today,end=today)
        assert r.status_code==200,r.text
        return next(row for row in r.json()['items'] if row['id']==intent['id'])
    monkeypatch.setattr(mp,'call',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Report must not call provider')))
    row=read();assert row['state']=='matched' and row['difference']=='0.00'
    with Session(engine) as db:
        original=db.get(PaymentObservation,str(pay['id']));original.refunded=1;db.commit()
    row=read();assert row['state']=='review' and row['difference']=='-1.00'
    assert 'Reembolso principal diferente del registro local' in row['issues']

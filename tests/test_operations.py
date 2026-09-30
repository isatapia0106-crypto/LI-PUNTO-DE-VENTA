"""Financial and inventory regression tests for blocks 3, 4 and 5."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_sales import client, ADMIN, OUTSIDER, auth
from backend.app.main import engine, User, UserBranch, Sale, Stock, InventoryCount, password_hash


def actor(role='cajero', branch=6):
    username = 'ops-' + uuid.uuid4().hex[:16]
    with Session(engine) as db:
        user = User(username=username, empresa_id=1, role=role, password_hash=password_hash.hash('operations-password-123'))
        db.add(user)
        db.flush()
        uid = user.id
        db.add(UserBranch(user_id=uid, branch_id=branch))
        db.commit()
    return auth(username, 'operations-password-123'), uid


def product(**extra):
    data = {'branch_id':6, 'sku':'OPS-'+uuid.uuid4().hex, 'name':'Producto operaciones', 'price':'100', 'stock':10, **extra}
    r = client.post('/api/products', headers=ADMIN, json=data)
    assert r.status_code == 201, r.text
    return r.json()['id']


def register():
    r = client.post('/api/cash/registers', headers=ADMIN, json={'branch_id':6,'name':'Caja '+uuid.uuid4().hex[:12]})
    assert r.status_code == 201, r.text
    return r.json()['id']


def opened(headers):
    rid = register()
    r = client.post('/api/cash/open', headers=headers, json={'branch_id':6,'register_id':rid,'opening':'100'})
    assert r.status_code == 201, r.text
    return r.json()


def payload(pid, session, **extra):
    return {'branch_id':6,'cash_session_id':session['id'],'items':[{'product_id':pid,'quantity':1}], 'payment_method':'cash','paid':'200', **extra}


def test_mixed_tax_discount_authorization_and_historical_ticket():
    cashier, uid = actor()
    turn = opened(cashier)
    included = product(price='116', price_includes_tax=True, barcode=uuid.uuid4().hex)
    exempt = product(price='50', tax_exempt=True)
    zero = product(price='10', tax_rate='0')
    data = payload(included, turn, items=[{'product_id':p,'quantity':1} for p in [included, exempt, zero]], discount_percent='10', discount_reason='Promoción autorizada')
    quote = client.post('/api/sales/quote', headers=cashier, json=data)
    assert quote.status_code == 200, quote.text
    assert quote.json() == {'subtotal':'144.00','tax':'14.40','discount_total':'17.60','total':'158.40'}
    key = {**cashier, 'Idempotency-Key':'mixed-'+uuid.uuid4().hex}
    assert client.post('/api/sales', headers=key, json=data).status_code == 403
    assert client.post('/api/sales', headers=key, json={**data,'approval':{'username':'owner','password':'wrong'}}).status_code == 403
    data['approval'] = {'username':'owner','password':'admin-password-123'}
    sold = client.post('/api/sales', headers=key, json=data)
    assert sold.status_code == 201, sold.text
    assert sold.json()['total'] == '158.40'
    assert sold.json()['folio'].startswith('LI-B6-')
    detail = client.get(f"/api/sales/{sold.json()['id']}", headers=cashier).json()
    assert detail['discount_total'] == '17.60' and detail['actor_id'] == uid
    assert sum(Decimal(x['net']) for x in detail['items']) == Decimal('144')
    assert sum(Decimal(x['tax']) for x in detail['items']) == Decimal('14.40')
    assert client.post('/api/sales', headers=key, json=data).json()['replayed']
    assert client.post('/api/sales', headers=key, json={**data, 'discount_percent':'5'}).status_code == 409
    edit = {'branch_id':6,'sku':'EDIT-'+uuid.uuid4().hex,'name':'Nuevo nombre','price':'200','tax_rate':'0'}
    assert client.put(f'/api/products/{included}', headers=ADMIN, json=edit).status_code == 200
    again = client.get(f"/api/sales/{detail['id']}", headers=cashier).json()
    assert again['items'] == detail['items'] and again['folio'] == detail['folio']


def test_product_barcode_uniqueness_inactive_and_validation():
    code = uuid.uuid4().hex
    pid = product(barcode=code)
    duplicate = client.post('/api/products', headers=ADMIN, json={'branch_id':6,'sku':uuid.uuid4().hex,'name':'Duplicado','price':'1','stock':0,'barcode':code})
    assert duplicate.status_code == 409
    assert client.post('/api/products', headers=ADMIN, json={'branch_id':6,'sku':' ','name':' ','price':'.001','stock':0}).status_code == 422
    cashier, _ = actor()
    turn = opened(cashier)
    assert client.put(f'/api/products/{pid}', headers=cashier, json={'branch_id':6,'sku':code,'name':'Fraude','price':'10'}).status_code == 403
    assert client.put(f'/api/products/{pid}', headers=ADMIN, json={'branch_id':6,'sku':code,'name':'Inactivo','price':'100','active':False}).status_code == 200
    assert client.post('/api/sales', headers={**cashier,'Idempotency-Key':uuid.uuid4().hex}, json=payload(pid,turn)).status_code == 409


def test_multiple_registers_turn_ownership_entries_retries_and_close():
    first, _ = actor()
    second, _ = actor()
    a = opened(first)
    b = opened(second)
    assert a['id'] != b['id'] and a['register_id'] != b['register_id']
    assert client.post('/api/cash/open', headers=first, json={'branch_id':6,'register_id':register(),'opening':0}).status_code == 409
    assert client.post('/api/cash/open', headers=second, json={'branch_id':6,'register_id':a['register_id'],'opening':0}).status_code == 409
    assert client.get(f"/api/cash/current?branch_id=6&register_id={a['register_id']}", headers=second).status_code == 403
    assert client.post(f"/api/cash/{a['id']}/close", headers=second, json={'counted':100}).status_code == 403
    pid = product()
    assert client.post('/api/sales', headers={**second,'Idempotency-Key':uuid.uuid4().hex}, json=payload(pid,a)).status_code == 403
    assert client.post(f"/api/cash/{a['id']}/deposit", headers=first, json={'amount':20,'reason':'Cambio'}).status_code == 403
    key = {**ADMIN,'Idempotency-Key':'deposit-'+uuid.uuid4().hex}
    url = f"/api/cash/{a['id']}/deposit"
    assert client.post(url, headers=key, json={'amount':20,'reason':'Cambio'}).json()['expected_after'] == '120.00'
    assert client.post(url, headers=key, json={'amount':20,'reason':'Cambio'}).json()['replayed']
    assert client.post(url, headers=key, json={'amount':21,'reason':'Cambio'}).status_code == 409
    withdrawn = client.post(f"/api/cash/{a['id']}/withdraw",headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'amount':30,'reason':'Retiro autorizado'})
    assert withdrawn.status_code == 201 and withdrawn.json()['expected_after'] == '90.00'
    moves = client.get(f"/api/cash/{a['id']}/movements",headers=first).json()
    assert len(moves) == 2 and all(x['actor_id'] for x in moves)
    assert client.get(f"/api/cash/{a['id']}/movements",headers=second).status_code == 403
    close = client.post(f"/api/cash/{a['id']}/close",headers=first,json={'counted':89})
    assert close.status_code == 200 and close.json()['difference'] == '-1.00'
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'amount':1,'reason':'Cerrado'}).status_code == 409
    assert client.post('/api/sales',headers={**first,'Idempotency-Key':uuid.uuid4().hex},json=payload(pid,a)).status_code == 409


def test_purchase_partial_reception_costs_permissions_and_idempotency():
    pid = product(stock=2, initial_cost='10')
    supplier = client.post('/api/suppliers', headers=ADMIN, json={'branch_id':6,'name':'Proveedor de prueba'}).json()['id']
    data = {'branch_id':6,'supplier_id':supplier,'reference':'Orden de prueba','items':[{'product_id':pid,'quantity':4,'unit_cost':'20'}]}
    key = {**ADMIN,'Idempotency-Key':'purchase-'+uuid.uuid4().hex}
    cashier, _ = actor()
    assert client.post('/api/purchases',headers=cashier,json=data).status_code in (403,422)
    created = client.post('/api/purchases',headers=key,json=data)
    assert created.status_code == 201, created.text
    purchase_id = created.json()['id']
    assert client.put(f'/api/suppliers/{supplier}',headers=OUTSIDER,json={'branch_id':7,'name':'Intento ajeno'}).status_code == 404
    assert client.put(f'/api/suppliers/{supplier}',headers=ADMIN,json={'branch_id':6,'name':'Proveedor actualizado','phone':'4431234567'}).status_code == 200
    assert client.post('/api/purchases',headers=key,json=data).json()['replayed']
    assert client.post('/api/purchases',headers=key,json={**data,'reference':'Otra orden'}).status_code == 409
    def stock():
        return next(x for x in client.get('/api/products?branch_id=6',headers=ADMIN).json() if x['id']==pid)
    assert stock()['stock'] == 2
    warehouse, _ = actor('almacenista')
    receive_url = f'/api/purchases/{purchase_id}/receive'
    receive_key = {**warehouse,'Idempotency-Key':'receive-'+uuid.uuid4().hex}
    receipt = client.post(receive_url,headers=receive_key,json={'items':[{'product_id':pid,'quantity':2}]})
    assert receipt.status_code == 201 and receipt.json()['status'] == 'partial', receipt.text
    assert stock()['stock'] == 4 and stock()['average_cost'] == '15.0000'
    assert client.post(receive_url,headers=receive_key,json={'items':[{'product_id':pid,'quantity':2}]}).json()['replayed']
    assert stock()['stock'] == 4
    assert client.post(receive_url,headers=receive_key,json={'items':[{'product_id':pid,'quantity':1}]}).status_code == 409
    assert client.post(receive_url,headers={**warehouse,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':pid,'quantity':3}]}).status_code == 409
    assert stock()['stock'] == 4
    complete = client.post(receive_url,headers={**warehouse,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':pid,'quantity':2}]})
    assert complete.status_code == 201 and complete.json()['status'] == 'received'
    assert stock()['stock'] == 6 and stock()['average_cost'] == '16.6667'
    history = client.get(f'/api/purchases/{purchase_id}/receipts',headers=warehouse)
    assert history.status_code == 200 and len(history.json()) == 2
    assert all(x['actor_id'] for x in history.json())
    assert client.get(f'/api/purchases/{purchase_id}/receipts',headers=OUTSIDER).status_code == 404
    assert client.get('/api/purchases?branch_id=6',headers=OUTSIDER).status_code == 404
    assert client.post(receive_url,headers={**OUTSIDER,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':pid,'quantity':1}]}).status_code == 404
    assert client.post(receive_url,headers={**cashier,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':pid,'quantity':1}]}).status_code == 403


def test_receipt_is_atomic_across_lines_and_initializes_destination_stock():
    stocked = product(stock=0)
    elsewhere = product(stock=0, branch_id=5)
    supplier = client.post('/api/suppliers',headers=ADMIN,json={'branch_id':6,'name':'Otro proveedor'}).json()['id']
    order = client.post('/api/purchases',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'branch_id':6,'supplier_id':supplier,'reference':'Dos partidas',
          'items':[{'product_id':stocked,'quantity':2,'unit_cost':5},{'product_id':elsewhere,'quantity':1,'unit_cost':8}]}).json()
    url = f"/api/purchases/{order['id']}/receive"
    failed = client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':stocked,'quantity':2},{'product_id':elsewhere,'quantity':2}]})
    assert failed.status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(Stock).where(Stock.product_id==stocked,Stock.branch_id==6)).quantity == 0
        assert db.scalar(select(Stock).where(Stock.product_id==elsewhere,Stock.branch_id==6)) is None
    assert client.post(url,headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':stocked,'quantity':2},{'product_id':elsewhere,'quantity':1}]}).status_code == 201
    with Session(engine) as db:
        assert db.scalar(select(Stock).where(Stock.product_id==elsewhere,Stock.branch_id==6)).quantity == 1


def test_inventory_count_snapshot_scope_and_retries():
    pid = product(stock=5,initial_cost=7)
    data = {'branch_id':6,'product_id':pid,'expected':5,'counted':3,'reason':'Conteo físico de cierre'}
    cashier, _ = actor()
    key = {**ADMIN,'Idempotency-Key':uuid.uuid4().hex}
    assert client.post('/api/stock/counts',headers={**cashier,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code == 403
    r = client.post('/api/stock/counts',headers=key,json=data)
    assert r.status_code == 201 and r.json()['difference'] == -2, r.text
    assert client.post('/api/stock/counts',headers=key,json=data).json()['replayed']
    assert client.post('/api/stock/counts',headers=key,json={**data,'counted':4}).status_code == 409
    assert client.post('/api/stock/counts',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code == 409
    assert client.post('/api/stock/counts',headers={**OUTSIDER,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code == 404
    with Session(engine) as db:
        stock = db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6))
        assert stock.quantity == 3 and stock.average_cost == Decimal('7')
        assert len(db.scalars(select(InventoryCount).where(InventoryCount.product_id==pid)).all()) == 1


def test_simultaneous_checkouts_cannot_oversell_sqlite():
    a, _ = actor()
    b, _ = actor()
    a_turn, b_turn = opened(a), opened(b)
    pid = product(stock=1)
    def buy(pair):
        headers, turn = pair
        return client.post('/api/sales',headers={**headers,'Idempotency-Key':uuid.uuid4().hex},json=payload(pid,turn)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(buy, [(a,a_turn),(b,b_turn)]))
    assert sorted(statuses) == [201,409]
    with Session(engine) as db:
        assert db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==6)).quantity == 0

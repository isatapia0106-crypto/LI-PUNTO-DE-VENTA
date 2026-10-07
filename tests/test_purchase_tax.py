import uuid
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_sales import client,ADMIN
from test_operations import product
from backend.app.main import engine,Stock


def test_mixed_purchase_taxes_rounding_idempotency_and_inventory_cost():
    a=product(stock=0);b=product(stock=0)
    sid=client.post('/api/suppliers',headers=ADMIN,json={'branch_id':6,'name':'Proveedor impuestos'}).json()['id']
    data={'branch_id':6,'supplier_id':sid,'reference':'Impuestos mixtos','items':[{'product_id':a,'quantity':3,'unit_cost':'0.3333','tax_rate':'.16'},{'product_id':b,'quantity':2,'unit_cost':'10','tax_rate':'0'}]}
    headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex}
    r=client.post('/api/purchases',headers=headers,json=data);assert r.status_code==201,r.text
    row=r.json();assert row['total_cost']=='21.00' and row['tax']=='0.16' and row['total']=='21.16'
    assert client.post('/api/purchases',headers=headers,json=data).json()['replayed']
    data['items'][0]['tax_rate']='.08'
    assert client.post('/api/purchases',headers=headers,json=data).status_code==409
    data['items'][0]['tax_rate']='1.01'
    assert client.post('/api/purchases',headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json=data).status_code==422
    assert client.post(f"/api/purchases/{row['id']}/receive",headers={**ADMIN,'Idempotency-Key':uuid.uuid4().hex},json={'items':[{'product_id':a,'quantity':1}]}).status_code==201
    with Session(engine) as db:
        stock=db.scalar(select(Stock).where(Stock.product_id==a,Stock.branch_id==6));assert stock.average_cost==Decimal('.3333') and stock.quantity==1

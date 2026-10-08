"""Accounts payable: explicit recognition and manual external payment ledger."""
from datetime import date,datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator

class PayableIn(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    purchase_id:int=Field(gt=0)
    invoice:str=Field(min_length=1,max_length=100)
    due_date:date
    @field_validator('invoice')
    @classmethod
    def invoice_key(cls,value):return value.upper()

class PayablePaymentIn(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    amount:Decimal=Field(gt=0,le=9999999999,decimal_places=2)
    method:Literal['transfer','card']
    reference:str=Field(min_length=3,max_length=100)


def view(db,record):
    from . import main as p
    payments=db.scalars(p.select(p.PayablePayment).where(p.PayablePayment.payable_id==record.id).order_by(p.PayablePayment.id)).all()
    paid=sum((x.amount for x in payments),Decimal('0'));balance=record.amount-paid
    today=datetime.now(ZoneInfo('America/Mexico_City')).date()
    return {'id':record.id,'purchase_id':record.purchase_id,'supplier_id':record.supplier_id,
        'supplier':db.get(p.Supplier,record.supplier_id).name,'invoice':record.invoice,'due_date':record.due_date.isoformat(),
        'amount':str(record.amount),'paid':str(p.money(paid)),'balance':str(p.money(balance)),
        'status':'paid' if not balance else 'overdue' if record.due_date<today else 'pending',
        'payments':[{'id':x.id,'amount':str(x.amount),'reference':x.reference,'method':x.method,
                     'actor_id':x.actor_id,'created_at':x.created_at.isoformat()} for x in payments]}


def create_payable(data,user):
    from . import main as p
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import IntegrityError
    p.require(user,'payable_write')
    with Session(p.engine) as db:
        purchase=db.scalar(p.select(p.Purchase).where(p.Purchase.id==data.purchase_id,p.Purchase.empresa_id==user.empresa_id))
        if purchase is None:raise p.HTTPException(404,'Compra no encontrada')
        p.branch_for(db,user,purchase.branch_id)
        db.scalar(p.select(p.Branch).where(p.Branch.id==purchase.branch_id).with_for_update())
        db.refresh(purchase,with_for_update=True)
        previous=db.scalar(p.select(p.Payable).where(p.Payable.purchase_id==purchase.id))
        if previous:
            if previous.invoice!=data.invoice or previous.due_date!=data.due_date:raise p.HTTPException(409,'Compra ya reconocida con otra factura o vencimiento')
            return {**view(db,previous),'replayed':True}
        if purchase.status!='received':raise p.HTTPException(409,'Primero recibe la orden completa; este flujo no admite facturación parcial')
        amount=Decimal(p.purchase_view(db,purchase)['total'])
        if amount<=0 or amount>Decimal('9999999999.99'):raise p.HTTPException(422,'Importe fuera de rango para cuentas por pagar')
        record=p.Payable(empresa_id=user.empresa_id,branch_id=purchase.branch_id,supplier_id=purchase.supplier_id,
            purchase_id=purchase.id,invoice=data.invoice,due_date=data.due_date,amount=amount,actor_id=user.id)
        db.add(record)
        try:
            db.flush();db.add(p.Audit(empresa_id=user.empresa_id,branch_id=purchase.branch_id,actor_id=user.id,action='payable_registered',record_id=record.id))
            result={**view(db,record),'replayed':False};db.commit();return result
        except IntegrityError:raise p.HTTPException(409,'Factura ya registrada para este proveedor')


def list_payables(branch_id,before_id,user):
    from . import main as p
    from sqlalchemy.orm import Session
    p.require(user,'report')
    with Session(p.engine) as db:
        p.branch_for(db,user,branch_id)
        q=p.select(p.Payable).where(p.Payable.empresa_id==user.empresa_id,p.Payable.branch_id==branch_id)
        if before_id:q=q.where(p.Payable.id<before_id)
        records=db.scalars(q.order_by(p.Payable.id.desc()).limit(101)).all()
        return {'items':[view(db,r) for r in records[:100]],'next_cursor':records[99].id if len(records)>100 else None}


def add_payable_payment(payable_id,data,key,user):
    from . import main as p
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import IntegrityError
    p.require(user,'payable_write')
    with Session(p.engine) as db:
        record=db.scalar(p.select(p.Payable).where(p.Payable.id==payable_id,p.Payable.empresa_id==user.empresa_id))
        if record is None:raise p.HTTPException(404,'Cuenta por pagar no encontrada')
        p.branch_for(db,user,record.branch_id)
        db.scalar(p.select(p.Branch).where(p.Branch.id==record.branch_id).with_for_update())
        db.refresh(record,with_for_update=True)
        old=db.scalar(p.select(p.PayablePayment).where(p.PayablePayment.empresa_id==user.empresa_id,p.PayablePayment.request_key==key))
        if old:
            if (old.payable_id,old.amount,old.method,old.reference)!=(record.id,data.amount,data.method,data.reference):raise p.HTTPException(409,'Clave usada con otro abono')
            return {**view(db,record),'replayed':True}
        balance=Decimal(view(db,record)['balance'])
        if data.amount>balance:raise p.HTTPException(409,'El abono excede el saldo pendiente')
        payment=p.PayablePayment(empresa_id=user.empresa_id,payable_id=record.id,amount=data.amount,method=data.method,
            reference=data.reference,actor_id=user.id,request_key=key)
        db.add(payment)
        try:
            db.flush();db.add(p.Audit(empresa_id=user.empresa_id,branch_id=record.branch_id,actor_id=user.id,action='payable_payment',record_id=payment.id))
            result={**view(db,record),'replayed':False};db.commit();return result
        except IntegrityError:raise p.HTTPException(409,'Clave de abono duplicada; consulta la cuenta antes de reintentar')

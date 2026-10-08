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
    paid=sum((x.amount for x in payments if x.reversed_at is None),Decimal('0'))
    credits=sum((x.total for x in db.scalars(p.select(p.SupplierReturn).where(p.SupplierReturn.payable_id==record.id))),Decimal('0'))
    raw_balance=record.amount-paid-credits;balance=max(raw_balance,Decimal('0'))
    today=datetime.now(ZoneInfo('America/Mexico_City')).date()
    return {'id':record.id,'purchase_id':record.purchase_id,'supplier_id':record.supplier_id,
        'supplier':db.get(p.Supplier,record.supplier_id).name,'invoice':record.invoice,'due_date':record.due_date.isoformat(),
        'amount':str(record.amount),'paid':str(p.money(paid)),'balance':str(p.money(balance)),
        'credits':str(p.money(credits)),'supplier_credit':str(p.money(max(-raw_balance,Decimal('0')))),
        'status':'credit' if raw_balance<0 else 'paid' if not balance else 'overdue' if record.due_date<today else 'pending',
        'payments':[{'id':x.id,'amount':str(x.amount),'reference':x.reference,'method':x.method,
                     'actor_id':x.actor_id,'created_at':x.created_at.isoformat(),
                     'reversed_at':x.reversed_at.isoformat() if x.reversed_at else None,'reversed_by':x.reversed_by,'reversal_reason':x.reversal_reason} for x in payments]}


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


class ReverseIn(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    reason:str=Field(min_length=3,max_length=300)


def reverse_payment(payment_id,data,user):
    from . import main as p
    from sqlalchemy.orm import Session
    p.require(user,'payable_write')
    with Session(p.engine) as db:
        payment=db.scalar(p.select(p.PayablePayment).where(p.PayablePayment.id==payment_id,p.PayablePayment.empresa_id==user.empresa_id))
        if payment is None:raise p.HTTPException(404,'Abono no encontrado')
        record=db.get(p.Payable,payment.payable_id);p.branch_for(db,user,record.branch_id)
        db.scalar(p.select(p.Branch).where(p.Branch.id==record.branch_id).with_for_update())
        db.refresh(payment,with_for_update=True)
        if payment.reversed_at:
            if payment.reversal_reason!=data.reason:raise p.HTTPException(409,'Abono ya revertido con otro motivo')
            return {**view(db,record),'replayed':True}
        payment.reversed_at=datetime.now(p.timezone.utc);payment.reversed_by=user.id;payment.reversal_reason=data.reason
        db.add(p.Audit(empresa_id=user.empresa_id,branch_id=record.branch_id,actor_id=user.id,action='payable_payment_reversed',record_id=payment.id))
        db.flush();result={**view(db,record),'replayed':False};db.commit();return result

class SupplierReturnLine(BaseModel):
    product_id:int=Field(gt=0)
    quantity:int=Field(gt=0,le=100000)

class SupplierReturnIn(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    reason:str=Field(min_length=3,max_length=300)
    credit_reference:str=Field(min_length=3,max_length=100)
    items:list[SupplierReturnLine]=Field(min_length=1,max_length=100)


def return_view(record):
    from . import main as p
    return {'id':record.id,'purchase_id':record.purchase_id,'payable_id':record.payable_id,
            'reason':record.reason,'credit_reference':record.credit_reference,'total':str(record.total),
            'actor_id':record.actor_id,'created_at':record.created_at.isoformat(),'items':p.json.loads(record.payload)['items']}


def return_to_supplier(purchase_id,data,key,user):
    from . import main as p
    from sqlalchemy.orm import Session
    p.require(user,'purchase_write');p.require(user,'stock_write');p.require(user,'payable_write')
    ids=[x.product_id for x in data.items]
    if len(ids)!=len(set(ids)):raise p.HTTPException(422,'Productos duplicados')
    payload=p.json.dumps({'reason':data.reason,'credit_reference':data.credit_reference,
        'items':sorted([x.model_dump() for x in data.items],key=lambda x:x['product_id'])},sort_keys=True,separators=(',',':'))
    with Session(p.engine) as db:
        purchase=db.scalar(p.select(p.Purchase).where(p.Purchase.id==purchase_id,p.Purchase.empresa_id==user.empresa_id))
        if purchase is None:raise p.HTTPException(404,'Compra no encontrada')
        p.branch_for(db,user,purchase.branch_id)
        db.scalar(p.select(p.Branch).where(p.Branch.id==purchase.branch_id).with_for_update())
        db.refresh(purchase,with_for_update=True)
        old=db.scalar(p.select(p.SupplierReturn).where(p.SupplierReturn.empresa_id==user.empresa_id,p.SupplierReturn.request_key==key))
        if old:
            if old.purchase_id!=purchase_id or old.payload!=payload:raise p.HTTPException(409,'Clave usada con otra devolución')
            return {**return_view(old),'replayed':True}
        payable=db.scalar(p.select(p.Payable).where(p.Payable.purchase_id==purchase_id).with_for_update())
        if payable is None:raise p.HTTPException(409,'Registra primero la cuenta por pagar de la compra recibida completa')
        if purchase.status!='received':raise p.HTTPException(409,'Este flujo sólo admite compras recibidas completamente')
        prior={}
        for r in db.scalars(p.select(p.SupplierReturn).where(p.SupplierReturn.purchase_id==purchase_id)):
            for x in p.json.loads(r.payload)['items']:prior[x['product_id']]=prior.get(x['product_id'],0)+x['quantity']
        lines={x.product_id:x for x in purchase.items}
        stocks={x.product_id:x for x in db.scalars(p.select(p.Stock).where(p.Stock.branch_id==purchase.branch_id,p.Stock.product_id.in_(ids)).order_by(p.Stock.product_id).with_for_update())}
        total=Decimal('0')
        for x in data.items:
            line=lines.get(x.product_id);used=prior.get(x.product_id,0)
            if line is None or used+x.quantity>line.received:raise p.HTTPException(409,'La devolución excede la cantidad recibida disponible')
            stock=stocks.get(x.product_id)
            if stock is None or stock.quantity-p.reserved_quantity(db,purchase.branch_id,x.product_id)<x.quantity:raise p.HTTPException(409,'Inventario disponible insuficiente')
            net=p.money(line.unit_cost*line.quantity);original=net+p.money(net*line.tax_rate)
            # Cumulative allocation conserves the last cent over partial returns.
            total+=p.money(original*Decimal(used+x.quantity)/line.quantity)-p.money(original*Decimal(used)/line.quantity)
        if total<=0:raise p.HTTPException(422,'La devolución no genera crédito positivo')
        record=p.SupplierReturn(empresa_id=user.empresa_id,purchase_id=purchase_id,payable_id=payable.id,actor_id=user.id,
             reason=data.reason,credit_reference=data.credit_reference,total=p.money(total),payload=payload,request_key=key)
        db.add(record);db.flush()
        for x in data.items:
            stocks[x.product_id].quantity-=x.quantity
            db.add(p.StockMovement(empresa_id=user.empresa_id,branch_id=purchase.branch_id,product_id=x.product_id,
                change=-x.quantity,reason='supplier_return',reference_id=record.id,actor_id=user.id))
        db.add(p.Audit(empresa_id=user.empresa_id,branch_id=purchase.branch_id,actor_id=user.id,action='supplier_return',record_id=record.id))
        result={**return_view(record),'replayed':False};db.commit();return result


def list_supplier_returns(purchase_id,user):
    from . import main as p
    from sqlalchemy.orm import Session
    p.require_any(user,'purchase_read','report')
    with Session(p.engine) as db:
        purchase=db.scalar(p.select(p.Purchase).where(p.Purchase.id==purchase_id,p.Purchase.empresa_id==user.empresa_id))
        if purchase is None:raise p.HTTPException(404,'Compra no encontrada')
        p.branch_for(db,user,purchase.branch_id)
        return [return_view(r) for r in db.scalars(p.select(p.SupplierReturn).where(p.SupplierReturn.purchase_id==purchase_id).order_by(p.SupplierReturn.id))]

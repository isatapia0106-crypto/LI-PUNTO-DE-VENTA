"""Read-only controls. No provider calls or manual dismissal of discrepancies."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo


def bounds(start, end):
    from .main import HTTPException
    if end < start or (end-start).days > 365:
        raise HTTPException(422, 'Selecciona hasta 366 días en orden válido')
    tz = ZoneInfo('America/Mexico_City')
    return (datetime.combine(start, datetime.min.time(), tz).astimezone(timezone.utc).replace(tzinfo=None),
            datetime.combine(end+timedelta(days=1), datetime.min.time(), tz).astimezone(timezone.utc).replace(tzinfo=None))


def audit_page(branch_id, start, end, actor_id, action, before_id, user):
    from . import main as p
    from sqlalchemy.orm import Session
    lower, upper = bounds(start,end)
    p.require(user,'report')
    with Session(p.engine) as db:
        p.branch_for(db,user,branch_id)
        q = p.select(p.Audit).where(p.Audit.empresa_id==user.empresa_id, p.Audit.branch_id==branch_id,
                                   p.Audit.created_at>=lower,p.Audit.created_at<upper)
        if actor_id is not None:q=q.where(p.Audit.actor_id==actor_id)
        if action:q=q.where(p.Audit.action==action)
        if before_id is not None:q=q.where(p.Audit.id<before_id)
        rows=db.scalars(q.order_by(p.Audit.id.desc()).limit(101)).all()
        page=rows[:100]
        users={u.id:u.username for u in db.scalars(p.select(p.User).where(p.User.empresa_id==user.empresa_id,
                    p.User.id.in_([r.actor_id for r in page if r.actor_id is not None])))}
        return {'items':[{'id':r.id,'action':r.action,'record_id':r.record_id,'actor_id':r.actor_id,
                          'actor':users.get(r.actor_id,'Sistema o usuario histórico'), 'created_at':r.created_at.isoformat()} for r in page],
                'next_cursor':page[-1].id if len(rows)>100 else None,'timezone':'America/Mexico_City'}


def payment_page(branch_id,start,end,before_id,user):
    from . import main as p
    from sqlalchemy.orm import Session
    p.require(user,'report')
    lower,upper=bounds(start,end)
    with Session(p.engine) as db:
        p.branch_for(db,user,branch_id)
        q=p.select(p.PaymentIntent).where(p.PaymentIntent.empresa_id==user.empresa_id,
                p.PaymentIntent.branch_id==branch_id,p.PaymentIntent.created_at>=lower,p.PaymentIntent.created_at<upper)
        if before_id:q=q.where(p.PaymentIntent.id<before_id)
        intents=db.scalars(q.order_by(p.PaymentIntent.id.desc()).limit(101)).all()
        page=intents[:100];ids=[i.id for i in page]
        observations={i:[] for i in ids}
        for o in db.scalars(p.select(p.PaymentObservation).where(p.PaymentObservation.empresa_id==user.empresa_id,p.PaymentObservation.intent_id.in_(ids))):
            observations[o.intent_id].append(o)
        keys=['mp-sale-'+i for i in ids]
        sales={s.request_key:s for s in db.scalars(p.select(p.Sale).where(p.Sale.empresa_id==user.empresa_id,
                p.Sale.branch_id==branch_id,p.Sale.request_key.in_(keys)))}
        refunds={s.id:Decimal('0') for s in sales.values()};pending=set()
        for r in db.scalars(p.select(p.SaleReturn).where(p.SaleReturn.empresa_id==user.empresa_id,p.SaleReturn.sale_id.in_(list(refunds)))):
            if r.status=='completed':refunds[r.sale_id]+=r.total
            else:pending.add(r.sale_id)
        items=[]
        for i in page:
            obs=observations[i.id];sale=sales.get('mp-sale-'+i.id)
            local=sale.total-refunds[sale.id] if sale else Decimal('0')
            collected=sum((o.amount-o.refunded for o in obs if o.status in ('approved','refunded')),Decimal('0'))
            issues=[]
            primary=next((o for o in obs if o.payment_id==i.payment_id),None)
            if not obs or (sale and primary is None):issues.append('Sin observación verificada del pago principal' if sale else 'Sin pagos observados')
            if i.review_reason:issues.append('Incidencia de pago registrada')
            if sale and sale.id in pending:issues.append('Devolución pendiente de confirmación')
            if any(o.status=='charged_back' for o in obs):issues.append('Contracargo observado')
            if any(o.refunded<0 or o.refunded>o.amount for o in obs):issues.append('Importe de reembolso inconsistente')
            if sale and (primary is None or primary.amount!=sale.total or primary.status not in ('approved','refunded')):
                issues.append('Pago principal no coincide con el ticket')
            if sale and primary and primary.refunded!=refunds[sale.id]:issues.append('Reembolso principal diferente del registro local')
            if sale and sale.total!=i.amount:issues.append('Importe de cobro diferente del ticket')
            difference=collected-local
            if difference:issues.append('Diferencia entre pagos observados y tickets netos')
            state='review' if issues else ('matched' if sale else 'pending')
            items.append({'id':i.id,'created_at':i.created_at.isoformat(),'status':i.status,'state':state,
                'folio':sale.folio if sale else None,'sale_id':sale.id if sale else None,
                'local_net':str(p.money(local)),'observed_net':str(p.money(collected)), 'difference':str(p.money(difference)),
                'issues':issues,'last_observed_at':max((o.updated_at for o in obs),default=None).isoformat() if obs else None})
        return {'items':items,'next_cursor':page[-1].id if len(intents)>100 else None,
            'timezone':'America/Mexico_City','generated_at':datetime.now(timezone.utc).isoformat(),
            'scope':'Cobros creados en el periodo; valores acumulados actuales según observaciones verificadas guardadas. No confirma depósitos bancarios ni comisiones.'}

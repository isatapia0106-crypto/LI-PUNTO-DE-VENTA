import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, ForeignKey, String, Integer, Numeric, DateTime, select, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./pos.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)

class Base(DeclarativeBase):
    pass

class Branch(Base):
    __tablename__ = 'branches'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint('empresa_id', 'name'),)

class CashSession(Base):
    __tablename__ = 'cash_sessions'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'))
    opening: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    counted: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default='open')
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class CashMovement(Base):
    __tablename__ = 'cash_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer)
    branch_id: Mapped[int] = mapped_column(Integer)
    session_id: Mapped[int] = mapped_column(ForeignKey('cash_sessions.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    kind: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class StockMovement(Base):
    __tablename__ = 'stock_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer)
    branch_id: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    change: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(30))
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    sku: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(160))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    __table_args__ = (UniqueConstraint('empresa_id', 'sku'),)

class Stock(Base):
    __tablename__ = 'stock'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    branch_id: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint('product_id', 'branch_id'),)

class Sale(Base):
    __tablename__ = 'sales'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    branch_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payment_method: Mapped[str] = mapped_column(String(30))
    cash_session_id: Mapped[int] = mapped_column(ForeignKey('cash_sessions.id'))
    request_key: Mapped[str] = mapped_column(String(100))
    paid: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    items: Mapped[list['SaleItem']] = relationship(cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('empresa_id', 'request_key'),)

class SaleItem(Base):
    __tablename__ = 'sale_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey('sales.id'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))

class Audit(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer)
    branch_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(50))
    record_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Line(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=10000)

class SaleIn(BaseModel):
    branch_id: int = Field(gt=0)
    items: list[Line] = Field(min_length=1)
    payment_method: str
    paid: Decimal = Field(ge=0)

class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    price: Decimal = Field(gt=0)
    branch_id: int = Field(gt=0)
    stock: int = Field(ge=0)

class OpenCash(BaseModel):
    branch_id: int = Field(gt=0)
    opening: Decimal = Field(ge=0)

class CloseCash(BaseModel):
    counted: Decimal = Field(ge=0)

class WithdrawCash(BaseModel):
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=3, max_length=160)

class AdjustStock(BaseModel):
    branch_id: int = Field(gt=0)
    change: int = Field(ge=-100000, le=100000)
    reason: str = Field(min_length=3, max_length=100)

app = FastAPI(title='LI Punto de Venta · MVP')

# Demo identity only. Production must replace this with verified JWT and server-side RBAC.
def identity(x_demo_empresa: int = Header(default=1)) -> int:
    if os.getenv('APP_ENV') == 'production':
        raise HTTPException(503, 'Autenticación productiva pendiente')
    if x_demo_empresa < 1:
        raise HTTPException(400, 'Empresa inválida')
    return x_demo_empresa

from fastapi import Depends

def money(v):
    return Decimal(v).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def branch_for(db: Session, empresa: int, branch_id: int):
    branch = db.scalar(select(Branch).where(Branch.id == branch_id, Branch.empresa_id == empresa))
    if branch is None:
        raise HTTPException(404, 'Sucursal no encontrada para esta empresa')
    return branch

@app.get('/api/branches')
def branches(empresa: int = Depends(identity)):
    with Session(engine) as db:
        return [{'id': b.id, 'name': b.name} for b in db.scalars(select(Branch).where(Branch.empresa_id == empresa).order_by(Branch.id))]

@app.post('/api/cash/open', status_code=201)
def open_cash(data: OpenCash, empresa: int = Depends(identity)):
    with Session(engine) as db:
        # Lock the branch before checking open sessions; PostgreSQL serializes openings.
        branch = db.scalar(select(Branch).where(Branch.id == data.branch_id, Branch.empresa_id == empresa).with_for_update())
        if branch is None:
            raise HTTPException(404, 'Sucursal no encontrada para esta empresa')
        current = db.scalar(select(CashSession).where(CashSession.empresa_id == empresa, CashSession.branch_id == data.branch_id, CashSession.status == 'open').with_for_update())
        if current:
            raise HTTPException(409, 'Ya existe una caja abierta en esta sucursal')
        session = CashSession(empresa_id=empresa, branch_id=data.branch_id, opening=money(data.opening))
        db.add(session)
        db.flush()
        db.add(Audit(empresa_id=empresa, branch_id=data.branch_id, action='cash_opened', record_id=session.id))
        result = {'id': session.id, 'opening': str(session.opening)}
        db.commit()
        return result

@app.get('/api/cash/current')
def current_cash(branch_id: int, empresa: int = Depends(identity)):
    with Session(engine) as db:
        branch_for(db, empresa, branch_id)
        session = db.scalar(select(CashSession).where(CashSession.empresa_id == empresa, CashSession.branch_id == branch_id, CashSession.status == 'open'))
        if not session:
            return {'open': False}
        cash_sales = db.scalars(select(Sale).where(Sale.cash_session_id == session.id, Sale.payment_method == 'cash')).all()
        withdrawals = db.scalars(select(CashMovement).where(CashMovement.session_id == session.id, CashMovement.kind == 'withdrawal')).all()
        withdrawn = sum((x.amount for x in withdrawals), Decimal('0'))
        expected = money(session.opening + sum((s.total for s in cash_sales), Decimal('0')) - withdrawn)
        return {'open': True, 'id': session.id, 'opening': str(session.opening), 'expected': str(expected), 'cash_sales': len(cash_sales), 'withdrawn': str(money(withdrawn))}

@app.post('/api/cash/{session_id}/withdraw', status_code=201)
def withdraw_cash(session_id: int, data: WithdrawCash, empresa: int = Depends(identity)):
    with Session(engine) as db:
        session = db.scalar(select(CashSession).where(CashSession.id == session_id, CashSession.empresa_id == empresa, CashSession.status == 'open').with_for_update())
        if session is None:
            raise HTTPException(404, 'Caja abierta no encontrada')
        cash_sales = db.scalars(select(Sale).where(Sale.cash_session_id == session.id, Sale.payment_method == 'cash')).all()
        withdrawals = db.scalars(select(CashMovement).where(CashMovement.session_id == session.id, CashMovement.kind == 'withdrawal')).all()
        available = money(session.opening + sum((s.total for s in cash_sales), Decimal('0')) - sum((x.amount for x in withdrawals), Decimal('0')))
        amount = money(data.amount)
        if amount <= 0 or amount > available:
            raise HTTPException(409, 'Efectivo insuficiente en caja')
        movement = CashMovement(empresa_id=empresa, branch_id=session.branch_id, session_id=session.id, amount=amount, kind='withdrawal', reason=data.reason)
        db.add(movement)
        db.flush()
        db.add(Audit(empresa_id=empresa, branch_id=session.branch_id, action='cash_withdrawal', record_id=movement.id))
        result = {'id': movement.id, 'amount': str(amount), 'expected_after': str(money(available - amount))}
        db.commit()
        return result

@app.post('/api/cash/{session_id}/close')
def close_cash(session_id: int, data: CloseCash, empresa: int = Depends(identity)):
    with Session(engine) as db:
        session = db.scalar(select(CashSession).where(CashSession.id == session_id, CashSession.empresa_id == empresa, CashSession.status == 'open').with_for_update())
        if not session:
            raise HTTPException(404, 'Caja abierta no encontrada')
        cash_sales = db.scalars(select(Sale).where(Sale.cash_session_id == session.id, Sale.payment_method == 'cash')).all()
        withdrawals = db.scalars(select(CashMovement).where(CashMovement.session_id == session.id, CashMovement.kind == 'withdrawal')).all()
        expected = money(session.opening + sum((s.total for s in cash_sales), Decimal('0')) - sum((x.amount for x in withdrawals), Decimal('0')))
        session.counted = money(data.counted)
        session.closed_at = datetime.now(timezone.utc)
        session.status = 'closed'
        db.add(Audit(empresa_id=empresa, branch_id=session.branch_id, action='cash_closed', record_id=session.id))
        result = {'id': session.id, 'expected': str(expected), 'counted': str(session.counted), 'difference': str(money(session.counted - expected))}
        db.commit()
        return result

@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': 'demo' if os.getenv('APP_ENV') != 'production' else 'locked'}

@app.post('/api/products', status_code=201)
def create_product(data: ProductIn, empresa: int = Depends(identity)):
    with Session(engine) as db:
        branch_for(db, empresa, data.branch_id)
        product = Product(empresa_id=empresa, sku=data.sku, name=data.name, price=money(data.price))
        db.add(product)
        try:
            db.flush()
            db.add(Stock(product_id=product.id, branch_id=data.branch_id, quantity=data.stock))
            db.add(StockMovement(empresa_id=empresa, branch_id=data.branch_id, product_id=product.id, change=data.stock, reason='initial'))
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(409, 'SKU duplicado o datos inválidos')
        return {'id': product.id, 'sku': product.sku}

@app.get('/api/products')
def products(branch_id: int, empresa: int = Depends(identity)):
    with Session(engine) as db:
        branch_for(db, empresa, branch_id)
        rows = db.execute(select(Product, Stock).join(Stock).where(Product.empresa_id == empresa, Stock.branch_id == branch_id).order_by(Product.name)).all()
        return [{'id': p.id, 'sku': p.sku, 'name': p.name, 'price': str(p.price), 'stock': s.quantity} for p, s in rows]

@app.post('/api/products/{product_id}/stock')
def adjust_stock(product_id: int, data: AdjustStock, empresa: int = Depends(identity)):
    if data.change == 0:
        raise HTTPException(422, 'El movimiento debe cambiar existencias')
    with Session(engine) as db:
        branch_for(db, empresa, data.branch_id)
        row = db.execute(select(Product, Stock).join(Stock).where(Product.id == product_id, Product.empresa_id == empresa, Stock.branch_id == data.branch_id).with_for_update()).first()
        if not row:
            raise HTTPException(404, 'Producto sin inventario en sucursal')
        product, stock = row
        if stock.quantity + data.change < 0:
            raise HTTPException(409, 'Inventario insuficiente')
        stock.quantity += data.change
        db.add(StockMovement(empresa_id=empresa, branch_id=data.branch_id, product_id=product.id, change=data.change, reason=data.reason))
        db.add(Audit(empresa_id=empresa, branch_id=data.branch_id, action='stock_adjusted', record_id=product.id))
        result = {'product_id': product.id, 'stock': stock.quantity}
        db.commit()
        return result

@app.get('/api/stock/movements')
def movements(branch_id: int, empresa: int = Depends(identity)):
    with Session(engine) as db:
        branch_for(db, empresa, branch_id)
        rows = db.scalars(select(StockMovement).where(StockMovement.empresa_id == empresa, StockMovement.branch_id == branch_id).order_by(StockMovement.id.desc()).limit(100)).all()
        return [{'id': x.id, 'product_id': x.product_id, 'change': x.change, 'reason': x.reason, 'reference_id': x.reference_id} for x in rows]

@app.post('/api/sales', status_code=201)
def sell(data: SaleIn, idempotency_key: str = Header(min_length=8, max_length=100), empresa: int = Depends(identity)):
    if data.payment_method not in ('cash', 'card', 'transfer'):
        raise HTTPException(422, 'Forma de pago inválida')
    ids = [i.product_id for i in data.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, 'Productos duplicados en carrito')
    with Session(engine) as db:
        try:
            branch_for(db, empresa, data.branch_id)
            existing = db.scalar(select(Sale).where(Sale.empresa_id == empresa, Sale.request_key == idempotency_key))
            if existing:
                previous = sorted((x.product_id, x.quantity) for x in existing.items)
                incoming = sorted((x.product_id, x.quantity) for x in data.items)
                if (existing.branch_id != data.branch_id or existing.payment_method != data.payment_method
                        or existing.paid != money(data.paid) or previous != incoming):
                    raise HTTPException(409, 'Clave de venta ya utilizada para otra operación')
                return {'id': existing.id, 'subtotal': str(existing.subtotal), 'tax': str(existing.tax), 'total': str(existing.total), 'change': str(money(existing.paid - existing.total)), 'replayed': True}
            cash = db.scalar(select(CashSession).where(CashSession.empresa_id == empresa, CashSession.branch_id == data.branch_id, CashSession.status == 'open').with_for_update())
            if not cash:
                raise HTTPException(409, 'Abre caja antes de vender')
            # PostgreSQL row locks serialize stock decrements for concurrent checkouts.
            rows = db.execute(select(Product, Stock).join(Stock).where(Product.id.in_(ids), Product.empresa_id == empresa, Stock.branch_id == data.branch_id).order_by(Product.id).with_for_update()).all()
            mapped = {p.id: (p, s) for p, s in rows}
            if len(mapped) != len(ids):
                raise HTTPException(404, 'Producto fuera de esta empresa o sucursal')
            subtotal = Decimal('0')
            sale_lines = []
            for item in data.items:
                p, stock = mapped[item.product_id]
                if stock.quantity < item.quantity:
                    raise HTTPException(409, f'Sin existencias suficientes: {p.name}')
                stock.quantity -= item.quantity
                subtotal += p.price * item.quantity
                sale_lines.append(SaleItem(product_id=p.id, name=p.name, quantity=item.quantity, unit_price=p.price))
            subtotal = money(subtotal)
            # Prices in this MVP are before tax; 16% is a configurable assumption for demo.
            tax = money(subtotal * Decimal('.16'))
            total = subtotal + tax
            if data.payment_method == 'cash' and money(data.paid) < total:
                raise HTTPException(422, 'Pago insuficiente')
            if data.payment_method != 'cash' and money(data.paid) != total:
                raise HTTPException(422, 'El pago debe coincidir con el total')
            sale = Sale(empresa_id=empresa, branch_id=data.branch_id, cash_session_id=cash.id, request_key=idempotency_key, subtotal=subtotal, tax=tax, total=total, payment_method=data.payment_method, paid=money(data.paid), items=sale_lines)
            db.add(sale)
            db.flush()
            for item in data.items:
                db.add(StockMovement(empresa_id=empresa, branch_id=data.branch_id, product_id=item.product_id, change=-item.quantity, reason='sale', reference_id=sale.id))
            db.add(Audit(empresa_id=empresa, branch_id=data.branch_id, action='sale_created', record_id=sale.id))
            result = {'id': sale.id, 'subtotal': str(subtotal), 'tax': str(tax), 'total': str(total), 'change': str(money(data.paid - total)), 'items': [{'name': x.name, 'quantity': x.quantity, 'unit_price': str(x.unit_price)} for x in sale_lines]}
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise

@app.get('/api/sales')
def sales(branch_id: int, empresa: int = Depends(identity)):
    with Session(engine) as db:
        branch_for(db, empresa, branch_id)
        rows = db.scalars(select(Sale).where(Sale.empresa_id == empresa, Sale.branch_id == branch_id).order_by(Sale.id.desc()).limit(30)).all()
        return [{'id': s.id, 'total': str(s.total), 'created_at': s.created_at.isoformat(), 'payment_method': s.payment_method} for s in rows]

@app.get('/api/reports/summary')
def summary(branch_id: int, empresa: int = Depends(identity)):
    with Session(engine) as db:
        branch_for(db, empresa, branch_id)
        rows = db.scalars(select(Sale).where(Sale.empresa_id == empresa, Sale.branch_id == branch_id)).all()
        by_method = {method: str(money(sum((s.total for s in rows if s.payment_method == method), Decimal('0')))) for method in ('cash', 'card', 'transfer')}
        return {'branch_id': branch_id, 'sales_count': len(rows), 'total': str(money(sum((s.total for s in rows), Decimal('0')))), 'by_method': by_method}

Base.metadata.create_all(engine)  # MVP bootstrap; migrate with Alembic before production.
if os.getenv('APP_ENV', 'demo') != 'production':
    with Session(engine) as db:
        if not db.scalar(select(Branch.id).where(Branch.empresa_id == 1).limit(1)):
            db.add_all(Branch(empresa_id=1, name=name) for name in ('Zamora', 'Zacapu', 'Uruapan', '20 de Noviembre', 'Maravatío', 'CDMX'))
            db.commit()
frontend = Path(__file__).resolve().parents[2] / 'frontend' / 'public'
app.mount('/assets', StaticFiles(directory=frontend), name='assets')
@app.get('/')
def home():
    return FileResponse(frontend / 'index.html')

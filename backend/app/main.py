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
    paid: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    items: Mapped[list['SaleItem']] = relationship(cascade='all, delete-orphan')

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

@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': 'demo' if os.getenv('APP_ENV') != 'production' else 'locked'}

@app.post('/api/products', status_code=201)
def create_product(data: ProductIn, empresa: int = Depends(identity)):
    with Session(engine) as db:
        product = Product(empresa_id=empresa, sku=data.sku, name=data.name, price=money(data.price))
        db.add(product)
        try:
            db.flush()
            db.add(Stock(product_id=product.id, branch_id=data.branch_id, quantity=data.stock))
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(409, 'SKU duplicado o datos inválidos')
        return {'id': product.id, 'sku': product.sku}

@app.get('/api/products')
def products(branch_id: int, empresa: int = Depends(identity)):
    with Session(engine) as db:
        rows = db.execute(select(Product, Stock).join(Stock).where(Product.empresa_id == empresa, Stock.branch_id == branch_id).order_by(Product.name)).all()
        return [{'id': p.id, 'sku': p.sku, 'name': p.name, 'price': str(p.price), 'stock': s.quantity} for p, s in rows]

@app.post('/api/sales', status_code=201)
def sell(data: SaleIn, empresa: int = Depends(identity)):
    if data.payment_method not in ('cash', 'card', 'transfer'):
        raise HTTPException(422, 'Forma de pago inválida')
    ids = [i.product_id for i in data.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, 'Productos duplicados en carrito')
    with Session(engine) as db:
        try:
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
            sale = Sale(empresa_id=empresa, branch_id=data.branch_id, subtotal=subtotal, tax=tax, total=total, payment_method=data.payment_method, paid=money(data.paid), items=sale_lines)
            db.add(sale)
            db.flush()
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
        rows = db.scalars(select(Sale).where(Sale.empresa_id == empresa, Sale.branch_id == branch_id).order_by(Sale.id.desc()).limit(30)).all()
        return [{'id': s.id, 'total': str(s.total), 'created_at': s.created_at.isoformat(), 'payment_method': s.payment_method} for s in rows]

Base.metadata.create_all(engine)  # MVP bootstrap; migrate with Alembic before production.
frontend = Path(__file__).resolve().parents[2] / 'frontend' / 'public'
app.mount('/assets', StaticFiles(directory=frontend), name='assets')
@app.get('/')
def home():
    return FileResponse(frontend / 'index.html')

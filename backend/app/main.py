import os
import secrets
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, ForeignKey, String, Integer, Numeric, DateTime, select, UniqueConstraint, inspect
from sqlalchemy.exc import IntegrityError
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

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(default=True)

class UserBranch(Base):
    __tablename__ = 'user_branches'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'), primary_key=True)

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

class StockTransfer(Base):
    __tablename__ = 'stock_transfers'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    source_branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'))
    target_branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    quantity: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('empresa_id', 'request_key'),)

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
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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

class TransferStock(BaseModel):
    source_branch_id: int = Field(gt=0)
    target_branch_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100000)

class LoginIn(BaseModel):
    username: str
    password: str

class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=200)
    role: str
    branch_ids: list[int] = Field(min_length=1)

app = FastAPI(title='LI Punto de Venta · MVP')
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
JWT_SECRET = os.getenv('JWT_SECRET')
if not JWT_SECRET:
    if os.getenv('APP_ENV') == 'production':
        raise RuntimeError('JWT_SECRET es obligatorio en producción')
    JWT_SECRET = secrets.token_urlsafe(48)  # Transient local key; restarts invalidate sessions.

ROLE_ACTIONS = {
    'admin_general': {'sale', 'catalog_write', 'stock_write', 'cash_open', 'cash_close', 'cash_withdraw', 'report', 'users_write'},
    'admin_sucursal': {'sale', 'catalog_write', 'stock_write', 'cash_open', 'cash_close', 'cash_withdraw', 'report'},
    'cajero': {'sale', 'cash_open', 'cash_close'},
    'almacenista': {'stock_write'},
    'supervisor_inventarios': {'stock_write', 'report'},
    'contabilidad': {'report'},
    'repartidor': set(),
    'auditoria': {'report'},
}

def require(user: User, action: str):
    if action not in ROLE_ACTIONS.get(user.role, set()):
        raise HTTPException(403, 'Permiso insuficiente')

def require_any(user: User, *actions: str):
    if not any(action in ROLE_ACTIONS.get(user.role, set()) for action in actions):
        raise HTTPException(403, 'Permiso insuficiente')

def identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    if credentials is None:
        raise HTTPException(401, 'Se requiere iniciar sesión', headers={'WWW-Authenticate': 'Bearer'})
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=['HS256'], options={'require': ['sub', 'exp']})
        user_id = int(payload['sub'])
    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(401, 'Sesión inválida', headers={'WWW-Authenticate': 'Bearer'})
    with Session(engine) as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise HTTPException(401, 'Sesión inválida')
        return user

def token_for(user: User) -> str:
    return jwt.encode({'sub': str(user.id), 'exp': datetime.now(timezone.utc) + timedelta(hours=8)}, JWT_SECRET, algorithm='HS256')

@app.post('/api/auth/login')
def login(data: LoginIn):
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == data.username))
        if not user or not user.active or not password_hash.verify(data.password, user.password_hash):
            raise HTTPException(401, 'Credenciales inválidas')
        return {'access_token': token_for(user), 'token_type': 'bearer', 'role': user.role}

@app.get('/api/auth/me')
def me(user: User = Depends(identity)):
    return {'id': user.id, 'username': user.username, 'role': user.role}

@app.post('/api/users', status_code=201)
def create_user(data: UserIn, user: User = Depends(identity)):
    require(user, 'users_write')
    if data.role not in ROLE_ACTIONS:
        raise HTTPException(422, 'Rol inválido')
    ids = set(data.branch_ids)
    with Session(engine) as db:
        branches = db.scalars(select(Branch).where(Branch.id.in_(ids), Branch.empresa_id == user.empresa_id)).all()
        if len(branches) != len(ids) or len(ids) != len(data.branch_ids):
            raise HTTPException(422, 'Sucursales inválidas o duplicadas')
        created = User(empresa_id=user.empresa_id, username=data.username, password_hash=password_hash.hash(data.password), role=data.role)
        db.add(created)
        try:
            db.flush()
            db.add_all(UserBranch(user_id=created.id, branch_id=branch_id) for branch_id in ids)
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(409, 'Usuario duplicado')
        return {'id': created.id, 'username': created.username, 'role': created.role}

def money(v):
    return Decimal(v).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def branch_for(db: Session, user: User, branch_id: int):
    branch = db.scalar(select(Branch).where(Branch.id == branch_id, Branch.empresa_id == user.empresa_id))
    if branch is None:
        raise HTTPException(404, 'Sucursal no encontrada para esta empresa')
    if user.role != 'admin_general' and not db.scalar(select(UserBranch).where(UserBranch.user_id == user.id, UserBranch.branch_id == branch_id)):
        raise HTTPException(403, 'Sucursal no autorizada')
    return branch

@app.get('/api/branches')
def branches(user: User = Depends(identity)):
    empresa = user.empresa_id
    with Session(engine) as db:
        return [{'id': b.id, 'name': b.name} for b in db.scalars(select(Branch).where(Branch.empresa_id == empresa).order_by(Branch.id)) if user.role == 'admin_general' or db.scalar(select(UserBranch).where(UserBranch.user_id == user.id, UserBranch.branch_id == b.id))]

@app.post('/api/cash/open', status_code=201)
def open_cash(data: OpenCash, user: User = Depends(identity)):
    require(user, 'cash_open')
    empresa = user.empresa_id
    with Session(engine) as db:
        # Lock the branch before checking open sessions; PostgreSQL serializes openings.
        branch = db.scalar(select(Branch).where(Branch.id == data.branch_id, Branch.empresa_id == empresa).with_for_update())
        if branch is None:
            raise HTTPException(404, 'Sucursal no encontrada para esta empresa')
        branch_for(db, user, data.branch_id)
        current = db.scalar(select(CashSession).where(CashSession.empresa_id == empresa, CashSession.branch_id == data.branch_id, CashSession.status == 'open').with_for_update())
        if current:
            raise HTTPException(409, 'Ya existe una caja abierta en esta sucursal')
        session = CashSession(empresa_id=empresa, branch_id=data.branch_id, opening=money(data.opening))
        db.add(session)
        db.flush()
        db.add(Audit(empresa_id=empresa, branch_id=data.branch_id, action='cash_opened', record_id=session.id, actor_id=user.id))
        result = {'id': session.id, 'opening': str(session.opening)}
        db.commit()
        return result

@app.get('/api/cash/current')
def current_cash(branch_id: int, user: User = Depends(identity)):
    require_any(user, 'cash_open', 'report')
    empresa = user.empresa_id
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        session = db.scalar(select(CashSession).where(CashSession.empresa_id == empresa, CashSession.branch_id == branch_id, CashSession.status == 'open'))
        if not session:
            return {'open': False}
        cash_sales = db.scalars(select(Sale).where(Sale.cash_session_id == session.id, Sale.payment_method == 'cash')).all()
        withdrawals = db.scalars(select(CashMovement).where(CashMovement.session_id == session.id, CashMovement.kind == 'withdrawal')).all()
        withdrawn = sum((x.amount for x in withdrawals), Decimal('0'))
        expected = money(session.opening + sum((s.total for s in cash_sales), Decimal('0')) - withdrawn)
        return {'open': True, 'id': session.id, 'opening': str(session.opening), 'expected': str(expected), 'cash_sales': len(cash_sales), 'withdrawn': str(money(withdrawn))}

@app.post('/api/cash/{session_id}/withdraw', status_code=201)
def withdraw_cash(session_id: int, data: WithdrawCash, user: User = Depends(identity)):
    require(user, 'cash_withdraw')
    empresa = user.empresa_id
    with Session(engine) as db:
        session = db.scalar(select(CashSession).where(CashSession.id == session_id, CashSession.empresa_id == empresa, CashSession.status == 'open').with_for_update())
        if session is None:
            raise HTTPException(404, 'Caja abierta no encontrada')
        branch_for(db, user, session.branch_id)
        cash_sales = db.scalars(select(Sale).where(Sale.cash_session_id == session.id, Sale.payment_method == 'cash')).all()
        withdrawals = db.scalars(select(CashMovement).where(CashMovement.session_id == session.id, CashMovement.kind == 'withdrawal')).all()
        available = money(session.opening + sum((s.total for s in cash_sales), Decimal('0')) - sum((x.amount for x in withdrawals), Decimal('0')))
        amount = money(data.amount)
        if amount <= 0 or amount > available:
            raise HTTPException(409, 'Efectivo insuficiente en caja')
        movement = CashMovement(empresa_id=empresa, branch_id=session.branch_id, session_id=session.id, amount=amount, kind='withdrawal', reason=data.reason)
        db.add(movement)
        db.flush()
        db.add(Audit(empresa_id=empresa, branch_id=session.branch_id, action='cash_withdrawal', record_id=movement.id, actor_id=user.id))
        result = {'id': movement.id, 'amount': str(amount), 'expected_after': str(money(available - amount))}
        db.commit()
        return result

@app.post('/api/cash/{session_id}/close')
def close_cash(session_id: int, data: CloseCash, user: User = Depends(identity)):
    require(user, 'cash_close')
    empresa = user.empresa_id
    with Session(engine) as db:
        session = db.scalar(select(CashSession).where(CashSession.id == session_id, CashSession.empresa_id == empresa, CashSession.status == 'open').with_for_update())
        if not session:
            raise HTTPException(404, 'Caja abierta no encontrada')
        branch_for(db, user, session.branch_id)
        cash_sales = db.scalars(select(Sale).where(Sale.cash_session_id == session.id, Sale.payment_method == 'cash')).all()
        withdrawals = db.scalars(select(CashMovement).where(CashMovement.session_id == session.id, CashMovement.kind == 'withdrawal')).all()
        expected = money(session.opening + sum((s.total for s in cash_sales), Decimal('0')) - sum((x.amount for x in withdrawals), Decimal('0')))
        session.counted = money(data.counted)
        session.closed_at = datetime.now(timezone.utc)
        session.status = 'closed'
        db.add(Audit(empresa_id=empresa, branch_id=session.branch_id, action='cash_closed', record_id=session.id, actor_id=user.id))
        result = {'id': session.id, 'expected': str(expected), 'counted': str(session.counted), 'difference': str(money(session.counted - expected))}
        db.commit()
        return result

@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': os.getenv('APP_ENV', 'demo')}

@app.post('/api/products', status_code=201)
def create_product(data: ProductIn, user: User = Depends(identity)):
    require(user, 'catalog_write')
    empresa = user.empresa_id
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
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
def products(branch_id: int, user: User = Depends(identity)):
    empresa = user.empresa_id
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        rows = db.execute(select(Product, Stock).join(Stock).where(Product.empresa_id == empresa, Stock.branch_id == branch_id).order_by(Product.name)).all()
        return [{'id': p.id, 'sku': p.sku, 'name': p.name, 'price': str(p.price), 'stock': s.quantity} for p, s in rows]

@app.post('/api/products/{product_id}/stock')
def adjust_stock(product_id: int, data: AdjustStock, user: User = Depends(identity)):
    require(user, 'stock_write')
    empresa = user.empresa_id
    if data.change == 0:
        raise HTTPException(422, 'El movimiento debe cambiar existencias')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        row = db.execute(select(Product, Stock).join(Stock).where(Product.id == product_id, Product.empresa_id == empresa, Stock.branch_id == data.branch_id).with_for_update()).first()
        if not row:
            raise HTTPException(404, 'Producto sin inventario en sucursal')
        product, stock = row
        if stock.quantity + data.change < 0:
            raise HTTPException(409, 'Inventario insuficiente')
        stock.quantity += data.change
        db.add(StockMovement(empresa_id=empresa, branch_id=data.branch_id, product_id=product.id, change=data.change, reason=data.reason))
        db.add(Audit(empresa_id=empresa, branch_id=data.branch_id, action='stock_adjusted', record_id=product.id, actor_id=user.id))
        result = {'product_id': product.id, 'stock': stock.quantity}
        db.commit()
        return result

@app.get('/api/stock/movements')
def movements(branch_id: int, user: User = Depends(identity)):
    require(user, 'stock_write')
    empresa = user.empresa_id
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        rows = db.scalars(select(StockMovement).where(StockMovement.empresa_id == empresa, StockMovement.branch_id == branch_id).order_by(StockMovement.id.desc()).limit(100)).all()
        return [{'id': x.id, 'product_id': x.product_id, 'change': x.change, 'reason': x.reason, 'reference_id': x.reference_id} for x in rows]

@app.post('/api/stock/transfers', status_code=201)
def transfer_stock(data: TransferStock, idempotency_key: str = Header(min_length=8, max_length=100), user: User = Depends(identity)):
    require(user, 'stock_write')
    if data.source_branch_id == data.target_branch_id:
        raise HTTPException(422, 'Selecciona dos sucursales distintas')
    with Session(engine) as db:
        try:
            branch_for(db, user, data.source_branch_id)
            branch_for(db, user, data.target_branch_id)
            # Consistent lock order serializes opposite-direction transfers in PostgreSQL.
            db.scalars(select(Branch).where(Branch.id.in_((data.source_branch_id, data.target_branch_id)))
                       .order_by(Branch.id).with_for_update()).all()
            existing = db.scalar(select(StockTransfer).where(
                StockTransfer.empresa_id == user.empresa_id, StockTransfer.request_key == idempotency_key))
            if existing:
                if (existing.source_branch_id, existing.target_branch_id, existing.product_id, existing.quantity) != (
                    data.source_branch_id, data.target_branch_id, data.product_id, data.quantity):
                    raise HTTPException(409, 'Clave de traspaso ya utilizada para otra operación')
                return {'id': existing.id, 'source_branch_id': existing.source_branch_id,
                        'target_branch_id': existing.target_branch_id, 'product_id': existing.product_id,
                        'quantity': existing.quantity, 'replayed': True}
            product = db.scalar(select(Product).where(Product.id == data.product_id, Product.empresa_id == user.empresa_id))
            if product is None:
                raise HTTPException(404, 'Producto no encontrado para esta empresa')
            stocks = db.scalars(select(Stock).where(Stock.product_id == product.id,
                Stock.branch_id.in_((data.source_branch_id, data.target_branch_id)))
                .order_by(Stock.branch_id).with_for_update()).all()
            by_branch = {stock.branch_id: stock for stock in stocks}
            source = by_branch.get(data.source_branch_id)
            if source is None or source.quantity < data.quantity:
                raise HTTPException(409, 'Existencias insuficientes en sucursal origen')
            target = by_branch.get(data.target_branch_id)
            if target is None:
                target = Stock(product_id=product.id, branch_id=data.target_branch_id, quantity=0)
                db.add(target)
            source.quantity -= data.quantity
            target.quantity += data.quantity
            transfer = StockTransfer(empresa_id=user.empresa_id, source_branch_id=data.source_branch_id,
                target_branch_id=data.target_branch_id, product_id=product.id, quantity=data.quantity,
                request_key=idempotency_key, actor_id=user.id)
            db.add(transfer)
            db.flush()
            db.add_all([
                StockMovement(empresa_id=user.empresa_id, branch_id=data.source_branch_id,
                    product_id=product.id, change=-data.quantity, reason='transfer_out', reference_id=transfer.id),
                StockMovement(empresa_id=user.empresa_id, branch_id=data.target_branch_id,
                    product_id=product.id, change=data.quantity, reason='transfer_in', reference_id=transfer.id),
                Audit(empresa_id=user.empresa_id, branch_id=data.source_branch_id,
                    action='stock_transferred', record_id=transfer.id, actor_id=user.id),
            ])
            result = {'id': transfer.id, 'source_branch_id': data.source_branch_id,
                      'target_branch_id': data.target_branch_id, 'product_id': product.id,
                      'quantity': data.quantity, 'replayed': False}
            db.commit()
            return result
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, 'Traspaso duplicado o inventario modificado simultáneamente')
        except Exception:
            db.rollback()
            raise

@app.post('/api/sales', status_code=201)
def sell(data: SaleIn, idempotency_key: str = Header(min_length=8, max_length=100), user: User = Depends(identity)):
    require(user, 'sale')
    empresa = user.empresa_id
    if data.payment_method not in ('cash', 'card', 'transfer'):
        raise HTTPException(422, 'Forma de pago inválida')
    ids = [i.product_id for i in data.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, 'Productos duplicados en carrito')
    with Session(engine) as db:
        try:
            branch_for(db, user, data.branch_id)
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
            db.add(Audit(empresa_id=empresa, branch_id=data.branch_id, action='sale_created', record_id=sale.id, actor_id=user.id))
            result = {'id': sale.id, 'subtotal': str(subtotal), 'tax': str(tax), 'total': str(total), 'change': str(money(data.paid - total)), 'items': [{'name': x.name, 'quantity': x.quantity, 'unit_price': str(x.unit_price)} for x in sale_lines]}
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise

@app.get('/api/sales')
def sales(branch_id: int, user: User = Depends(identity)):
    require_any(user, 'sale', 'report')
    empresa = user.empresa_id
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        rows = db.scalars(select(Sale).where(Sale.empresa_id == empresa, Sale.branch_id == branch_id).order_by(Sale.id.desc()).limit(30)).all()
        return [{'id': s.id, 'total': str(s.total), 'created_at': s.created_at.isoformat(), 'payment_method': s.payment_method} for s in rows]

@app.get('/api/sales/{sale_id}')
def sale_detail(sale_id: int, user: User = Depends(identity)):
    require_any(user, 'sale', 'report')
    with Session(engine) as db:
        sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.empresa_id == user.empresa_id))
        if sale is None:
            raise HTTPException(404, 'Venta no encontrada')
        branch = branch_for(db, user, sale.branch_id)
        return {
            'id': sale.id, 'branch_id': branch.id, 'branch_name': branch.name,
            'created_at': sale.created_at.isoformat(), 'payment_method': sale.payment_method,
            'subtotal': str(sale.subtotal), 'tax': str(sale.tax), 'total': str(sale.total),
            'paid': str(sale.paid), 'change': str(money(sale.paid - sale.total)),
            'items': [
                {'product_id': item.product_id, 'name': item.name, 'quantity': item.quantity,
                 'unit_price': str(item.unit_price), 'line_total': str(money(item.unit_price * item.quantity))}
                for item in sale.items
            ],
        }

@app.get('/api/reports/summary')
def summary(branch_id: int, user: User = Depends(identity)):
    require(user, 'report')
    empresa = user.empresa_id
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        rows = db.scalars(select(Sale).where(Sale.empresa_id == empresa, Sale.branch_id == branch_id)).all()
        by_method = {method: str(money(sum((s.total for s in rows if s.payment_method == method), Decimal('0')))) for method in ('cash', 'card', 'transfer')}
        return {'branch_id': branch_id, 'sales_count': len(rows), 'total': str(money(sum((s.total for s in rows), Decimal('0')))), 'by_method': by_method}

if os.getenv('APP_ENV', 'demo') != 'production':
    if 'audit_logs' in inspect(engine).get_table_names() and 'actor_id' not in {c['name'] for c in inspect(engine).get_columns('audit_logs')}:
        raise RuntimeError('Base demo anterior: ejecuta python scripts/upgrade_demo_sqlite.py pos.db')
    Base.metadata.create_all(engine)  # Only for a fresh local demo DB.
    with Session(engine) as db:
        if not db.scalar(select(Branch.id).where(Branch.empresa_id == 1).limit(1)):
            db.add_all(Branch(empresa_id=1, name=name) for name in ('Zamora', 'Zacapu', 'Uruapan', '20 de Noviembre', 'Maravatío', 'CDMX'))
            db.commit()
frontend = Path(__file__).resolve().parents[2] / 'frontend' / 'public'
app.mount('/assets', StaticFiles(directory=frontend), name='assets')
@app.get('/')
def home():
    return FileResponse(frontend / 'index.html')

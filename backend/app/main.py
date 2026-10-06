import os
import json
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
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import create_engine, ForeignKey, String, Integer, Numeric, DateTime, select, UniqueConstraint, inspect, or_, and_, Index, text, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./pos.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)

if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_connect(connection, record):
        connection.isolation_level = None
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=15000')

    @event.listens_for(engine, 'begin')
    def sqlite_begin(connection):
        connection.exec_driver_sql('BEGIN IMMEDIATE')

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

class CashRegister(Base):
    __tablename__ = 'cash_registers'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'))
    name: Mapped[str] = mapped_column(String(80))
    __table_args__ = (UniqueConstraint('branch_id', 'name'),)

class CashSession(Base):
    __tablename__ = 'cash_sessions'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'))
    register_id: Mapped[int | None] = mapped_column(ForeignKey('cash_registers.id'), nullable=True)
    cashier_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    expected_on_close: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    opening: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    counted: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default='open')
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

Index('uq_open_register', CashSession.register_id, unique=True, sqlite_where=text("status = 'open'"), postgresql_where=text("status = 'open'"))
Index('uq_open_cashier_branch', CashSession.branch_id, CashSession.cashier_id, unique=True, sqlite_where=text("status = 'open'"), postgresql_where=text("status = 'open'"))

class CashMovement(Base):
    __tablename__ = 'cash_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer)
    branch_id: Mapped[int] = mapped_column(Integer)
    session_id: Mapped[int] = mapped_column(ForeignKey('cash_sessions.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    request_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    __table_args__ = (UniqueConstraint('empresa_id', 'request_key'),)
    kind: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class StockMovement(Base):
    __tablename__ = 'stock_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer)
    branch_id: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
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
    barcode: Mapped[str | None] = mapped_column(String(80), nullable=True)
    unit: Mapped[str] = mapped_column(String(30), default='pieza')
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal('.16'))
    tax_exempt: Mapped[bool] = mapped_column(default=False)
    price_includes_tax: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (UniqueConstraint('empresa_id', 'sku'), UniqueConstraint('empresa_id', 'barcode'))

class Customer(Base):
    __tablename__ = 'customers'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Stock(Base):
    __tablename__ = 'stock'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    branch_id: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal('0'))
    __table_args__ = (UniqueConstraint('product_id', 'branch_id'),)

class Sale(Base):
    __tablename__ = 'sales'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    branch_id: Mapped[int] = mapped_column(Integer)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey('customers.id'), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    folio: Mapped[str | None] = mapped_column(String(60), nullable=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal('0'))
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal('0'))
    discount_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    discount_approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payment_method: Mapped[str] = mapped_column(String(30))
    cash_session_id: Mapped[int] = mapped_column(ForeignKey('cash_sessions.id'))
    request_key: Mapped[str] = mapped_column(String(100))
    paid: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    items: Mapped[list['SaleItem']] = relationship(cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('empresa_id', 'request_key'), UniqueConstraint('empresa_id', 'folio'))

class SaleItem(Base):
    __tablename__ = 'sale_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey('sales.id'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit: Mapped[str] = mapped_column(String(30), default='pieza')
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal('.16'))
    tax_exempt: Mapped[bool] = mapped_column(default=False)
    price_includes_tax: Mapped[bool] = mapped_column(default=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal('0'))
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal('0'))

class SaleReturn(Base):
    __tablename__ = 'sale_returns'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey('sales.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    cash_session_id: Mapped[int | None] = mapped_column(ForeignKey('cash_sessions.id'), nullable=True)
    reason: Mapped[str] = mapped_column(String(160))
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[str] = mapped_column(String(20000))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    request_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    items: Mapped[list['SaleReturnItem']] = relationship(cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('empresa_id', 'request_key'),)

class SaleReturnItem(Base):
    __tablename__ = 'sale_return_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey('sale_returns.id'))
    sale_item_id: Mapped[int] = mapped_column(ForeignKey('sale_items.id'))
    quantity: Mapped[int] = mapped_column(Integer)
    restock: Mapped[bool] = mapped_column(default=True)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    __table_args__ = (UniqueConstraint('return_id', 'sale_item_id'),)

class Supplier(Base):
    __tablename__ = 'suppliers'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

class Purchase(Base):
    __tablename__ = 'purchases'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'))
    supplier_id: Mapped[int] = mapped_column(ForeignKey('suppliers.id'))
    reference: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    request_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default='ordered')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    items: Mapped[list['PurchaseItem']] = relationship(cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('empresa_id', 'request_key'),)

class PurchaseItem(Base):
    __tablename__ = 'purchase_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey('purchases.id'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    received: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    __table_args__ = (UniqueConstraint('purchase_id', 'product_id'),)

class PurchaseReceipt(Base):
    __tablename__ = 'purchase_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer)
    purchase_id: Mapped[int] = mapped_column(ForeignKey('purchases.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    request_key: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(String(4000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('empresa_id', 'request_key'),)

class InventoryCount(Base):
    __tablename__ = 'inventory_counts'
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(Integer)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expected: Mapped[int] = mapped_column(Integer)
    counted: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(160))
    request_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('empresa_id', 'request_key'),)

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

class ApprovalIn(BaseModel):
    username: str
    password: str

class SaleIn(BaseModel):
    branch_id: int = Field(gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    cash_session_id: int | None = Field(default=None, gt=0)
    discount_percent: Decimal = Field(default=Decimal('0'), ge=0, lt=100, decimal_places=2)
    discount_reason: str | None = Field(default=None, max_length=160)
    approval: ApprovalIn | None = None
    items: list[Line] = Field(min_length=1)
    payment_method: str
    paid: Decimal = Field(ge=0, le=9999999999, decimal_places=2)

class ProductFields(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    price: Decimal = Field(gt=0, le=9999999999, decimal_places=2)
    barcode: str | None = Field(default=None, max_length=80)
    unit: str = Field(default='pieza', min_length=1, max_length=30)
    tax_rate: Decimal = Field(default=Decimal('.16'), ge=0, le=1, decimal_places=4)
    tax_exempt: bool = False
    price_includes_tax: bool = False
    active: bool = True
    @field_validator('barcode')
    @classmethod
    def empty_barcode(cls, value):
        return value or None

class ProductUpdate(ProductFields):
    branch_id: int = Field(gt=0)

class ProductIn(ProductFields):
    initial_cost: Decimal = Field(default=Decimal('0'), ge=0, le=99999999, decimal_places=4)
    branch_id: int = Field(gt=0)
    stock: int = Field(ge=0)

class CustomerIn(BaseModel):
    branch_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=30)

class CustomerUpdate(CustomerIn):
    pass

class RegisterIn(BaseModel):
    branch_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=80)

class OpenCash(BaseModel):
    register_id: int | None = Field(default=None, gt=0)
    branch_id: int = Field(gt=0)
    opening: Decimal = Field(ge=0, le=9999999999, decimal_places=2)

class CloseCash(BaseModel):
    counted: Decimal = Field(ge=0, le=9999999999, decimal_places=2)

class WithdrawCash(BaseModel):
    amount: Decimal = Field(gt=0, le=9999999999, decimal_places=2)
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
    'admin_general': {'sale_return', 'discount', 'purchase_write', 'purchase_read', 'count_write', 'cash_deposit', 'sale', 'catalog_write', 'customer_read', 'customer_write', 'stock_write', 'cash_open', 'cash_close', 'cash_withdraw', 'report', 'users_write'},
    'admin_sucursal': {'sale_return', 'discount', 'purchase_write', 'purchase_read', 'count_write', 'cash_deposit', 'sale', 'catalog_write', 'customer_read', 'customer_write', 'stock_write', 'cash_open', 'cash_close', 'cash_withdraw', 'report'},
    'cajero': {'sale', 'customer_read', 'customer_write', 'cash_open', 'cash_close'},
    'almacenista': {'stock_write', 'purchase_read', 'purchase_receive'},
    'supervisor_inventarios': {'stock_write', 'report', 'purchase_read', 'purchase_receive', 'count_write'},
    'contabilidad': {'report', 'customer_read', 'purchase_read'},
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
    return {'id': user.id, 'username': user.username, 'role': user.role, 'permissions': sorted(ROLE_ACTIONS.get(user.role, set()))}

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

def cash_access(db, user, session, owner=False):
    branch_for(db, user, session.branch_id)
    if session.cashier_id != user.id and (owner or user.role not in ('admin_general', 'admin_sucursal', 'contabilidad', 'auditoria')):
        raise HTTPException(403, 'Este turno pertenece a otro cajero')


def cash_totals(db, session):
    sales = db.scalars(select(Sale).where(Sale.cash_session_id == session.id, Sale.payment_method == 'cash')).all()
    movements = db.scalars(select(CashMovement).where(CashMovement.session_id == session.id)).all()
    withdrawn = sum((m.amount for m in movements if m.kind == 'withdrawal'), Decimal('0'))
    deposited = sum((m.amount for m in movements if m.kind == 'deposit'), Decimal('0'))
    refunded = sum((m.amount for m in movements if m.kind == 'refund'), Decimal('0'))
    expected = money(session.opening + sum((s.total for s in sales), Decimal('0')) + deposited - withdrawn - refunded)
    return {'expected': str(expected), 'withdrawn': str(money(withdrawn)), 'deposited': str(money(deposited)), 'cash_sales': len(sales), 'refunded': str(money(refunded))}


def cash_view(db, session):
    cashier = db.get(User, session.cashier_id) if session.cashier_id else None
    register = db.get(CashRegister, session.register_id) if session.register_id else None
    return {'open': session.status == 'open', 'id': session.id, 'register_id': session.register_id,
            'register_name': register.name if register else 'Caja anterior', 'cashier_id': session.cashier_id,
            'cashier_name': cashier.username if cashier else 'Sin responsable (turno anterior)',
            'opening': str(session.opening), 'status': session.status, 'opened_at': session.opened_at.isoformat(),
            'closed_at': session.closed_at.isoformat() if session.closed_at else None,
            'counted': str(session.counted) if session.counted is not None else None,
            **cash_totals(db, session)}

@app.get('/api/cash/registers')
def registers(branch_id: int, user: User = Depends(identity)):
    require_any(user, 'cash_open', 'report')
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        return [{'id': r.id, 'name': r.name} for r in db.scalars(select(CashRegister).where(
            CashRegister.branch_id == branch_id, CashRegister.empresa_id == user.empresa_id).order_by(CashRegister.id))]

@app.post('/api/cash/registers', status_code=201)
def create_register(data: RegisterIn, user: User = Depends(identity)):
    require(user, 'cash_deposit')
    if not data.name.strip():
        raise HTTPException(422, 'Nombre de caja vacío')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        register = CashRegister(empresa_id=user.empresa_id, branch_id=data.branch_id, name=data.name.strip())
        db.add(register)
        try:
            db.flush()
            db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id, action='register_created', record_id=register.id, actor_id=user.id))
            result = {'id': register.id, 'name': register.name}
            db.commit()
            return result
        except IntegrityError:
            raise HTTPException(409, 'Ya existe una caja con ese nombre')

@app.post('/api/cash/open', status_code=201)
def open_cash(data: OpenCash, user: User = Depends(identity)):
    require(user, 'cash_open')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        db.scalar(select(Branch).where(Branch.id == data.branch_id).with_for_update())
        query = select(CashRegister).where(CashRegister.branch_id == data.branch_id, CashRegister.empresa_id == user.empresa_id)
        if data.register_id:
            query = query.where(CashRegister.id == data.register_id)
        register = db.scalar(query.order_by(CashRegister.id).with_for_update())
        if register is None:
            raise HTTPException(404, 'Caja no encontrada en esta sucursal')
        existing = db.scalar(select(CashSession).where(CashSession.branch_id == data.branch_id, CashSession.status == 'open',
                    or_(CashSession.register_id == register.id, CashSession.cashier_id == user.id)))
        if existing:
            raise HTTPException(409, 'La caja o el cajero ya tiene un turno abierto')
        session = CashSession(empresa_id=user.empresa_id, branch_id=data.branch_id, register_id=register.id,
                              cashier_id=user.id, opening=money(data.opening))
        db.add(session)
        try:
            db.flush()
            db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id, action='cash_opened', record_id=session.id, actor_id=user.id))
            result = cash_view(db, session)
            db.commit()
            return result
        except IntegrityError:
            raise HTTPException(409, 'La caja o el cajero ya tiene un turno abierto')

@app.get('/api/cash/current')
def current_cash(branch_id: int, register_id: int | None = None, user: User = Depends(identity)):
    require_any(user, 'cash_open', 'report')
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        query = select(CashSession).where(CashSession.empresa_id == user.empresa_id, CashSession.branch_id == branch_id, CashSession.status == 'open')
        if register_id:
            query = query.where(CashSession.register_id == register_id)
        elif user.role not in ('admin_general', 'admin_sucursal', 'contabilidad', 'auditoria'):
            query = query.where(CashSession.cashier_id == user.id)
        session = db.scalar(query.order_by(CashSession.id.desc()))
        if not session:
            return {'open': False}
        cash_access(db, user, session)
        return cash_view(db, session)

@app.get('/api/cash/sessions')
def cash_sessions(branch_id: int, user: User = Depends(identity)):
    require_any(user, 'cash_open', 'report')
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        query = select(CashSession).where(CashSession.empresa_id == user.empresa_id, CashSession.branch_id == branch_id)
        if user.role not in ('admin_general', 'admin_sucursal', 'contabilidad', 'auditoria'):
            query = query.where(CashSession.cashier_id == user.id)
        return [cash_view(db, s) for s in db.scalars(query.order_by(CashSession.id.desc()).limit(100))]


def post_cash_movement(session_id, data, user, kind, key):
    require(user, 'cash_withdraw' if kind == 'withdrawal' else 'cash_deposit')
    reason = data.reason.strip()
    if len(reason) < 3 or money(data.amount) <= 0:
        raise HTTPException(422, 'Importe o motivo inválidos')
    with Session(engine) as db:
        session = db.scalar(select(CashSession).where(CashSession.id == session_id, CashSession.empresa_id == user.empresa_id).with_for_update())
        if session is None:
            raise HTTPException(404, 'Turno no encontrado')
        cash_access(db, user, session)
        previous = db.scalar(select(CashMovement).where(CashMovement.empresa_id == user.empresa_id, CashMovement.request_key == key)) if key else None
        if previous:
            if (previous.session_id, previous.amount, previous.kind, previous.reason) != (session.id, money(data.amount), kind, reason):
                raise HTTPException(409, 'Clave de movimiento utilizada con otros datos')
            return {'id': previous.id, 'amount': str(previous.amount), 'replayed': True}
        if session.status != 'open':
            raise HTTPException(409, 'El turno está cerrado')
        available = Decimal(cash_totals(db, session)['expected'])
        amount = money(data.amount)
        if kind == 'withdrawal' and amount > available:
            raise HTTPException(409, 'Efectivo insuficiente en caja')
        movement = CashMovement(empresa_id=user.empresa_id, branch_id=session.branch_id, session_id=session.id,
                               actor_id=user.id, request_key=key, amount=amount, kind=kind, reason=reason)
        db.add(movement)
        try:
            db.flush()
            db.add(Audit(empresa_id=user.empresa_id, branch_id=session.branch_id, action=f'cash_{kind}', record_id=movement.id, actor_id=user.id))
            result = {'id': movement.id, 'amount': str(amount), 'expected_after': str(money(available + (amount if kind == 'deposit' else -amount))), 'replayed': False}
            db.commit()
            return result
        except IntegrityError:
            raise HTTPException(409, 'Movimiento duplicado; vuelve a consultar el turno')

@app.post('/api/cash/{session_id}/withdraw', status_code=201)
def withdraw_cash(session_id: int, data: WithdrawCash, idempotency_key: str | None = Header(default=None, min_length=8, max_length=100), user: User = Depends(identity)):
    return post_cash_movement(session_id, data, user, 'withdrawal', idempotency_key)

@app.post('/api/cash/{session_id}/deposit', status_code=201)
def deposit_cash(session_id: int, data: WithdrawCash, idempotency_key: str | None = Header(default=None, min_length=8, max_length=100), user: User = Depends(identity)):
    return post_cash_movement(session_id, data, user, 'deposit', idempotency_key)

@app.get('/api/cash/{session_id}/movements')
def cash_movements(session_id: int, user: User = Depends(identity)):
    require_any(user, 'cash_open', 'report')
    with Session(engine) as db:
        session = db.scalar(select(CashSession).where(CashSession.id == session_id, CashSession.empresa_id == user.empresa_id))
        if session is None:
            raise HTTPException(404, 'Turno no encontrado')
        cash_access(db, user, session)
        return [{'id': m.id, 'amount': str(m.amount), 'kind': m.kind, 'reason': m.reason,
                 'actor_id': m.actor_id, 'created_at': m.created_at.isoformat(), 'session_id': session.id}
                for m in db.scalars(select(CashMovement).where(CashMovement.session_id == session.id).order_by(CashMovement.id))]

@app.post('/api/cash/{session_id}/close')
def close_cash(session_id: int, data: CloseCash, user: User = Depends(identity)):
    require(user, 'cash_close')
    with Session(engine) as db:
        session = db.scalar(select(CashSession).where(CashSession.id == session_id, CashSession.empresa_id == user.empresa_id, CashSession.status == 'open').with_for_update())
        if session is None:
            raise HTTPException(404, 'Turno abierto no encontrado')
        cash_access(db, user, session)
        expected = Decimal(cash_totals(db, session)['expected'])
        session.counted = money(data.counted)
        session.expected_on_close = expected
        session.closed_by = user.id
        session.closed_at = datetime.now(timezone.utc)
        session.status = 'closed'
        db.add(Audit(empresa_id=user.empresa_id, branch_id=session.branch_id, action='cash_closed', record_id=session.id, actor_id=user.id))
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
        product = Product(empresa_id=empresa, **data.model_dump(exclude={'branch_id', 'stock', 'initial_cost'}))
        db.add(product)
        try:
            db.flush()
            db.add(Stock(product_id=product.id, branch_id=data.branch_id, quantity=data.stock, average_cost=data.initial_cost))
            db.add(StockMovement(actor_id=user.id, empresa_id=empresa, branch_id=data.branch_id, product_id=product.id, change=data.stock, reason='initial'))
            db.add(Audit(empresa_id=empresa, branch_id=data.branch_id, action='product_created', record_id=product.id, actor_id=user.id))
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(409, 'SKU duplicado o datos inválidos')
        return {'id': product.id, 'sku': product.sku}

@app.get('/api/products')
def products(branch_id: int, include_unstocked: bool = False, user: User = Depends(identity)):
    empresa = user.empresa_id
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        query = select(Product, Stock).outerjoin(Stock, and_(Stock.product_id == Product.id, Stock.branch_id == branch_id)).where(Product.empresa_id == empresa)
        if not include_unstocked:
            query = query.where(Stock.id.is_not(None))
        rows = db.execute(query.order_by(Product.name)).all()
        return [product_view(p, s) for p, s in rows]

@app.post('/api/customers', status_code=201)
def create_customer(data: CustomerIn, user: User = Depends(identity)):
    require(user, 'customer_write')
    name = data.name.strip()
    phone = data.phone.strip() if data.phone else None
    if len(name) < 2:
        raise HTTPException(422, 'Nombre inválido')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        customer = Customer(empresa_id=user.empresa_id, name=name, phone=phone or None)
        db.add(customer)
        db.flush()
        db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id,
                     action='customer_created', record_id=customer.id, actor_id=user.id))
        result = {'id': customer.id, 'name': customer.name, 'phone': customer.phone}
        db.commit()
        return result

@app.get('/api/customers')
def customers(branch_id: int, q: str = '', user: User = Depends(identity)):
    require(user, 'customer_read')
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        query = select(Customer).where(Customer.empresa_id == user.empresa_id)
        if q.strip():
            term = f'%{q.strip()[:80]}%'
            query = query.where(or_(Customer.name.ilike(term), Customer.phone.ilike(term)))
        rows = db.scalars(query.order_by(Customer.id.desc()).limit(50)).all()
        return [{'id': x.id, 'name': x.name, 'phone': x.phone} for x in rows]

@app.put('/api/customers/{customer_id}')
def update_customer(customer_id: int, data: CustomerUpdate, user: User = Depends(identity)):
    require(user, 'customer_write')
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(422, 'Nombre inválido')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        customer = db.scalar(select(Customer).where(Customer.id == customer_id,
                                                   Customer.empresa_id == user.empresa_id))
        if customer is None:
            raise HTTPException(404, 'Cliente no encontrado')
        customer.name = name
        customer.phone = (data.phone or '').strip() or None
        db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id,
                     action='customer_updated', record_id=customer.id, actor_id=user.id))
        result = {'id': customer.id, 'name': customer.name, 'phone': customer.phone}
        db.commit()
        return result

@app.get('/api/customers/{customer_id}/sales')
def customer_sales(customer_id: int, branch_id: int, user: User = Depends(identity)):
    require(user, 'customer_read')
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        if not db.scalar(select(Customer.id).where(Customer.id == customer_id,
                                                  Customer.empresa_id == user.empresa_id)):
            raise HTTPException(404, 'Cliente no encontrado')
        rows = db.scalars(select(Sale).where(Sale.customer_id == customer_id,
                          Sale.empresa_id == user.empresa_id, Sale.branch_id == branch_id)
                          .order_by(Sale.id.desc()).limit(50)).all()
        return [{'id': s.id, 'created_at': s.created_at.isoformat(), 'total': str(s.total),
                 'payment_method': s.payment_method} for s in rows]

@app.post('/api/products/{product_id}/stock')
def adjust_stock(product_id: int, data: AdjustStock, user: User = Depends(identity)):
    require(user, 'stock_write')
    empresa = user.empresa_id
    if data.change == 0:
        raise HTTPException(422, 'El movimiento debe cambiar existencias')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        db.scalar(select(Branch).where(Branch.id == data.branch_id).with_for_update())
        row = db.execute(select(Product, Stock).join(Stock).where(Product.id == product_id, Product.empresa_id == empresa, Stock.branch_id == data.branch_id).with_for_update()).first()
        if not row:
            raise HTTPException(404, 'Producto sin inventario en sucursal')
        product, stock = row
        if stock.quantity + data.change < 0:
            raise HTTPException(409, 'Inventario insuficiente')
        stock.quantity += data.change
        db.add(StockMovement(actor_id=user.id, empresa_id=empresa, branch_id=data.branch_id, product_id=product.id, change=data.change, reason=data.reason))
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
        return [{'id': x.id, 'product_id': x.product_id, 'change': x.change, 'reason': x.reason, 'reference_id': x.reference_id, 'actor_id': x.actor_id, 'created_at': x.created_at.isoformat()} for x in rows]

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
            target.average_cost = weighted_cost(target.quantity, target.average_cost or Decimal('0'), data.quantity, source.average_cost or Decimal('0'))
            source.quantity -= data.quantity
            target.quantity += data.quantity
            transfer = StockTransfer(empresa_id=user.empresa_id, source_branch_id=data.source_branch_id,
                target_branch_id=data.target_branch_id, product_id=product.id, quantity=data.quantity,
                request_key=idempotency_key, actor_id=user.id)
            db.add(transfer)
            db.flush()
            db.add_all([
                StockMovement(actor_id=user.id, empresa_id=user.empresa_id, branch_id=data.source_branch_id,
                    product_id=product.id, change=-data.quantity, reason='transfer_out', reference_id=transfer.id),
                StockMovement(actor_id=user.id, empresa_id=user.empresa_id, branch_id=data.target_branch_id,
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

def product_view(p, stock):
    return {'id': p.id, 'sku': p.sku, 'barcode': p.barcode, 'name': p.name, 'price': str(p.price),
            'unit': p.unit, 'tax_rate': str(p.tax_rate), 'tax_exempt': p.tax_exempt,
            'price_includes_tax': p.price_includes_tax, 'active': p.active, 'stock': stock.quantity if stock else 0,
            'average_cost': str(stock.average_cost) if stock else '0.0000'}


def weighted_cost(quantity, cost, incoming, incoming_cost):
    return ((quantity * cost + incoming * incoming_cost) / (quantity + incoming)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)

@app.put('/api/products/{product_id}')
def edit_product(product_id: int, data: ProductUpdate, user: User = Depends(identity)):
    require(user, 'catalog_write')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        product = db.scalar(select(Product).where(Product.id == product_id, Product.empresa_id == user.empresa_id).with_for_update())
        if product is None:
            raise HTTPException(404, 'Producto no encontrado')
        for key, value in data.model_dump(exclude={'branch_id'}).items():
            setattr(product, key, value)
        db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id, action='product_updated', record_id=product.id, actor_id=user.id))
        try:
            db.commit()
            return {'id': product.id, 'sku': product.sku}
        except IntegrityError:
            raise HTTPException(409, 'SKU o código de barras duplicado')


def approve_discount(db, user, data):
    if not data.discount_percent:
        return None
    if not data.discount_reason or len(data.discount_reason.strip()) < 3:
        raise HTTPException(422, 'Indica el motivo del descuento')
    approver = user
    if data.approval:
        approver = db.scalar(select(User).where(User.username == data.approval.username, User.empresa_id == user.empresa_id))
        if approver is None or not approver.active or not password_hash.verify(data.approval.password, approver.password_hash):
            raise HTTPException(403, 'Autorización de descuento inválida')
    require(approver, 'discount')
    branch_for(db, approver, data.branch_id)
    return approver.id


def price_line(product, quantity, percent):
    # Round each line, so printed totals equal the sum of the stored lines.
    gross = money(product.price * quantity)
    discount = money(gross * percent / Decimal('100'))
    discounted = gross - discount
    rate = Decimal('0') if product.tax_exempt else product.tax_rate
    net = money(discounted / (Decimal('1') + rate)) if product.price_includes_tax else discounted
    tax = discounted - net if product.price_includes_tax else money(net * rate)
    return net, tax, discount


@app.post('/api/sales/quote')
def sale_quote(data: SaleIn, user: User = Depends(identity)):
    require(user, 'sale')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        ids = [x.product_id for x in data.items]
        rows = db.scalars(select(Product).where(Product.empresa_id == user.empresa_id, Product.id.in_(ids), Product.active == True)).all()
        if len(rows) != len(ids) or len(ids) != len(set(ids)):
            raise HTTPException(422, 'Carrito con productos inválidos o duplicados')
        by_id = {p.id: p for p in rows}
        amounts = [price_line(by_id[x.product_id], x.quantity, data.discount_percent) for x in data.items]
        subtotal = sum((a[0] for a in amounts), Decimal('0'))
        tax = sum((a[1] for a in amounts), Decimal('0'))
        return {'subtotal': str(subtotal), 'tax': str(tax), 'discount_total': str(sum((a[2] for a in amounts), Decimal('0'))), 'total': str(subtotal + tax)}


def sale_result(sale, replayed=False):
    return {'id': sale.id, 'folio': sale.folio or f'LI-B{sale.branch_id}-{sale.id:08d}',
            'subtotal': str(sale.subtotal), 'tax': str(sale.tax), 'discount_total': str(sale.discount_total),
            'total': str(sale.total), 'change': str(money(sale.paid - sale.total)), 'replayed': replayed}

@app.post('/api/sales', status_code=201)
def sell(data: SaleIn, idempotency_key: str = Header(min_length=8, max_length=100), user: User = Depends(identity)):
    require(user, 'sale')
    if data.payment_method not in ('cash', 'card', 'transfer'):
        raise HTTPException(422, 'Forma de pago inválida')
    ids = [i.product_id for i in data.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, 'Productos duplicados en carrito')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        db.scalar(select(Branch).where(Branch.id == data.branch_id).with_for_update())
        existing = db.scalar(select(Sale).where(Sale.empresa_id == user.empresa_id, Sale.request_key == idempotency_key))
        if existing:
            previous = sorted((x.product_id, x.quantity) for x in existing.items)
            incoming = sorted((x.product_id, x.quantity) for x in data.items)
            if (existing.branch_id != data.branch_id or existing.customer_id != data.customer_id
                or existing.payment_method != data.payment_method or existing.paid != money(data.paid)
                or previous != incoming or existing.discount_percent != data.discount_percent
                or (existing.discount_reason or '') != (data.discount_reason or '').strip()
                or (data.cash_session_id is not None and existing.cash_session_id != data.cash_session_id)):
                raise HTTPException(409, 'Clave de venta ya utilizada para otra operación')
            if existing.actor_id is not None and existing.actor_id != user.id:
                raise HTTPException(403, 'El reintento pertenece a otro cajero')
            return sale_result(existing, True)
        customer = db.scalar(select(Customer).where(Customer.id == data.customer_id, Customer.empresa_id == user.empresa_id)) if data.customer_id else None
        if data.customer_id and customer is None:
            raise HTTPException(404, 'Cliente fuera de esta empresa o inexistente')
        query = select(CashSession).where(CashSession.empresa_id == user.empresa_id, CashSession.branch_id == data.branch_id, CashSession.status == 'open')
        query = query.where(CashSession.id == data.cash_session_id) if data.cash_session_id else query.where(CashSession.cashier_id == user.id)
        cash = db.scalar(query.with_for_update())
        if not cash:
            raise HTTPException(409, 'Abre tu turno de caja antes de vender')
        cash_access(db, user, cash, owner=True)
        approved_by = approve_discount(db, user, data)
        rows = db.execute(select(Product, Stock).join(Stock).where(Product.id.in_(ids), Product.empresa_id == user.empresa_id,
                        Stock.branch_id == data.branch_id).order_by(Product.id).with_for_update()).all()
        mapped = {p.id: (p, stock) for p, stock in rows}
        if len(mapped) != len(ids):
            raise HTTPException(404, 'Producto fuera de esta empresa o sucursal')
        subtotal, tax, discount = Decimal('0'), Decimal('0'), Decimal('0')
        sale_lines = []
        for item in data.items:
            product, stock = mapped[item.product_id]
            if not product.active:
                raise HTTPException(409, f'Producto inactivo: {product.name}')
            if stock.quantity < item.quantity:
                raise HTTPException(409, f'Sin existencias suficientes: {product.name}')
            net, line_tax, line_discount = price_line(product, item.quantity, data.discount_percent)
            subtotal += net
            tax += line_tax
            discount += line_discount
            stock.quantity -= item.quantity
            sale_lines.append(SaleItem(product_id=product.id, name=product.name, quantity=item.quantity, unit_price=product.price,
                unit=product.unit, tax_rate=product.tax_rate, tax_exempt=product.tax_exempt, price_includes_tax=product.price_includes_tax,
                discount_amount=line_discount, net_amount=net, tax_amount=line_tax, cost=stock.average_cost))
        total = subtotal + tax
        if total > Decimal('9999999999.99') or subtotal > Decimal('9999999999.99') or discount > Decimal('9999999999.99'):
            raise HTTPException(422, 'El importe excede el límite de una venta')
        if data.payment_method == 'cash' and money(data.paid) < total:
            raise HTTPException(422, 'Pago insuficiente')
        if data.payment_method != 'cash' and money(data.paid) != total:
            raise HTTPException(422, 'El pago debe coincidir con el total')
        sale = Sale(empresa_id=user.empresa_id, branch_id=data.branch_id, customer_id=data.customer_id,
                    customer_name=customer.name if customer else None, cash_session_id=cash.id, actor_id=user.id,
                    discount_percent=data.discount_percent, discount_total=discount, discount_reason=(data.discount_reason or '').strip() or None,
                    discount_approved_by=approved_by, request_key=idempotency_key, subtotal=subtotal, tax=tax,
                    total=total, payment_method=data.payment_method, paid=money(data.paid), items=sale_lines)
        db.add(sale)
        try:
            db.flush()
            sale.folio = f'LI-B{data.branch_id}-{sale.id:08d}'
            for item in data.items:
                db.add(StockMovement(empresa_id=user.empresa_id, branch_id=data.branch_id, product_id=item.product_id,
                       change=-item.quantity, reason='sale', reference_id=sale.id, actor_id=user.id))
            db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id, action='sale_created', record_id=sale.id, actor_id=user.id))
            if approved_by:
                db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id, action='discount_approved', record_id=sale.id, actor_id=approved_by))
            result = sale_result(sale)
            db.commit()
            return result
        except IntegrityError:
            raise HTTPException(409, 'Venta duplicada; vuelve a consultar el historial')

@app.get('/api/sales')
def sales(branch_id: int, user: User = Depends(identity)):
    require_any(user, 'sale', 'report')
    empresa = user.empresa_id
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        rows = db.scalars(select(Sale).where(Sale.empresa_id == empresa, Sale.branch_id == branch_id).order_by(Sale.id.desc()).limit(30)).all()
        return [{'id': s.id, 'folio': s.folio, 'total': str(s.total), 'created_at': s.created_at.isoformat(), 'payment_method': s.payment_method} for s in rows]

@app.get('/api/sales/{sale_id}')
def sale_detail(sale_id: int, user: User = Depends(identity)):
    require_any(user, 'sale', 'report')
    with Session(engine) as db:
        sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.empresa_id == user.empresa_id))
        if sale is None:
            raise HTTPException(404, 'Venta no encontrada')
        branch = branch_for(db, user, sale.branch_id)
        customer = db.get(Customer, sale.customer_id) if sale.customer_id else None
        return {
            'folio': sale.folio, 'discount_total': str(sale.discount_total), 'discount_percent': str(sale.discount_percent),
            'discount_reason': sale.discount_reason, 'discount_approved_by': sale.discount_approved_by,
            'cash_session_id': sale.cash_session_id, 'actor_id': sale.actor_id,
            'id': sale.id, 'branch_id': branch.id, 'branch_name': branch.name,
            'customer_id': sale.customer_id, 'customer_name': sale.customer_name or (customer.name if customer else None),
            'created_at': sale.created_at.isoformat(), 'payment_method': sale.payment_method,
            'subtotal': str(sale.subtotal), 'tax': str(sale.tax), 'total': str(sale.total),
            'paid': str(sale.paid), 'change': str(money(sale.paid - sale.total)),
            'items': [
                {'id': item.id, 'product_id': item.product_id, 'name': item.name, 'quantity': item.quantity,
                 'returned_quantity': returned_quantities(db, sale.id).get(item.id, 0),
                 'refundable_total': str(refundable_line_total(sale, item)) if item.net_amount is not None or not sale.discount_total else None,
                 'unit_price': str(item.unit_price), 'unit': item.unit, 'tax_rate': str(item.tax_rate), 'tax_exempt': item.tax_exempt,
                 'discount': str(item.discount_amount), 'net': str(item.net_amount) if item.net_amount is not None else None,
                 'tax': str(item.tax_amount) if item.tax_amount is not None else None,
                 'line_total': str(item.net_amount) if item.net_amount is not None else str(money(item.unit_price * item.quantity))}
                for item in sale.items
            ],
        }

class ReturnLine(BaseModel):
    sale_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=10000)
    restock: bool = True

class ReturnIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=160)
    cash_session_id: int | None = Field(default=None, gt=0)
    payment_reference: str | None = Field(default=None, max_length=100)
    items: list[ReturnLine] = Field(min_length=1, max_length=100)


def returned_quantities(db, sale_id):
    rows = db.scalars(select(SaleReturnItem).join(SaleReturn).where(SaleReturn.sale_id == sale_id)).all()
    totals = {}
    for item in rows:
        totals[item.sale_item_id] = totals.get(item.sale_item_id, 0) + item.quantity
    return totals


def return_view(record, replayed=False):
    return {'id': record.id, 'sale_id': record.sale_id, 'total': str(record.total),
            'reason': record.reason, 'actor_id': record.actor_id, 'cash_session_id': record.cash_session_id,
            'payment_reference': record.payment_reference, 'created_at': record.created_at.isoformat(),
            'items': [{'sale_item_id': x.sale_item_id, 'quantity': x.quantity, 'restock': x.restock,
                       'total': str(x.total)} for x in record.items], 'replayed': replayed}


def refundable_line_total(sale, item):
    if item.net_amount is not None and item.tax_amount is not None:
        return item.net_amount + item.tax_amount
    # Legacy tickets lack stored line taxes. Allocate the original total; refuse
    # discounted legacy records whose allocation cannot be established reliably.
    if sale.discount_total:
        raise HTTPException(409, 'Venta antigua sin desglose: requiere revisión de administración')
    gross = sum((x.unit_price * x.quantity for x in sale.items), Decimal('0'))
    if gross <= 0:
        raise HTTPException(409, 'Venta antigua sin importes válidos')
    ordered = sorted(sale.items, key=lambda x: x.id)
    before = sum((x.unit_price * x.quantity for x in ordered if x.id < item.id), Decimal('0'))
    return money(sale.total * (before + item.unit_price * item.quantity) / gross) - money(sale.total * before / gross)


@app.get('/api/sales/{sale_id}/returns')
def sale_returns(sale_id: int, user: User = Depends(identity)):
    require_any(user, 'sale', 'report', 'sale_return')
    with Session(engine) as db:
        sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.empresa_id == user.empresa_id))
        if sale is None:
            raise HTTPException(404, 'Venta no encontrada')
        branch_for(db, user, sale.branch_id)
        return [return_view(r) for r in db.scalars(select(SaleReturn).where(SaleReturn.sale_id == sale.id).order_by(SaleReturn.id.desc()))]


@app.post('/api/sales/{sale_id}/returns', status_code=201)
def create_return(sale_id: int, data: ReturnIn, idempotency_key: str = Header(min_length=8, max_length=100), user: User = Depends(identity)):
    require(user, 'sale_return')
    ids = [x.sale_item_id for x in data.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, 'Partidas duplicadas')
    payload = json.dumps({'sale_id': sale_id, **data.model_dump(mode='json'),
                          'items': sorted([x.model_dump() for x in data.items], key=lambda x: x['sale_item_id'])}, sort_keys=True)
    with Session(engine) as db:
        sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.empresa_id == user.empresa_id))
        if sale is None:
            raise HTTPException(404, 'Venta no encontrada')
        branch_for(db, user, sale.branch_id)
        # Same lock order as checkout: branch, cash, stock. Serializes returns
        # against each other and against checkout in this branch on PostgreSQL.
        db.scalar(select(Branch).where(Branch.id == sale.branch_id).with_for_update())
        existing = db.scalar(select(SaleReturn).where(SaleReturn.empresa_id == user.empresa_id, SaleReturn.request_key == idempotency_key))
        if existing:
            if existing.actor_id != user.id or existing.payload != payload:
                raise HTTPException(409, 'Clave de devolución utilizada para otra operación')
            return return_view(existing, True)
        cash = None
        if sale.payment_method == 'cash':
            cash = db.scalar(select(CashSession).where(CashSession.id == data.cash_session_id,
                CashSession.empresa_id == user.empresa_id, CashSession.branch_id == sale.branch_id).with_for_update())
            if cash is None or cash.status != 'open':
                raise HTTPException(409, 'Selecciona un turno abierto de la misma sucursal para reembolsar')
        elif not data.payment_reference:
            raise HTTPException(422, 'Indica la referencia del reembolso externo realizado')
        elif data.cash_session_id is not None:
            raise HTTPException(422, 'Un reembolso externo no debe afectar efectivo')
        already = returned_quantities(db, sale.id)
        by_id = {x.id: x for x in sale.items}
        lines, total = [], Decimal('0')
        for incoming in data.items:
            item = by_id.get(incoming.sale_item_id)
            if item is None:
                raise HTTPException(422, 'Partida fuera de esta venta')
            previous = already.get(item.id, 0)
            if previous + incoming.quantity > item.quantity:
                raise HTTPException(409, 'La cantidad supera lo pendiente por devolver')
            original = refundable_line_total(sale, item)
            # Cumulative rounding leaves no lost/extra cents over partial returns.
            amount = money(original * (previous + incoming.quantity) / item.quantity) - money(original * previous / item.quantity)
            total += amount
            lines.append(SaleReturnItem(sale_item_id=item.id, quantity=incoming.quantity, restock=incoming.restock, total=amount))
        if cash and Decimal(cash_totals(db, cash)['expected']) < total:
            raise HTTPException(409, 'Efectivo insuficiente en el turno para el reembolso')
        record = SaleReturn(empresa_id=user.empresa_id, sale_id=sale.id, actor_id=user.id,
            cash_session_id=cash.id if cash else None, reason=data.reason, payment_reference=data.payment_reference,
            payload=payload, total=total, request_key=idempotency_key, items=lines)
        db.add(record)
        db.flush()
        for incoming in sorted(data.items, key=lambda x: by_id[x.sale_item_id].product_id):
            if not incoming.restock:
                continue
            item = by_id[incoming.sale_item_id]
            stock = db.scalar(select(Stock).where(Stock.product_id == item.product_id, Stock.branch_id == sale.branch_id).with_for_update())
            if stock is None:
                raise HTTPException(409, 'Existencia de la venta no encontrada; revisa el inventario')
            new_quantity = stock.quantity + incoming.quantity
            stock.average_cost = ((stock.average_cost * stock.quantity + item.cost * incoming.quantity) / new_quantity).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)
            stock.quantity = new_quantity
            db.add(StockMovement(empresa_id=user.empresa_id, branch_id=sale.branch_id, product_id=item.product_id,
                actor_id=user.id, change=incoming.quantity, reason='sale_return', reference_id=record.id))
        if cash:
            db.add(CashMovement(empresa_id=user.empresa_id, branch_id=sale.branch_id, session_id=cash.id,
                actor_id=user.id, amount=total, kind='refund', reason=f'Devolución #{record.id}: {data.reason}'[:160]))
        db.add(Audit(empresa_id=user.empresa_id, branch_id=sale.branch_id, actor_id=user.id, action='sale_return', record_id=record.id))
        db.flush()
        result = return_view(record)
        db.commit()
        return result

@app.get('/api/reports/summary')
def summary(branch_id: int, user: User = Depends(identity)):
    require(user, 'report')
    empresa = user.empresa_id
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        rows = db.scalars(select(Sale).where(Sale.empresa_id == empresa, Sale.branch_id == branch_id)).all()
        returns = db.scalars(select(SaleReturn).join(Sale).where(Sale.empresa_id == empresa, Sale.branch_id == branch_id)).all()
        methods = {s.id: s.payment_method for s in rows}
        refunded = sum((r.total for r in returns), Decimal('0'))
        by_method = {method: str(money(sum((s.total for s in rows if s.payment_method == method), Decimal('0')) - sum((r.total for r in returns if methods[r.sale_id] == method), Decimal('0')))) for method in ('cash', 'card', 'transfer')}
        return {'branch_id': branch_id, 'sales_count': len(rows), 'gross_total': str(money(sum((s.total for s in rows), Decimal('0')))), 'returns_total': str(money(refunded)), 'total': str(money(sum((s.total for s in rows), Decimal('0')) - refunded)), 'by_method': by_method}

class SupplierIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    branch_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=30)
    reference: str | None = Field(default=None, max_length=100)

class PurchaseLine(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100000)
    unit_cost: Decimal = Field(ge=0, le=99999999, decimal_places=4)

class PurchaseIn(BaseModel):
    branch_id: int = Field(gt=0)
    supplier_id: int = Field(gt=0)
    reference: str = Field(min_length=1, max_length=100)
    items: list[PurchaseLine] = Field(min_length=1, max_length=100)

class ReceiptIn(BaseModel):
    items: list[Line] = Field(min_length=1, max_length=100)

class CountIn(BaseModel):
    branch_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    expected: int = Field(ge=0, le=100000000)
    counted: int = Field(ge=0, le=100000000)
    reason: str = Field(min_length=3, max_length=160)

@app.get('/api/suppliers')
def suppliers(branch_id: int, user: User = Depends(identity)):
    require_any(user, 'purchase_write', 'purchase_read')
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        return [{'id': s.id, 'name': s.name, 'phone': s.phone, 'reference': s.reference}
                for s in db.scalars(select(Supplier).where(Supplier.empresa_id == user.empresa_id).order_by(Supplier.name))]

@app.post('/api/suppliers', status_code=201)
def create_supplier(data: SupplierIn, user: User = Depends(identity)):
    require(user, 'purchase_write')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        supplier = Supplier(empresa_id=user.empresa_id, **data.model_dump(exclude={'branch_id'}))
        db.add(supplier)
        db.flush()
        db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id, actor_id=user.id, action='supplier_created', record_id=supplier.id))
        result = {'id': supplier.id, 'name': supplier.name}
        db.commit()
        return result


@app.put('/api/suppliers/{supplier_id}')
def update_supplier(supplier_id: int, data: SupplierIn, user: User = Depends(identity)):
    require(user, 'purchase_write')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        supplier = db.scalar(select(Supplier).where(Supplier.id == supplier_id, Supplier.empresa_id == user.empresa_id))
        if supplier is None:
            raise HTTPException(404, 'Proveedor no encontrado')
        for key, value in data.model_dump(exclude={'branch_id'}).items():
            setattr(supplier, key, value)
        db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id, actor_id=user.id, action='supplier_updated', record_id=supplier.id))
        db.commit()
        return {'id': supplier.id, 'name': supplier.name}

@app.get('/api/purchases/{purchase_id}/receipts')
def purchase_receipts(purchase_id: int, user: User = Depends(identity)):
    import json
    require_any(user, 'purchase_read', 'purchase_write')
    with Session(engine) as db:
        purchase = db.scalar(select(Purchase).where(Purchase.id == purchase_id, Purchase.empresa_id == user.empresa_id))
        if purchase is None:
            raise HTTPException(404, 'Compra no encontrada')
        branch_for(db, user, purchase.branch_id)
        return [{'id': x.id, 'actor_id': x.actor_id, 'created_at': x.created_at.isoformat(),
                'items': [{'product_id': pid, 'quantity': qty} for pid, qty in json.loads(x.payload)]}
                for x in db.scalars(select(PurchaseReceipt).where(PurchaseReceipt.purchase_id == purchase.id).order_by(PurchaseReceipt.id))]


def purchase_view(db, purchase):
    supplier = db.get(Supplier, purchase.supplier_id)
    return {'id': purchase.id, 'branch_id': purchase.branch_id, 'supplier_id': purchase.supplier_id,
            'supplier_name': supplier.name, 'reference': purchase.reference, 'status': purchase.status,
            'created_at': purchase.created_at.isoformat(), 'actor_id': purchase.actor_id,
            'total_cost': str(money(sum((x.unit_cost * x.quantity for x in purchase.items), Decimal('0')))),
            'items': [{'product_id': x.product_id, 'name': x.name, 'quantity': x.quantity,
                       'received': x.received, 'pending': x.quantity - x.received, 'unit_cost': str(x.unit_cost)} for x in purchase.items]}

@app.get('/api/purchases')
def purchases(branch_id: int, user: User = Depends(identity)):
    require_any(user, 'purchase_write', 'purchase_read')
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        rows = db.scalars(select(Purchase).where(Purchase.branch_id == branch_id, Purchase.empresa_id == user.empresa_id).order_by(Purchase.id.desc()).limit(100))
        return [purchase_view(db, p) for p in rows]

@app.post('/api/purchases', status_code=201)
def create_purchase(data: PurchaseIn, idempotency_key: str = Header(min_length=8, max_length=100), user: User = Depends(identity)):
    require(user, 'purchase_write')
    ids = [x.product_id for x in data.items]
    if len(ids) != len(set(ids)) or not data.reference.strip():
        raise HTTPException(422, 'Productos duplicados o referencia vacía')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        db.scalar(select(Branch).where(Branch.id == data.branch_id).with_for_update())
        previous = db.scalar(select(Purchase).where(Purchase.empresa_id == user.empresa_id, Purchase.request_key == idempotency_key))
        if previous:
            if (previous.branch_id, previous.supplier_id, previous.reference,
                sorted((x.product_id, x.quantity, x.unit_cost) for x in previous.items)) != (data.branch_id, data.supplier_id,
                data.reference.strip(), sorted((x.product_id, x.quantity, x.unit_cost) for x in data.items)):
                raise HTTPException(409, 'Clave de compra utilizada con otros datos')
            return {**purchase_view(db, previous), 'replayed': True}
        supplier = db.scalar(select(Supplier).where(Supplier.id == data.supplier_id, Supplier.empresa_id == user.empresa_id))
        products = db.scalars(select(Product).where(Product.id.in_(ids), Product.empresa_id == user.empresa_id, Product.active == True)).all()
        if supplier is None or len(products) != len(ids):
            raise HTTPException(404, 'Proveedor o productos fuera de esta empresa, inexistentes o inactivos')
        names = {p.id: p.name for p in products}
        purchase = Purchase(empresa_id=user.empresa_id, branch_id=data.branch_id, supplier_id=supplier.id,
                    reference=data.reference.strip(), request_key=idempotency_key, actor_id=user.id,
                    items=[PurchaseItem(product_id=x.product_id, name=names[x.product_id], quantity=x.quantity, unit_cost=x.unit_cost) for x in data.items])
        db.add(purchase)
        try:
            db.flush()
            db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id, action='purchase_ordered', record_id=purchase.id, actor_id=user.id))
            result = {**purchase_view(db, purchase), 'replayed': False}
            db.commit()
            return result
        except IntegrityError:
            raise HTTPException(409, 'Compra duplicada; consulta la lista de compras')

@app.post('/api/purchases/{purchase_id}/receive', status_code=201)
def receive_purchase(purchase_id: int, data: ReceiptIn, idempotency_key: str = Header(min_length=8, max_length=100), user: User = Depends(identity)):
    import json
    require_any(user, 'purchase_write', 'purchase_receive')
    ids = [x.product_id for x in data.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, 'Productos duplicados en recepción')
    payload = json.dumps(sorted((x.product_id, x.quantity) for x in data.items), separators=(',', ':'))
    with Session(engine) as db:
        purchase = db.scalar(select(Purchase).where(Purchase.id == purchase_id, Purchase.empresa_id == user.empresa_id))
        if purchase is None:
            raise HTTPException(404, 'Compra no encontrada')
        branch_for(db, user, purchase.branch_id)
        db.scalar(select(Branch).where(Branch.id == purchase.branch_id).with_for_update())
        db.refresh(purchase, with_for_update=True)
        previous = db.scalar(select(PurchaseReceipt).where(PurchaseReceipt.empresa_id == user.empresa_id, PurchaseReceipt.request_key == idempotency_key))
        if previous:
            if previous.purchase_id != purchase_id or previous.payload != payload:
                raise HTTPException(409, 'Clave de recepción utilizada con otros datos')
            return {'id': previous.id, 'purchase_id': purchase.id, 'status': purchase.status, 'replayed': True}
        lines = {x.product_id: x for x in purchase.items}
        for item in data.items:
            if item.product_id not in lines or item.quantity > lines[item.product_id].quantity - lines[item.product_id].received:
                raise HTTPException(409, 'La recepción excede la cantidad pendiente o incluye un producto ajeno')
        stocks = {x.product_id: x for x in db.scalars(select(Stock).where(Stock.product_id.in_(ids), Stock.branch_id == purchase.branch_id).order_by(Stock.product_id).with_for_update())}
        receipt = PurchaseReceipt(empresa_id=user.empresa_id, purchase_id=purchase.id, actor_id=user.id, request_key=idempotency_key, payload=payload)
        db.add(receipt)
        try:
            db.flush()
            for item in data.items:
                line = lines[item.product_id]
                stock = stocks.get(item.product_id)
                if stock is None:
                    stock = Stock(product_id=item.product_id, branch_id=purchase.branch_id, quantity=0, average_cost=Decimal('0'))
                    db.add(stock)
                stock.average_cost = weighted_cost(stock.quantity, stock.average_cost, item.quantity, line.unit_cost)
                stock.quantity += item.quantity
                line.received += item.quantity
                db.add(StockMovement(empresa_id=user.empresa_id, branch_id=purchase.branch_id, product_id=item.product_id,
                        change=item.quantity, reason='purchase_received', reference_id=receipt.id, actor_id=user.id))
            purchase.status = 'received' if all(x.received == x.quantity for x in purchase.items) else 'partial'
            db.add(Audit(empresa_id=user.empresa_id, branch_id=purchase.branch_id, action='purchase_received', record_id=receipt.id, actor_id=user.id))
            result = {'id': receipt.id, 'purchase_id': purchase.id, 'status': purchase.status, 'replayed': False}
            db.commit()
            return result
        except IntegrityError:
            raise HTTPException(409, 'Recepción duplicada; consulta la compra')

@app.get('/api/stock/counts')
def inventory_counts(branch_id: int, user: User = Depends(identity)):
    require_any(user, 'stock_write', 'report')
    with Session(engine) as db:
        branch_for(db, user, branch_id)
        return [{'id': x.id, 'product_id': x.product_id, 'expected': x.expected, 'counted': x.counted,
                 'difference': x.counted - x.expected, 'reason': x.reason, 'actor_id': x.actor_id, 'created_at': x.created_at.isoformat()}
                for x in db.scalars(select(InventoryCount).where(InventoryCount.branch_id == branch_id,
                InventoryCount.empresa_id == user.empresa_id).order_by(InventoryCount.id.desc()).limit(100))]

@app.post('/api/stock/counts', status_code=201)
def reconcile_count(data: CountIn, idempotency_key: str = Header(min_length=8, max_length=100), user: User = Depends(identity)):
    require(user, 'count_write')
    if len(data.reason.strip()) < 3:
        raise HTTPException(422, 'Indica el motivo de conciliación')
    with Session(engine) as db:
        branch_for(db, user, data.branch_id)
        db.scalar(select(Branch).where(Branch.id == data.branch_id).with_for_update())
        previous = db.scalar(select(InventoryCount).where(InventoryCount.empresa_id == user.empresa_id, InventoryCount.request_key == idempotency_key))
        if previous:
            if (previous.branch_id, previous.product_id, previous.expected, previous.counted, previous.reason) != (data.branch_id,
                    data.product_id, data.expected, data.counted, data.reason.strip()):
                raise HTTPException(409, 'Clave de conteo utilizada con otros datos')
            return {'id': previous.id, 'difference': previous.counted - previous.expected, 'replayed': True}
        row = db.execute(select(Product, Stock).join(Stock).where(Product.id == data.product_id,
            Product.empresa_id == user.empresa_id, Stock.branch_id == data.branch_id).with_for_update()).first()
        if row is None:
            raise HTTPException(404, 'Producto sin inventario en esta sucursal')
        product, stock = row
        if stock.quantity != data.expected:
            raise HTTPException(409, 'El inventario cambió durante el conteo; actualiza y vuelve a contar')
        count = InventoryCount(empresa_id=user.empresa_id, branch_id=data.branch_id, product_id=product.id, actor_id=user.id,
                               expected=data.expected, counted=data.counted, reason=data.reason.strip(), request_key=idempotency_key)
        stock.quantity = data.counted
        db.add(count)
        try:
            db.flush()
            db.add(StockMovement(empresa_id=user.empresa_id, branch_id=data.branch_id, product_id=product.id,
                   actor_id=user.id, change=data.counted - data.expected, reason='count_reconciled', reference_id=count.id))
            db.add(Audit(empresa_id=user.empresa_id, branch_id=data.branch_id, actor_id=user.id, action='count_reconciled', record_id=count.id))
            result = {'id': count.id, 'difference': data.counted - data.expected, 'replayed': False}
            db.commit()
            return result
        except IntegrityError:
            raise HTTPException(409, 'Conteo duplicado; consulta el inventario')

if os.getenv('APP_ENV', 'demo') != 'production':
    if 'audit_logs' in inspect(engine).get_table_names() and 'actor_id' not in {c['name'] for c in inspect(engine).get_columns('audit_logs')}:
        raise RuntimeError('Base demo anterior: ejecuta python scripts/upgrade_demo_sqlite.py pos.db')
    if 'products' in inspect(engine).get_table_names() and 'barcode' not in {c['name'] for c in inspect(engine).get_columns('products')}:
        raise RuntimeError('Base anterior: ejecuta python scripts/migrate_local.py antes de iniciar')
    if 'products' in inspect(engine).get_table_names() and 'sale_returns' not in inspect(engine).get_table_names():
        raise RuntimeError('Base anterior: ejecuta python scripts/migrate_local.py antes de iniciar')
    Base.metadata.create_all(engine)  # Only for a fresh local demo DB.
    with Session(engine) as db:
        if not db.scalar(select(Branch.id).where(Branch.empresa_id == 1).limit(1)):
            db.add_all(Branch(empresa_id=1, name=name) for name in ('Zamora', 'Zacapu', 'Uruapan', '20 de Noviembre', 'Maravatío', 'CDMX'))
            db.commit()
        for branch in db.scalars(select(Branch)):
            if not db.scalar(select(CashRegister.id).where(CashRegister.branch_id == branch.id)):
                db.add(CashRegister(empresa_id=branch.empresa_id, branch_id=branch.id, name='Caja 1'))
        db.commit()
frontend = Path(__file__).resolve().parents[2] / 'frontend' / 'public'
app.mount('/assets', StaticFiles(directory=frontend), name='assets')
@app.get('/')
def home():
    return FileResponse(frontend / 'index.html')



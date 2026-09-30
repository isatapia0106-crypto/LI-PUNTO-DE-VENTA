"""Explicitly register LI's six planned branches for one company."""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.main import Branch, CashRegister, engine

parser = argparse.ArgumentParser()
parser.add_argument('--empresa-id', type=int, required=True)
args = parser.parse_args()
if args.empresa_id < 1:
    raise SystemExit('Empresa inválida')
names = ('Zamora', 'Zacapu', 'Uruapan', '20 de Noviembre', 'Maravatío', 'CDMX')
with Session(engine) as db:
    for name in names:
        if not db.scalar(select(Branch.id).where(Branch.empresa_id == args.empresa_id, Branch.name == name)):
            db.add(Branch(empresa_id=args.empresa_id, name=name))
    db.flush()
    for branch in db.scalars(select(Branch).where(Branch.empresa_id == args.empresa_id)):
        if not db.scalar(select(CashRegister.id).where(CashRegister.branch_id == branch.id)):
            db.add(CashRegister(empresa_id=args.empresa_id, branch_id=branch.id, name='Caja 1'))
    db.commit()
print('Sucursales verificadas para la empresa indicada')


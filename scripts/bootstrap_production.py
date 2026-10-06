"""Create first production administrator and explicitly supplied branches after migrations."""
import argparse
import getpass
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    if os.getenv('APP_ENV')!='production':raise SystemExit('Sólo para entorno production migrado.')
    from backend.app.main import engine, Branch, User, UserBranch, password_hash
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    parser=argparse.ArgumentParser()
    parser.add_argument('--empresa',type=int,required=True)
    parser.add_argument('--username',required=True)
    parser.add_argument('--branch',action='append',required=True)
    args=parser.parse_args()
    if args.empresa<=0 or len(args.username)<3 or len(args.username)>80 or any(x.isspace() for x in args.username):raise SystemExit('Empresa o usuario inválidos.')
    names=[n.strip() for n in args.branch]
    if len(names)!=len(set(names)) or any(not n or len(n)>100 for n in names):raise SystemExit('Sucursales inválidas o duplicadas.')
    password=getpass.getpass('Contraseña de administración (12 a 200 caracteres): ')
    if not 12<=len(password)<=200 or password!=getpass.getpass('Confirma contraseña: '):raise SystemExit('Contraseña inválida o distinta.')
    with Session(engine) as db:
        if db.scalar(select(User.id).where(User.empresa_id==args.empresa)):raise SystemExit('La empresa ya tiene usuarios. Usa administración de usuarios.')
        branches=[]
        for name in names:
            branch=db.scalar(select(Branch).where(Branch.empresa_id==args.empresa,Branch.name==name))
            if not branch:branch=Branch(empresa_id=args.empresa,name=name);db.add(branch);db.flush()
            branches.append(branch)
        user=User(empresa_id=args.empresa,username=args.username,role='admin_general',password_hash=password_hash.hash(password))
        db.add(user);db.flush();db.add_all(UserBranch(user_id=user.id,branch_id=b.id) for b in branches)
        from backend.app.main import CashRegister
        for branch in branches:
            if not db.scalar(select(CashRegister.id).where(CashRegister.branch_id==branch.id)):
                db.add(CashRegister(empresa_id=args.empresa,branch_id=branch.id,name='Caja 1'))
        db.commit()
    print('Administrador y sucursales creados. No se cargaron datos demo.')

if __name__=='__main__':main()

"""Create the first administrator interactively; never writes a password to the repository."""
import getpass
import sys
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.main import Branch, Session, User, engine, password_hash

def main():
    username = input('Usuario administrador: ').strip()
    password = getpass.getpass('Contraseña (mínimo 12 caracteres): ')
    empresa_id = int(input('ID de empresa (demo: 1): ').strip())
    if len(username) < 3 or len(password) < 12 or empresa_id < 1:
        raise SystemExit('Usuario, contraseña o empresa inválidos')
    with Session(engine) as db:
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit('El usuario ya existe')
        if not db.scalar(select(Branch).where(Branch.empresa_id == empresa_id)):
            raise SystemExit('La empresa no tiene sucursales; crea primero las sucursales')
        db.add(User(username=username, empresa_id=empresa_id, password_hash=password_hash.hash(password), role='admin_general'))
        db.commit()
    print('Administrador creado')

if __name__ == '__main__':
    main()

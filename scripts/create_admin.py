"""Create the first administrator interactively; never writes a password to the repository."""
import getpass
import sys
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.main import Branch, Session, User, engine, password_hash

def main():
    while True:
        username = input('Usuario administrador (mínimo 3 caracteres): ').strip()
        if 3 <= len(username) <= 80 and not any(c.isspace() for c in username):
            break
        print('El usuario debe tener entre 3 y 80 caracteres, sin espacios. Ejemplo: isata.')
    while True:
        password = getpass.getpass('Contraseña (mínimo 12 caracteres; no se muestra al escribir): ')
        if not 12 <= len(password) <= 200:
            print('La contraseña debe tener entre 12 y 200 caracteres. Vuelve a escribirla.')
            continue
        confirmation = getpass.getpass('Confirma la contraseña: ')
        if password == confirmation:
            break
        print('Las contraseñas no coinciden. Vuelve a escribirlas.')
    while True:
        value = input('ID de empresa (Enter para demo 1): ').strip() or '1'
        if value.isdigit() and int(value) > 0:
            empresa_id = int(value)
            break
        print('El ID de empresa debe ser un número mayor que cero.')
    with Session(engine) as db:
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit('El usuario ya existe')
        if not db.scalar(select(Branch).where(Branch.empresa_id == empresa_id)):
            raise SystemExit('La empresa no tiene sucursales; crea primero las sucursales')
        db.add(User(username=username, empresa_id=empresa_id, password_hash=password_hash.hash(password), role='admin_general'))
        db.commit()
    print(f'Administrador creado. Usuario para entrar en el navegador: {username}')

if __name__ == '__main__':
    main()


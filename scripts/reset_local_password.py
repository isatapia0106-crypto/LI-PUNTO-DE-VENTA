"""Recover access to the local SQLite installation without importing the server."""
import getpass
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from pwdlib import PasswordHash

ROOT = Path(__file__).resolve().parents[1]

def recover(database, username, password, new_username=None):
    database = Path(database).resolve()
    if not database.is_file():
        raise ValueError('No existe pos.db. Inicia primero la aplicación.')
    if len(password) < 12 or len(password) > 200:
        raise ValueError('La contraseña debe tener entre 12 y 200 caracteres.')
    if new_username is not None and (not 3 <= len(new_username) <= 80 or any(c.isspace() for c in new_username)):
        raise ValueError('El nuevo usuario debe tener entre 3 y 80 caracteres, sin espacios.')
    with sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=15) as db:
        row = db.execute('SELECT id, active FROM users WHERE username = ?', (username,)).fetchone()
        if row is None:
            raise ValueError('No existe ese usuario. Copia el nombre exacto del listado.')
        if not row[1]:
            raise ValueError('El usuario está desactivado. Solicita su activación a administración.')
        if new_username and db.execute('SELECT id FROM users WHERE username = ? AND id != ?', (new_username, row[0])).fetchone():
            raise ValueError('El nuevo nombre ya pertenece a otro usuario.')
        hashed = PasswordHash.recommended().hash(password)
        backup = database.with_name(database.name + '.backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        with sqlite3.connect(backup) as target:
            db.backup(target)
        cursor = db.execute('UPDATE users SET username = ?, password_hash = ? WHERE id = ? AND username = ? AND active = 1',
                           (new_username or username, hashed, row[0], username))
        if cursor.rowcount != 1:
            raise ValueError('El usuario cambió durante la recuperación. Vuelve a consultar sus datos.')
        db.commit()
    return backup

def main():
    database = ROOT / 'pos.db'
    if not database.is_file():
        raise ValueError('No existe pos.db. Inicia primero la aplicación.')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        rows = db.execute('SELECT username, active FROM users ORDER BY username').fetchall()
    print('Usuarios locales (las comillas delimitan el nombre):')
    for name, active in rows:
        print(f'  {name!r}' + ('' if active else ' — desactivado'))
    if not rows:
        raise ValueError('No hay usuarios. Ejecuta INICIAR_LI_POS.bat para crear el administrador.')
    username = input('Usuario actual exacto: ').strip()
    new_username = input('Nuevo usuario sin espacios (Enter para conservar): ').strip() or None
    while True:
        password = getpass.getpass('Nueva contraseña (12 a 200 caracteres; escritura oculta): ')
        if not 12 <= len(password) <= 200:
            print('Debe tener entre 12 y 200 caracteres.')
            continue
        if password != getpass.getpass('Confirma la nueva contraseña: '):
            print('Las contraseñas no coinciden. Inténtalo de nuevo.')
            continue
        break
    if input('Escribe GUARDAR para aplicar el cambio: ').strip() != 'GUARDAR':
        print('Cancelado. No se modificaron los datos.')
        return
    backup = recover(database, username, password, new_username)
    print(f'Acceso actualizado. Usuario: {new_username or username}')
    print(f'Respaldo: {backup.name}')
    print('Reinicia la aplicación y entra en http://127.0.0.1:8000 con tus nuevos datos.')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, sqlite3.Error) as error:
        raise SystemExit(f'No se pudo recuperar el acceso: {error}')

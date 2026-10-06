"""Verified local SQLite backups. Uses no application imports or credentials."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {'branches', 'users', 'products', 'stock', 'sales', 'sale_items', 'cash_sessions', 'cash_movements'}


def readonly(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f'No existe el archivo: {path}')
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def inspect_database(path):
    with closing(readonly(path)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('La base no pasó la verificación de integridad.')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('La base tiene referencias inválidas.')
        names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED <= names:
            raise ValueError('No es una base reconocida de LI Punto de Venta.')
        versions = [x[0] for x in db.execute('SELECT version_num FROM alembic_version')] if 'alembic_version' in names else []
        return {'schema_versions': versions, 'counts': {name: db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ('users', 'products', 'sales')}}


def copy_database(source, destination, timeout=15):
    deadline = time.monotonic() + timeout
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError('La base permanece ocupada. Inténtalo después de detener el servidor.')
    with closing(readonly(source)) as origin, closing(sqlite3.connect(destination, timeout=3)) as target:
        origin.backup(target, pages=64, progress=progress, sleep=.1)


def create_backup(database, directory):
    database, directory = Path(database).resolve(), Path(directory).resolve()
    inspect_database(database)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    path = directory / f'LI-POS-{stamp}.db'
    partial = path.with_suffix('.partial')
    try:
        # A transactionally consistent SQLite snapshot includes committed WAL pages.
        copy_database(database, partial)
        info = inspect_database(partial)
        partial.rename(path)
        info.update({'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'filename': path.name,
                     'sha256': digest(path), 'bytes': path.stat().st_size})
        manifest = path.with_suffix('.json')
        manifest.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
        return path
    except Exception:
        partial.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        path.with_suffix('.json').unlink(missing_ok=True)
        raise


def verify_backup(path):
    path = Path(path).resolve()
    manifest = path.with_suffix('.json')
    if not manifest.is_file():
        raise ValueError('Falta el manifiesto .json del respaldo. Conserva los dos archivos juntos.')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('format') != 1 or data.get('filename') != path.name or data.get('sha256') != digest(path):
        raise ValueError('El respaldo no coincide con su manifiesto. No se restauró.')
    info = inspect_database(path)
    if info['schema_versions'] != data.get('schema_versions') or info['counts'] != data.get('counts'):
        raise ValueError('Los datos no coinciden con el manifiesto.')
    return data


def list_backups(directory):
    result = []
    for path in sorted(Path(directory).glob('LI-POS-*.db'), reverse=True):
        try:
            data = verify_backup(path)
            result.append({'path': str(path.resolve()), 'valid': True, **data})
        except (ValueError, OSError, sqlite3.Error) as error:
            result.append({'path': str(path.resolve()), 'valid': False, 'error': str(error)})
    return result


def restore_backup(backup, database, directory, *, server_stopped=False, confirmation='', check_port=True):
    backup, database = Path(backup).resolve(), Path(database).resolve()
    if not server_stopped or confirmation != 'RESTAURAR':
        raise ValueError('Detén el servidor y confirma RESTAURAR. La recuperación sustituye los datos actuales.')
    if backup == database:
        raise ValueError('El respaldo y la base destino deben ser diferentes.')
    if check_port:
        with socket.socket() as connection:
            connection.settimeout(.5)
            if connection.connect_ex(('127.0.0.1', 8000)) == 0:
                raise ValueError('El puerto 8000 está activo. Detén el servidor antes de restaurar.')
    verify_backup(backup)
    database.parent.mkdir(parents=True, exist_ok=True)
    # Preserve a verified recovery point before modifying any existing database.
    previous = create_backup(database, directory) if database.exists() else None
    # SQLite backup runs its own destination transaction. It respects journal/WAL
    # and does not unlink or replace a database file underneath an open handle.
    copy_database(backup, database)
    inspect_database(database)
    return previous


def main():
    parser = argparse.ArgumentParser(description='Respaldos locales verificados de LI Punto de Venta')
    parser.add_argument('--database', type=Path, default=ROOT / 'pos.db')
    parser.add_argument('--directory', type=Path, default=ROOT / 'backups')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('create')
    commands.add_parser('list')
    verify = commands.add_parser('verify'); verify.add_argument('backup', type=Path)
    restore = commands.add_parser('restore'); restore.add_argument('backup', type=Path)
    restore.add_argument('--server-stopped', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'create':
            print(f'Respaldo verificado: {create_backup(args.database, args.directory)}')
        elif args.command == 'list':
            rows = list_backups(args.directory)
            for row in rows:
                print(f"{'OK' if row['valid'] else 'INVÁLIDO'} | {row['path']} | {row.get('created_at', row.get('error'))}")
            if not rows: print('No hay respaldos en esta carpeta.')
        elif args.command == 'verify':
            data = verify_backup(args.backup)
            print(f"Respaldo válido. Fecha: {data['created_at']}. Ventas: {data['counts']['sales']}.")
        else:
            print('La restauración recupera la fecha del respaldo y sustituye los datos posteriores.')
            print(f'Destino: {args.database.resolve()}\nRespaldo: {args.backup.resolve()}')
            previous = restore_backup(args.backup, args.database, args.directory,
                server_stopped=args.server_stopped, confirmation=input('Escribe RESTAURAR para continuar: '))
            print(f'Restauración verificada. Copia anterior: {previous or "No había base anterior"}')
            print('Inicia INICIAR_LI_POS.bat para verificar y actualizar el esquema si hace falta.')
    except (ValueError, OSError, sqlite3.Error, TimeoutError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

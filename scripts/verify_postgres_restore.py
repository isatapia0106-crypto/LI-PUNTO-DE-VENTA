"""Compare all migrated table rows in an isolated restored PostgreSQL database.
Never restores over production. Keep the source quiescent during comparison.
"""
import argparse
import hashlib
import json
import os
from decimal import Decimal
from datetime import datetime, date
from sqlalchemy import create_engine, inspect, text


def fingerprint(url):
    if not url.startswith('postgresql'):
        raise ValueError('Se requiere PostgreSQL')
    engine = create_engine(url)
    result = {}
    try:
        with engine.connect() as db:
            # Stable reads within each database. Source must be stopped separately.
            db = db.execution_options(isolation_level='REPEATABLE READ')
            for name in sorted(inspect(db).get_table_names()):
                quoted = engine.dialect.identifier_preparer.quote(name)
                rows = db.execute(text('SELECT * FROM ' + quoted)).mappings()
                encoded = sorted(json.dumps(dict(row), sort_keys=True, default=str) for row in rows)
                result[name] = (len(encoded), hashlib.sha256('\n'.join(encoded).encode()).hexdigest())
    finally:
        engine.dispose()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--restored-url', required=True)
    args = parser.parse_args()
    source = os.environ['DATABASE_URL']
    if source == args.restored_url:
        raise SystemExit('La restauración debe estar en una base aislada diferente.')
    if fingerprint(source) != fingerprint(args.restored_url):
        raise SystemExit('La base restaurada no coincide. Conserva ambas bases para revisión.')
    print('Restauración verificada: todas las tablas y filas coinciden.')


if __name__ == '__main__':
    main()

"""Backup recovery without importing the app or touching any real database."""
from contextlib import closing
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import pytest
from scripts.local_backups import create_backup, verify_backup, restore_backup, list_backups


def database(path):
    with sqlite3.connect(path) as db:
        for table in ('branches','users','products','stock','sales','sale_items','cash_sessions','cash_movements'):
            db.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, value TEXT)')
        db.execute("INSERT INTO sales VALUES (1,'venta conservada')")
        db.execute('CREATE TABLE alembic_version (version_num TEXT)')
        db.execute("INSERT INTO alembic_version VALUES ('c5f902ad6718')")
    return path


def test_backup_restore_and_preserve_current_database(tmp_path):
    live=database(tmp_path/'pos.db');folder=tmp_path/'backups'
    backup=create_backup(live,folder);data=verify_backup(backup)
    assert data['counts']['sales']==1 and len(data['sha256'])==64
    with sqlite3.connect(live) as db:db.execute("INSERT INTO sales VALUES (2,'venta posterior')")
    before=restore_backup(backup,live,folder,server_stopped=True,confirmation='RESTAURAR',check_port=False)
    assert verify_backup(before)['counts']['sales']==2
    with sqlite3.connect(live) as db:assert db.execute('SELECT * FROM sales').fetchall()==[(1,'venta conservada')]
    assert len(list_backups(folder))==2 and all(r['valid'] for r in list_backups(folder))


def test_modified_or_unrecognized_backup_cannot_restore(tmp_path):
    live=database(tmp_path/'pos.db');backup=create_backup(live,tmp_path/'backups')
    with sqlite3.connect(backup) as db:db.execute("INSERT INTO sales VALUES (2,'alteración')")
    with pytest.raises(ValueError,match='manifiesto'):restore_backup(backup,live,tmp_path/'backups',server_stopped=True,confirmation='RESTAURAR',check_port=False)
    with sqlite3.connect(live) as db:assert db.execute('SELECT COUNT(*) FROM sales').fetchone()[0]==1
    assert not list_backups(tmp_path/'backups')[0]['valid']
    unrelated=tmp_path/'other.db'
    with sqlite3.connect(unrelated) as db:db.execute('CREATE TABLE unrelated (id INTEGER)')
    with pytest.raises(ValueError,match='reconocida'):create_backup(unrelated,tmp_path/'backups')


def test_restore_confirmation_and_missing_database(tmp_path):
    live=database(tmp_path/'pos.db');backup=create_backup(live,tmp_path/'backups')
    for stopped,confirmation in [(False,'RESTAURAR'),(True,'no')]:
        with pytest.raises(ValueError):restore_backup(backup,live,tmp_path/'backups',server_stopped=stopped,confirmation=confirmation,check_port=False)
    target=tmp_path/'recovered.db'
    assert restore_backup(backup,target,tmp_path/'backups',server_stopped=True,confirmation='RESTAURAR',check_port=False) is None
    with sqlite3.connect(target) as db:assert db.execute('SELECT COUNT(*) FROM sales').fetchone()[0]==1
    with pytest.raises(ValueError):create_backup(tmp_path/'missing.db',tmp_path/'backups')
    assert not (tmp_path/'missing.db').exists()


def test_wal_committed_data_and_independent_snapshot(tmp_path):
    live=database(tmp_path/'pos.db')
    with closing(sqlite3.connect(live)) as db:
        db.execute('PRAGMA journal_mode=WAL');db.execute("INSERT INTO sales VALUES (2,'WAL confirmado')");db.commit()
        backup=create_backup(live,tmp_path/'backups')
        db.execute("INSERT INTO sales VALUES (3,'todavía sin confirmar')")
        assert verify_backup(backup)['counts']['sales']==2
        db.rollback()
    with sqlite3.connect(backup) as db:assert db.execute('SELECT value FROM sales WHERE id=2').fetchone()[0]=='WAL confirmado'


def test_invalid_foreign_keys_and_corruption_are_rejected(tmp_path):
    live=database(tmp_path/'pos.db')
    with sqlite3.connect(live) as db:
        db.execute('CREATE TABLE invalid_links (user_id INTEGER REFERENCES users(id))')
        db.execute('INSERT INTO invalid_links VALUES (99)')
    with pytest.raises(ValueError,match='referencias'):create_backup(live,tmp_path/'backups')
    corrupt=tmp_path/'corrupt.db';corrupt.write_bytes(b'not a database')
    with pytest.raises(sqlite3.Error):create_backup(corrupt,tmp_path/'backups')


def test_cli_create_list_verify(tmp_path):
    live=database(tmp_path/'pos.db');folder=tmp_path/'backups'
    script=Path(__file__).resolve().parents[1]/'scripts/local_backups.py'
    def run(*args):return subprocess.run([sys.executable,str(script),'--database',str(live),'--directory',str(folder),*args],capture_output=True,text=True)
    assert run('create').returncode==0
    backup=next(folder.glob('*.db'));assert run('verify',str(backup)).returncode==0
    assert 'OK' in run('list').stdout
    backup.with_suffix('.json').unlink()
    assert run('verify',str(backup)).returncode==1

def test_running_server_blocks_restore_before_preservation(tmp_path, monkeypatch):
    import scripts.local_backups as module
    live=database(tmp_path/'pos.db');folder=tmp_path/'backups';backup=create_backup(live,folder)
    class ActiveSocket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def settimeout(self,value):pass
        def connect_ex(self,address):return 0
    monkeypatch.setattr(module.socket,'socket',lambda:ActiveSocket())
    with pytest.raises(ValueError,match='8000'):restore_backup(backup,live,folder,server_stopped=True,confirmation='RESTAURAR')
    assert len(list(folder.glob('*.db')))==1


def test_failed_copy_cleans_partial_and_retains_source(tmp_path, monkeypatch):
    import scripts.local_backups as module
    live=database(tmp_path/'pos.db');folder=tmp_path/'backups'
    def fail(source,target):
        Path(target).write_bytes(b'incomplete')
        raise TimeoutError('busy')
    monkeypatch.setattr(module,'copy_database',fail)
    with pytest.raises(TimeoutError):create_backup(live,folder)
    assert not list(folder.iterdir())
    with sqlite3.connect(live) as db:assert db.execute('SELECT COUNT(*) FROM sales').fetchone()[0]==1

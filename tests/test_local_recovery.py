import sqlite3
import tempfile
import unittest
from pathlib import Path
from pwdlib import PasswordHash
from scripts.reset_local_password import recover

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'pos.db'
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, active INTEGER)')
            c.executemany('INSERT INTO users VALUES (?, ?, ?, ?)', [(1, 'e isata', 'old', 1), (2, 'other', 'untouched', 1), (3, 'inactive', 'old', 0)])
    def rows(self):
        with sqlite3.connect(self.db) as c:
            return c.execute('SELECT * FROM users ORDER BY id').fetchall()
    def test_reset_rename_and_backup(self):
        backup = recover(self.db, 'e isata', 'Local-Test-Password!', 'isata')
        rows = self.rows()
        self.assertEqual(rows[0][0:2], (1, 'isata'))
        self.assertTrue(PasswordHash.recommended().verify('Local-Test-Password!', rows[0][2]))
        self.assertFalse(PasswordHash.recommended().verify('wrong', rows[0][2]))
        self.assertEqual(rows[1], (2, 'other', 'untouched', 1))
        with sqlite3.connect(backup) as c:
            self.assertEqual(c.execute('SELECT username, password_hash FROM users WHERE id=1').fetchone(), ('e isata', 'old'))
    def test_invalid_changes_do_not_write(self):
        original = self.rows()
        for username, password, new_name in [('missing','Local-Test-Password!',None), ('inactive','Local-Test-Password!',None), ('e isata','short',None), ('e isata','Local-Test-Password!','other'), ('e isata','Local-Test-Password!','bad name')]:
            with self.subTest(username=username, new_name=new_name):
                with self.assertRaises(ValueError):
                    recover(self.db, username, password, new_name)
                self.assertEqual(self.rows(), original)
        self.assertEqual(list(self.db.parent.glob('*.backup-*')), [])
    def test_missing_database_not_created(self):
        missing = self.db.parent / 'missing.db'
        with self.assertRaises(ValueError):
            recover(missing, 'isata', 'Local-Test-Password!')
        self.assertFalse(missing.exists())

if __name__ == '__main__':
    unittest.main()

"""Single-instance durable queue and encrypted credential storage."""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from cryptography.fernet import Fernet


def data_dir():
    return Path(os.getenv('DATA_DIR', '/tmp/gameclip-data'))


def durable():
    return os.getenv('PERSISTENT_STORAGE_CONFIRMED', 'false').lower() == 'true'


@contextmanager
def db():
    data_dir().mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(data_dir() / 'publisher.db', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS accounts(platform TEXT PRIMARY KEY, label TEXT, secret TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS states(id TEXT PRIMARY KEY, platform TEXT, expires REAL);
    CREATE TABLE IF NOT EXISTS clips(id TEXT PRIMARY KEY, name TEXT, path TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, clip_id TEXT REFERENCES clips(id), platform TEXT,
      account_id TEXT, title TEXT, caption TEXT, privacy TEXT, made_for_kids INTEGER DEFAULT 0, due REAL, status TEXT,
      remote_id TEXT, error TEXT, updated REAL, UNIQUE(clip_id,platform));
    ''')
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def cipher():
    key = os.getenv('TOKEN_ENCRYPTION_KEY', '')
    if not key:
        raise ValueError('TOKEN_ENCRYPTION_KEY must be configured')
    return Fernet(key.encode())


def save_account(platform, label, token):
    secret = cipher().encrypt(json.dumps(token).encode()).decode()
    with db() as c:
        c.execute('INSERT OR REPLACE INTO accounts VALUES(?,?,?)', (platform, label, secret))


def account(platform):
    with db() as c:
        row = c.execute('SELECT * FROM accounts WHERE platform=?', (platform,)).fetchone()
    return json.loads(cipher().decrypt(row['secret'].encode())) if row else None


def job_update(job_id, **values):
    allowed = {'status', 'remote_id', 'error', 'due'}
    assert values.keys() <= allowed
    values['updated'] = time.time()
    with db() as c:
        c.execute('UPDATE jobs SET '+','.join(f'{k}=?' for k in values)+' WHERE id=?', (*values.values(), job_id))

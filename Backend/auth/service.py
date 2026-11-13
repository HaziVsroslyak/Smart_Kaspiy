"""Opaque sessions, adaptive password hashes and transactional role checks."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException

from auth.models import Actor, Role, User
from storage import Database

PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))
COOKIE_NAME = '__Host-session'


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def session_csrf(token: str) -> str:
    return hmac.new(token.encode(),b'smart-caspian-csrf-v1',hashlib.sha256).hexdigest()


def normalized(value: str) -> str:
    return value.strip().casefold()


def verify_password(encoded: str, password: str) -> bool:
    try:
        return PASSWORDS.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def user_from_row(row: tuple) -> User:
    return User(id=row[0], login=row[1], email=row[2], role=row[3], status=row[4], must_change_password=bool(row[5]))


USER_COLUMNS = 'id, login, email, role, status, must_change_password'


def current_actor(db: sqlite3.Connection, actor: Actor, *, writing: bool = False) -> User:
    """Recheck access in the same transaction as the protected operation."""
    now = time.time()
    row = db.execute(
        f'SELECT {", ".join("u." + c.strip() for c in USER_COLUMNS.split(","))} '
        'FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_digest=? '
        'AND u.id=? AND u.status=\'active\' AND s.revoked_at IS NULL '
        'AND s.expires_at>? AND s.last_seen_at>?',
        (actor.session_digest, actor.user.id, now, now - 1800),
    ).fetchone()
    if row is None:
        raise HTTPException(401, 'Session expired or revoked.')
    user = user_from_row(row)
    if user.must_change_password:
        raise HTTPException(403, 'Password change required.')
    if writing and user.role == 'admin':
        raise HTTPException(403, 'Administrators have read-only access to voyages.')
    return user


def audit(db: sqlite3.Connection, actor_id: str, action: str, subject: str, detail: dict[str, object] | None = None) -> None:
    db.execute('INSERT INTO audit_events(id,at_utc,actor_ref,action,subject_ref,detail_json) VALUES (?,?,?,?,?,?)',
               (str(uuid4()), time.time(), actor_id, action, subject, json.dumps(detail or {}, ensure_ascii=False)))


class AuthService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _new_session(self, db: sqlite3.Connection, user_id: str | None) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = session_csrf(token)
        now = time.time()
        db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,NULL)',
                   (digest(token), user_id, digest(csrf), now, now, now + (43200 if user_id else 600), int(user_id is None)))
        return token, csrf

    def bootstrap(self, token: str | None) -> tuple[str, str]:
        now = time.time()
        with self.database.transaction() as db:
            db.execute('DELETE FROM sessions WHERE expires_at<=? OR (user_id IS NULL AND created_at<?)', (now, now-600))
            if token:
                row = db.execute('SELECT user_id FROM sessions WHERE token_digest=? AND revoked_at IS NULL AND expires_at>? AND last_seen_at>?',
                                 (digest(token), now, now-1800)).fetchone()
                if row is not None:
                    if row[0] is not None:
                        active = db.execute("SELECT status FROM users WHERE id=?", (row[0],)).fetchone()
                        if active != ('active',):
                            db.execute('DELETE FROM sessions WHERE token_digest=?',(digest(token),))
                            return self._new_session(db,None)
                    csrf = session_csrf(token)
                    db.execute('UPDATE sessions SET csrf_digest=? WHERE token_digest=?', (digest(csrf), digest(token)))
                    return token, csrf
            return self._new_session(db, None)

    def check_csrf(self, token: str | None, csrf: str | None) -> None:
        if not token or not csrf:
            raise HTTPException(403, 'CSRF token required.')
        with self.database.connect() as db:
            row = db.execute('SELECT csrf_digest FROM sessions WHERE token_digest=? AND revoked_at IS NULL AND expires_at>? AND last_seen_at>?',
                             (digest(token), time.time(), time.time()-1800)).fetchone()
        if row is None or not secrets.compare_digest(row[0], digest(csrf)):
            raise HTTPException(403, 'Invalid CSRF token.')

    def authenticate(self, token: str | None, *, allow_password_change: bool = False) -> Actor:
        if not token:
            raise HTTPException(401, 'Authentication required.')
        now = time.time()
        with self.database.transaction() as db:
            row = db.execute(f'SELECT {", ".join("u." + c.strip() for c in USER_COLUMNS.split(","))} FROM users u '
                             'JOIN sessions s ON s.user_id=u.id WHERE s.token_digest=? AND u.status=\'active\' '
                             'AND s.revoked_at IS NULL AND s.expires_at>? AND s.last_seen_at>?',
                             (digest(token), now, now-1800)).fetchone()
            if row is None:
                raise HTTPException(401, 'Session expired or revoked.')
            user = user_from_row(row)
            if user.must_change_password and not allow_password_change:
                raise HTTPException(403, 'Password change required.')
            db.execute('UPDATE sessions SET last_seen_at=? WHERE token_digest=?', (now, digest(token)))
        return Actor(user, digest(token))

    def login(self, token: str, identity: str, password: str, source: str) -> tuple[User, str, str]:
        key = normalized(identity)
        now = time.time()
        keys = (digest('identity:' + key), digest('source:' + source))
        with self.database.transaction() as db:
            db.execute('DELETE FROM login_attempts WHERE window_start<?', (now-900,))
            for index, bucket in enumerate(keys):
                row = db.execute('SELECT failures FROM login_attempts WHERE bucket=?', (bucket,)).fetchone()
                if row and row[0] >= (10 if index == 0 else 50):
                    raise HTTPException(429, 'Too many login attempts. Try again later.')
            row = db.execute(f'SELECT {USER_COLUMNS}, password_hash FROM users WHERE login_normalized=? OR email_normalized=?', (key,key)).fetchone()
        # Argon2 runs outside SQLite's writer lock.
        valid = verify_password(row[6] if row else _DUMMY_HASH, password)
        with self.database.transaction() as db:
            if not valid or row is None or row[4] != 'active':
                for bucket in keys:
                    db.execute('INSERT INTO login_attempts VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET failures=failures+1', (bucket, now))
                failure = True
            else:
                latest = db.execute(f'SELECT {USER_COLUMNS}, password_hash FROM users WHERE id=?', (row[0],)).fetchone()
                if latest is None or latest[4] != 'active' or latest[6] != row[6]:
                    raise HTTPException(401, 'Invalid login or password.')
                preauth = db.execute('SELECT user_id FROM sessions WHERE token_digest=? AND revoked_at IS NULL AND expires_at>?', (digest(token), now)).fetchone()
                if preauth is None:
                    raise HTTPException(403, 'Login session expired.')
                db.execute('DELETE FROM sessions WHERE token_digest=?', (digest(token),))
                new_token, csrf = self._new_session(db, row[0])
                db.execute('DELETE FROM login_attempts WHERE bucket=?', (keys[0],))
                audit(db, row[0], 'login', row[0])
                failure = False
        if failure:
            raise HTTPException(401, 'Invalid login or password.')
        return user_from_row(latest), new_token, csrf

    def logout(self, actor: Actor) -> None:
        with self.database.transaction() as db:
            db.execute('UPDATE sessions SET revoked_at=? WHERE token_digest=?', (time.time(), actor.session_digest))
            audit(db, actor.user.id, 'logout', actor.user.id)

    def change_password(self, actor: Actor, current: str, new: str) -> tuple[User, str, str]:
        with self.database.connect() as db:
            row = db.execute('SELECT password_hash FROM users WHERE id=?', (actor.user.id,)).fetchone()
        if row is None or not verify_password(row[0], current):
            raise HTTPException(400, 'Current password is incorrect.')
        if current == new:
            raise HTTPException(422, 'New password must differ from the current password.')
        encoded = PASSWORDS.hash(new)
        with self.database.transaction() as db:
            self._allow_actor(db, actor, password_change=True)
            result = db.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=? AND password_hash=?', (encoded, actor.user.id, row[0]))
            if result.rowcount != 1:
                raise HTTPException(409, 'Password was changed; sign in again.')
            db.execute('UPDATE sessions SET revoked_at=? WHERE user_id=?', (time.time(), actor.user.id))
            token, csrf = self._new_session(db, actor.user.id)
            audit(db, actor.user.id, 'password_changed', actor.user.id)
            user = user_from_row(db.execute(f'SELECT {USER_COLUMNS} FROM users WHERE id=?', (actor.user.id,)).fetchone())
        return user, token, csrf

    def _allow_actor(self, db: sqlite3.Connection, actor: Actor, *, password_change: bool = False, root: bool = False) -> User:
        if password_change:
            # Forced password changes still need a live authenticated session.
            row = db.execute('SELECT 1 FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_digest=? AND u.id=? '
                             'AND u.status=\'active\' AND s.revoked_at IS NULL AND s.expires_at>? AND s.last_seen_at>?',
                             (actor.session_digest, actor.user.id, time.time(), time.time()-1800)).fetchone()
            if not row:
                raise HTTPException(401, 'Session expired or revoked.')
            return actor.user
        user = current_actor(db, actor)
        if user.role not in (('root',) if root else ('admin', 'root')):
            raise HTTPException(403, 'Insufficient permissions.')
        return user

    def create_user(self, login: str, email: str, password: str, *, actor: Actor | None = None, bootstrap: bool = False) -> User:
        login, email = login.strip(), email.strip()
        if not 3 <= len(login) <= 100 or not 3 <= len(email) <= 254 or '@' not in email or any(c.isspace() for c in login+email):
            raise HTTPException(422, 'A login without spaces and a valid email are required.')
        if not 12 <= len(password) <= 128:
            raise HTTPException(422, 'Password must contain 12–128 characters.')
        encoded, identity = PASSWORDS.hash(password), str(uuid4())
        with self.database.transaction() as db:
            if bootstrap:
                if actor is not None or db.execute("SELECT 1 FROM users WHERE role='root'").fetchone():
                    raise HTTPException(409, 'Root is already initialized.')
            elif actor is not None:
                self._allow_actor(db, actor)
            else:
                raise HTTPException(403, 'Administrator required.')
            names = (normalized(login), normalized(email))
            if names[0] == names[1] or db.execute('SELECT 1 FROM users WHERE login_normalized IN (?,?) OR email_normalized IN (?,?)', names+names).fetchone():
                raise HTTPException(409, 'Login or email is already used.')
            role = 'root' if bootstrap else 'logistician'
            db.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (identity,login,email,names[0],names[1],encoded,role,'active',int(not bootstrap),time.time()))
            audit(db, actor.user.id if actor else identity, 'root_bootstrap' if bootstrap else 'user_created', identity)
            return user_from_row(db.execute(f'SELECT {USER_COLUMNS} FROM users WHERE id=?', (identity,)).fetchone())

    def list_users(self, actor: Actor) -> list[User]:
        with self.database.connect() as db:
            self._allow_actor(db, actor)
            return [user_from_row(row) for row in db.execute(f'SELECT {USER_COLUMNS} FROM users ORDER BY created_at')]

    def manage_user(self, actor: Actor, identity: str, action: str, role: Role | None = None) -> tuple[User, str | None]:
        temporary = secrets.token_urlsafe(18) if action == 'password_reset' else None
        encoded = PASSWORDS.hash(temporary) if temporary else None
        with self.database.transaction() as db:
            authority = self._allow_actor(db, actor, root=action in ('role', 'unfreeze'))
            if identity==authority.id and action=='password_reset':
                raise HTTPException(409,'Use the password change endpoint for your own account.')
            row = db.execute(f'SELECT {USER_COLUMNS} FROM users WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise HTTPException(404, 'User not found.')
            target = user_from_row(row)
            if authority.role == 'admin' and target.role != 'logistician':
                raise HTTPException(403, 'Administrators can manage only logisticians.')
            if target.role == 'root' and target.status == 'active' and (action == 'freeze' or (action == 'role' and role != 'root')):
                if db.execute("SELECT count(*) FROM users WHERE role='root' AND status='active'").fetchone()[0] <= 1:
                    raise HTTPException(409, 'The last active root cannot be disabled or demoted.')
            if action == 'freeze':
                db.execute("UPDATE users SET status='frozen' WHERE id=?", (identity,))
            elif action == 'unfreeze':
                db.execute("UPDATE users SET status='active' WHERE id=?", (identity,))
            elif action == 'role' and role is not None:
                db.execute('UPDATE users SET role=? WHERE id=?', (role,identity))
            elif action == 'password_reset':
                db.execute('UPDATE users SET password_hash=?,must_change_password=1 WHERE id=?', (encoded,identity))
            else:
                raise ValueError('Unsupported user action')
            db.execute('UPDATE sessions SET revoked_at=? WHERE user_id=?', (time.time(),identity))
            audit(db, authority.id, action, identity, {'role':role} if action == 'role' else {})
            return user_from_row(db.execute(f'SELECT {USER_COLUMNS} FROM users WHERE id=?', (identity,)).fetchone()), temporary

"""Authorization boundary checks use real opaque sessions, never bypass flags."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.application import create_app
from api.config import Settings


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.app=create_app(Settings(database_path=Path(self.folder.name)/'security.db'))
        self.training=patch('api.application.build_resources',return_value=object())
        self.training.start()
        self.client=TestClient(self.app,base_url='https://localhost')
        self.client.__enter__()
        self.root=self.app.state.auth.create_user('root','root@example.com','RootPassword123!',bootstrap=True)

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.training.stop()
        self.folder.cleanup()

    def login(self,identity='root',password='RootPassword123!'):
        csrf=self.client.get('/api/v1/auth/csrf').json()['csrf_token']
        response=self.client.post('/api/v1/auth/login',json={'identity':identity,'password':password},headers={'Origin':'https://localhost','X-CSRF-Token':csrf})
        self.assertEqual(response.status_code,200,response.text)
        return {'Origin':'https://localhost','X-CSRF-Token':response.json()['csrf_token']}

    def test_anonymous_inventory_and_csrf(self):
        self.assertEqual(self.client.get('/healthz').status_code,200)
        for path in ('/docs','/openapi.json','/api/v1/health','/api/v1/weather/forecast','/api/v1/demo/scenarios','/api/v1/voyages'):
            self.assertEqual(self.client.get(path).status_code,401,path)
        self.assertEqual(self.client.post('/api/v1/auth/login',json={'identity':'root','password':'RootPassword123!'}).status_code,403)
        headers=self.login()
        self.assertEqual(self.client.get('/api/v1/auth/me').json()['role'],'root')
        headers['Origin']='https://evil.example'
        self.assertEqual(self.client.post('/api/v1/auth/logout',headers=headers).status_code,403)

    def test_forced_password_and_freeze(self):
        headers=self.login()
        response=self.client.post('/api/v1/admin/users',json={'login':'logistician','email':'log@example.com','password':'TemporaryPassword123!'},headers=headers)
        self.assertEqual(response.status_code,201,response.text)
        identity=response.json()['id']
        rootcookies=dict(self.client.cookies)
        headers=self.login('logistician','TemporaryPassword123!')
        self.assertTrue(self.client.get('/api/v1/auth/me').json()['must_change_password'])
        self.assertEqual(self.client.get('/api/v1/voyages').status_code,403)
        changed=self.client.post('/api/v1/auth/password',headers=headers,json={'current_password':'TemporaryPassword123!','new_password':'NewLogisticianPassword123!'})
        self.assertEqual(changed.status_code,200,changed.text)
        usercookies=dict(self.client.cookies)
        self.client.cookies.clear()
        self.client.cookies.update(rootcookies)
        headers=self.login()
        self.assertEqual(self.client.post(f'/api/v1/admin/users/{identity}/freeze',headers=headers).status_code,200)
        self.client.cookies.clear()
        self.client.cookies.update(usercookies)
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code,401)

    def test_last_root_and_admin_readonly(self):
        headers=self.login()
        self.assertEqual(self.client.post(f'/api/v1/admin/users/{self.root.id}/freeze',headers=headers).status_code,409)
        self.assertEqual(self.client.patch(f'/api/v1/root/users/{self.root.id}/role',headers=headers,json={'role':'admin'}).status_code,409)
        with self.app.state.auth.database.transaction() as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertNotIn('RootPassword123!',str(db.execute('SELECT * FROM audit_events').fetchall()))

    def test_ownership_transfer_admin_and_logout(self):
        rootheaders=self.login()
        identities=[]
        for name in ('alice','bravo','admin'):
            response=self.client.post('/api/v1/admin/users',headers=rootheaders,json={'login':name,'email':name+'@example.com','password':'InitialPassword123!'})
            self.assertEqual(response.status_code,201,response.text)
            identities.append(response.json()['id'])
        with self.app.state.auth.database.transaction() as db:
            db.execute('UPDATE users SET must_change_password=0')
            db.execute("UPDATE users SET role='admin' WHERE id=?",(identities[2],))
            db.execute("INSERT INTO voyages VALUES ('voyage','{}','{}','{}','{}',0)")
            db.execute("INSERT INTO resource_owners(resource_type,resource_id,owner_id) VALUES ('voyage','voyage',?)",(identities[0],))
        self.login('bravo','InitialPassword123!')
        self.assertEqual(self.client.get('/api/v1/voyages').json(),[])
        self.assertEqual(self.client.get('/api/v1/voyages/voyage').status_code,404)
        adminheaders=self.login('admin','InitialPassword123!')
        self.assertEqual(len(self.client.get('/api/v1/voyages').json()),1)
        self.assertEqual(self.client.post('/api/v1/voyages',headers=adminheaders,json={}).status_code,403)
        self.assertEqual(self.client.get('/api/v1/root/audit').status_code,403)
        self.assertEqual(self.client.post('/api/v1/root/voyages/voyage/transfer',headers=adminheaders,json={'destination_user_id':identities[1],'expected_ownership_revision':0}).status_code,403)
        headers=self.login()
        response=self.client.post('/api/v1/root/voyages/voyage/transfer',headers=headers,json={'destination_user_id':identities[1],'expected_ownership_revision':0})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['ownership_revision'],1)
        self.assertEqual(self.client.post('/api/v1/root/voyages/voyage/transfer',headers=headers,json={'destination_user_id':identities[0],'expected_ownership_revision':0}).status_code,409)
        self.login('bravo','InitialPassword123!')
        original=self.app.state.voyages.list_voyages
        def transfer_after_read():
            rows=original()
            with self.app.state.auth.database.transaction() as db:
                db.execute("UPDATE resource_owners SET owner_id=?,ownership_revision=ownership_revision+1 WHERE resource_type='voyage' AND resource_id='voyage'",(identities[0],))
            return rows
        with patch.object(self.app.state.voyages,'list_voyages',side_effect=transfer_after_read):
            self.assertEqual(self.client.get('/api/v1/voyages').status_code,404)
        with self.app.state.auth.database.transaction() as db:
            db.execute("UPDATE resource_owners SET owner_id=? WHERE resource_type='voyage' AND resource_id='voyage'",(identities[1],))
        headers=self.login('alice','InitialPassword123!')
        self.assertEqual(self.client.get('/api/v1/voyages').json(),[])
        self.assertEqual(self.client.post('/api/v1/auth/logout',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code,401)

    def test_csrf_bootstrap_stable_and_expired_session(self):
        headers=self.login()
        self.assertEqual(self.client.get('/api/v1/auth/csrf').json()['csrf_token'],headers['X-CSRF-Token'])
        self.assertEqual(self.client.post(f'/api/v1/admin/users/{self.root.id}/password-reset',headers=headers).status_code,409)
        with self.app.state.auth.database.transaction() as db:
            db.execute('UPDATE sessions SET expires_at=0')
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code,401)

    def test_reset_revokes_sessions_and_requires_new_password(self):
        headers=self.login()
        user=self.client.post('/api/v1/admin/users',headers=headers,json={'login':'resetuser','email':'reset@example.com','password':'InitialPassword123!'}).json()
        with self.app.state.auth.database.transaction() as db:
            db.execute('UPDATE users SET must_change_password=0 WHERE id=?',(user['id'],))
        self.login('resetuser','InitialPassword123!')
        previous=dict(self.client.cookies)
        headers=self.login()
        reset=self.client.post(f"/api/v1/admin/users/{user['id']}/password-reset",headers=headers)
        self.assertEqual(reset.status_code,200,reset.text)
        temporary=reset.json()['temporary_password']
        self.client.cookies.clear();self.client.cookies.update(previous)
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code,401)
        self.login('resetuser',temporary)
        self.assertTrue(self.client.get('/api/v1/auth/me').json()['must_change_password'])
        with self.app.state.auth.database.connect() as db:
            stored=db.execute('SELECT password_hash FROM users WHERE id=?',(user['id'],)).fetchone()[0]
            self.assertTrue(stored.startswith('$argon2id$'))
            self.assertNotIn(temporary,str(db.execute('SELECT * FROM audit_events').fetchall()))

    def test_login_rate_limit_and_cookie_flags(self):
        bootstrap=self.client.get('/api/v1/auth/csrf')
        cookie=bootstrap.headers['set-cookie']
        for flag in ('Secure','HttpOnly','SameSite=lax','Path=/'):
            self.assertIn(flag,cookie)
        headers={'Origin':'https://localhost','X-CSRF-Token':bootstrap.json()['csrf_token']}
        for _ in range(10):
            response=self.client.post('/api/v1/auth/login',headers=headers,json={'identity':'root','password':'incorrect'})
            self.assertEqual(response.status_code,401)
        self.assertEqual(self.client.post('/api/v1/auth/login',headers=headers,json={'identity':'root','password':'incorrect'}).status_code,429)

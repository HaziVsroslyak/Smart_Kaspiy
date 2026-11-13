"""Real cookie login fixture for legacy business integration checks."""
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from auth.service import AuthService
from voyage_store import VoyageStore


class SecureClient(TestClient):
    def __init__(self, app, **kwargs):
        super().__init__(app,base_url='https://localhost',**kwargs)
        self.csrf=''
        self.folder=tempfile.TemporaryDirectory()

    def __enter__(self):
        super().__enter__()
        self.app.state.voyages=VoyageStore(Path(self.folder.name)/'test.db')
        self.app.state.auth=AuthService(self.app.state.voyages.database)
        self.app.state.auth.create_user('fixture','fixture@example.com','FixturePassword123!',bootstrap=True)
        self.csrf=self.get('/api/v1/auth/csrf').json()['csrf_token']
        response=self.post('/api/v1/auth/login',json={'identity':'fixture','password':'FixturePassword123!'})
        assert response.status_code==200,response.text
        self.csrf=response.json()['csrf_token']
        return self

    def request(self,method,url,**kwargs):
        if method.upper() not in ('GET','HEAD','OPTIONS'):
            kwargs['headers']={'Origin':'https://localhost','X-CSRF-Token':self.csrf,**dict(kwargs.get('headers') or {})}
        return super().request(method,url,**kwargs)

    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.folder.cleanup()

"""Fail-closed authentication for every application endpoint."""
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from auth.context import request_actor, accessed_resources
from auth.service import COOKIE_NAME


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path, method = request.url.path, request.method
        public = (method, path) in {('GET','/healthz'),('GET','/api/v1/auth/csrf'),('POST','/api/v1/auth/login')}
        state = request.app.state
        if getattr(state, 'auth', None) is None:
            return JSONResponse({'detail':'Identity service is not initialized.'},status_code=503)
        token = None
        resources=[]
        resource_token=accessed_resources.set(resources)
        try:
            if path != '/healthz' and method not in ('GET','HEAD','OPTIONS'):
                origin = request.headers.get('origin')
                if origin not in state.settings.cors_origins:
                    raise HTTPException(403,'Invalid request origin.')
                await run_in_threadpool(state.auth.check_csrf, request.cookies.get(COOKIE_NAME), request.headers.get('x-csrf-token'))
            actor = None
            if not public:
                actor = await run_in_threadpool(state.auth.authenticate,request.cookies.get(COOKIE_NAME),allow_password_change=path in ('/api/v1/auth/me','/api/v1/auth/password','/api/v1/auth/logout'))
                request.state.actor = actor
                token = request_actor.set(actor)
                if actor.user.role == 'admin' and method not in ('GET','HEAD','OPTIONS') and not path.startswith(('/api/v1/auth/','/api/v1/admin/')):
                    raise HTTPException(403,'Administrators have read-only access to voyages.')
            response = await call_next(request)
            if actor is not None and path not in ('/api/v1/auth/logout','/api/v1/auth/password') and response.status_code < 400:
                await run_in_threadpool(state.auth.authenticate,request.cookies.get(COOKIE_NAME),allow_password_change=path=='/api/v1/auth/me')
                await run_in_threadpool(state.voyages.recheck_resources,resources)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except HTTPException as exc:
            return JSONResponse({'detail':exc.detail},status_code=exc.status_code,headers={'Cache-Control':'no-store'})
        finally:
            if token is not None:
                request_actor.reset(token)
            accessed_resources.reset(resource_token)

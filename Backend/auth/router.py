"""Identity and administrative routes; no password hashes are serialized."""
from fastapi import APIRouter, Request, Response
from auth.models import CreateUser, LoginRequest, PasswordChange, RoleChange, TransferRequest
from auth.service import COOKIE_NAME

router = APIRouter()


def session_response(response: Response, token: str, csrf: str) -> None:
    response.set_cookie(COOKIE_NAME,token,secure=True,httponly=True,samesite='lax',path='/',max_age=43200)
    response.headers['Cache-Control']='no-store'


@router.get('/healthz')
def healthz():
    return {'status':'ok'}


@router.get('/api/v1/auth/csrf')
def csrf(request: Request,response: Response):
    token,value=request.app.state.auth.bootstrap(request.cookies.get(COOKIE_NAME))
    session_response(response,token,value)
    return {'csrf_token':value}


@router.post('/api/v1/auth/login')
def login(payload: LoginRequest,request: Request,response: Response):
    user,token,csrf=request.app.state.auth.login(request.cookies[COOKIE_NAME],payload.identity,payload.password,request.client.host if request.client else 'unknown')
    session_response(response,token,csrf)
    return {'user':user,'csrf_token':csrf}


@router.get('/api/v1/auth/me')
def me(request: Request):
    return request.state.actor.user


@router.post('/api/v1/auth/logout')
def logout(request: Request,response: Response):
    request.app.state.auth.logout(request.state.actor)
    response.delete_cookie(COOKIE_NAME,path='/',secure=True,httponly=True,samesite='lax')
    return {'status':'ok'}


@router.post('/api/v1/auth/password')
def password(payload: PasswordChange,request: Request,response: Response):
    user,token,csrf=request.app.state.auth.change_password(request.state.actor,payload.current_password,payload.new_password)
    session_response(response,token,csrf)
    return {'user':user,'csrf_token':csrf}


@router.get('/api/v1/admin/users')
def users(request: Request):
    return request.app.state.auth.list_users(request.state.actor)


@router.post('/api/v1/admin/users',status_code=201)
def create_user(payload: CreateUser,request: Request):
    return request.app.state.auth.create_user(payload.login,payload.email,payload.password,actor=request.state.actor)


@router.post('/api/v1/admin/users/{user_id}/freeze')
def freeze(user_id: str,request: Request):
    return request.app.state.auth.manage_user(request.state.actor,user_id,'freeze')[0]


@router.post('/api/v1/root/users/{user_id}/unfreeze')
def unfreeze(user_id: str,request: Request):
    return request.app.state.auth.manage_user(request.state.actor,user_id,'unfreeze')[0]


@router.post('/api/v1/admin/users/{user_id}/password-reset')
def reset(user_id: str,request: Request):
    user,temporary=request.app.state.auth.manage_user(request.state.actor,user_id,'password_reset')
    return {'user':user,'temporary_password':temporary}


@router.patch('/api/v1/root/users/{user_id}/role')
def role(user_id: str,payload: RoleChange,request: Request):
    return request.app.state.auth.manage_user(request.state.actor,user_id,'role',payload.role)[0]


@router.get('/api/v1/root/audit')
def events(request: Request):
    service=request.app.state.auth
    with service.database.connect() as db:
        service._allow_actor(db,request.state.actor,root=True)
        return [dict(zip(('id','at_utc','actor_ref','action','subject_ref','detail_json'),row)) for row in db.execute('SELECT * FROM audit_events ORDER BY at_utc DESC LIMIT 200')]


@router.post('/api/v1/root/voyages/{voyage_id}/transfer')
def transfer(voyage_id: str,payload: TransferRequest,request: Request):
    return request.app.state.voyages.transfer(voyage_id,payload.destination_user_id,payload.expected_ownership_revision)

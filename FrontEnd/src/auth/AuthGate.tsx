import {useEffect,useState} from 'react';
import type {FormEvent,ReactNode} from 'react';
import {apiErrorMessage} from '../api/errors';
import {bootstrapCsrf,changePassword,login,logout,me} from './api';
import type {User} from './api';
import {clearPrivateState} from './privateState';
import {UserAdministration} from './UserAdministration';
import './auth.css';

export function AuthGate({children}:{children:ReactNode}){
 const [user,setUser]=useState<User|null>(null),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{
  let active=true;
  clearPrivateState();
  const expired=()=>{clearPrivateState();setUser(null);};
  window.addEventListener('caspian-auth-expired',expired);
  bootstrapCsrf().then(me).then(value=>{if(active)setUser(value);}).catch(()=>{}).finally(()=>{if(active)setLoading(false);});
  return ()=>{active=false;window.removeEventListener('caspian-auth-expired',expired);};
 },[]);
 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();const form=new FormData(event.currentTarget);setBusy(true);setError('');
  try{
   clearPrivateState();
   const value=user?await changePassword(String(form.get('current')),String(form.get('new'))):await login(String(form.get('identity')),String(form.get('password')));
   setUser(value);
  }catch(err){setError(apiErrorMessage(err));}finally{setBusy(false);}
 }
 async function signOut(){setBusy(true);setError('');try{await logout();clearPrivateState();setUser(null);}catch(err){setError(apiErrorMessage(err));}finally{setBusy(false);}}
 if(loading)return <main className="auth-page"><p>Проверка сеанса…</p></main>;
 if(!user||user.must_change_password)return <main className="auth-page"><section className="card auth-card"><p>SMART CASPIAN TRANSIT</p><h1>{user?'Смените временный пароль':'Вход в систему'}</h1><p>{user?'Перед началом работы задайте личный пароль.':'Аккаунт выдаёт администратор проекта.'}</p><form onSubmit={submit}>
  {user?<><label>Текущий пароль<input name="current" type="password" autoComplete="current-password" required/></label><label>Новый пароль<input name="new" type="password" autoComplete="new-password" minLength={12} required/></label></>:<><label>Логин или почта<input name="identity" autoComplete="username" required/></label><label>Пароль<input name="password" type="password" autoComplete="current-password" required/></label></>}
  {error&&<p role="alert" className="error">{error}</p>}<button disabled={busy}>{busy?'Подождите…':user?'Сохранить пароль':'Войти'}</button>
 </form></section></main>;
 return <div key={user.id}><div className="auth-bar"><span>{user.login} · {user.role==='root'?'Root':user.role==='admin'?'Администратор':'Логист'}</span><button disabled={busy} onClick={signOut}>Выйти</button>{error&&<span role="alert">{error}</span>}</div>{user.role!=='logistician'&&<UserAdministration user={user}/>}<div key={user.id}>{children}</div></div>;
}

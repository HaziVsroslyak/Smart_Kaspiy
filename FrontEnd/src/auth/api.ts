import {api,setCsrfToken} from '../api/client';
export interface User {id:string;login:string;email:string;role:'logistician'|'admin'|'root';status:string;must_change_password:boolean}
export async function bootstrapCsrf(){const {data}=await api.get<{csrf_token:string}>('/api/v1/auth/csrf');setCsrfToken(data.csrf_token);}
export async function me(){return (await api.get<User>('/api/v1/auth/me')).data;}
export async function login(identity:string,password:string){
 await bootstrapCsrf();
 const {data}=await api.post<{user:User;csrf_token:string}>('/api/v1/auth/login',{identity,password});
 setCsrfToken(data.csrf_token);return data.user;
}
export async function logout(){await api.post('/api/v1/auth/logout');setCsrfToken('');}
export async function changePassword(current_password:string,new_password:string){
 await api.post('/api/v1/auth/password',{current_password,new_password});
 await bootstrapCsrf();return me();
}

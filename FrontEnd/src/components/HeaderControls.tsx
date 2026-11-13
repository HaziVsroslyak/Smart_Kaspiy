import {useEffect,useState} from 'react';
import {api} from '../api/client';

export function HeaderControls(){
 const [dark,setDark]=useState(()=>document.documentElement.dataset.theme==='dark');
 const [health,setHealth]=useState<{state:'checking'|'ready'|'not_ready'|'error';ping:number|null}>({state:'checking',ping:null});
 useEffect(()=>{
  const controller=new AbortController();
  let timer:ReturnType<typeof setTimeout>|undefined;
  async function check(){
   const started=performance.now();
   try{
    const {data}=await api.get<{status:string}>('/api/v1/health',{signal:controller.signal,timeout:8000});
    if(!controller.signal.aborted)setHealth({state:data.status==='ready'?'ready':'not_ready',ping:Math.round(performance.now()-started)});
   }catch{
    if(!controller.signal.aborted)setHealth({state:'error',ping:null});
   }finally{if(!controller.signal.aborted)timer=setTimeout(()=>void check(),30000);}
  }
  void check();
  return ()=>{controller.abort();clearTimeout(timer);};
 },[]);
 function toggleTheme(){
  const next=!dark;setDark(next);
  document.documentElement.dataset.theme=next?'dark':'light';
  try{localStorage.setItem('caspian_theme',next?'dark':'light');}catch{/* Theme remains available when storage is disabled. */}
 }
 const label={checking:'Сервер: проверка…',ready:'Сервер: активен',not_ready:'Сервер: подготовка',error:'Сервер: недоступен'}[health.state];
 return <div className="topbar-right">
  <div className="backend-status-wrapper" tabIndex={0} aria-label={`${label}${health.ping===null?'':`, ${health.ping} мс`}`}>
   <div className={`status-indicator ${health.state==='ready'?'status-green':health.state==='error'?'status-red':'status-yellow'}`}><span className="pulse-dot"/>{label}</div>
   <div className="status-tooltip"><div className="tooltip-title">Статус сервера</div><div className="tooltip-row"><span>Время ответа API:</span><span>{health.ping===null?'—':`${health.ping} мс`}</span></div><div className="tooltip-endpoint"><span>Эндпоинт:</span><code>/api/v1/health</code></div></div>
  </div>
  <button type="button" className="theme-toggle-btn" onClick={toggleTheme} aria-label={dark?'Включить светлую тему':'Включить тёмную тему'} aria-pressed={dark} title="Сменить тему">{dark?'☀':'☾'}</button>
  <a href={`${api.defaults.baseURL}/docs`} target="_blank" rel="noreferrer" className="api-link">API документация ↗</a>
 </div>;
}

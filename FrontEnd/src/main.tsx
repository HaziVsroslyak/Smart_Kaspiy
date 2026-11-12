import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {api, clearCustoms, optimizeJIT} from './api/client';
import type {ApiResult, CustomsResponse, JITResponse, ForecastRouteWeather} from './api/client';
import {WeatherMap} from './components/WeatherMap';
import {VoyagePlanner as RoutePlanner} from './components/VoyagePlanner';
import './style.css';
import './route.css';

const titles = ['Маршрут','Таможня','JIT Arrival','Погода'];
function App() {
 const [tab,setTab]=useState(0), [busy,setBusy]=useState(false), [error,setError]=useState('');
 const [routeWeather,setRouteWeather]=useState<ForecastRouteWeather|null>(null);
 const [customs,setCustoms]=useState<ApiResult<CustomsResponse>|null>(null);
 const [jit,setJit]=useState<ApiResult<JITResponse>|null>(null);
 const [raw,setRaw]=useState('');
 const result = tab===1?customs:tab===2?jit:null;
 async function submit(e:React.FormEvent<HTMLFormElement>) {
  e.preventDefault();
  const data=new FormData(e.currentTarget);
  const s=(k:string)=>String(data.get(k)), n=(k:string)=>Number(data.get(k));
  setBusy(true);setError('');setRaw('');setCustoms(null);setJit(null);
  try {
   if(tab===1){
    const value=await clearCustoms({cargo_payload:{id:s('id'),type:s('type'),weight:n('weight')},provided_hash:s('hash')});
    setCustoms(value);setRaw(JSON.stringify(value,null,2));
   }else if(tab===2){
    const value=await optimizeJIT({distance_nm:n('distance'),current_speed_knots:n('speed'),port_delay_hours:n('delay')});
    setJit(value);setRaw(JSON.stringify(value,null,2));
   }
  }catch(err){setError(err instanceof Error?err.message:'Ошибка запроса');}finally{setBusy(false);}
 }
 function changeTab(i:number){setTab(i);setError('');setRaw('');}
 return <div className="shell">
  <aside><a className="brand" href="#">◈ <span>CASPIAN<small>TRANSIT CONTROL</small></span></a><div className="nav-label">ОПЕРАЦИОННЫЙ ЦЕНТР</div>
   <nav>{titles.map((title,i)=><button disabled={busy} className={tab===i?'active':''} onClick={()=>changeTab(i)} key={title}><span>0{i+1}</span>{title}<b>↗</b></button>)}</nav>
   <div className="aside-bottom"><span className="dot"/> Север — Юг<br/><small>Цифровой двойник · MVP</small></div>
  </aside>
  <main><header><span>МТК СЕВЕР — ЮГ / КАСПИЙ</span><a href={`${api.defaults.baseURL}/docs`} target="_blank" rel="noreferrer">API документация ↗</a></header>
   <section className="intro"><div><p className="eyebrow">SMART CASPIAN TRANSIT</p><h1>{['Движение без ожидания.','Груз готов к прибытию.','Меньше скорости. Больше смысла.','Погода по курсу.'][tab]}</h1><p>{['Рассчитайте маршрут с учетом погодных задержек.','Проверьте целостность данных груза до прибытия в порт.','Согласуйте прибытие судна с освобождением причала.','Прогноз OpenWeather на 5 суток с шагом 3 часа.'][tab]}</p></div><div className="edition">КАСПИЙСКИЙ<br/>КОРИДОР <strong>01—05</strong></div></section>
   {/* Keep the planner mounted so weather selection preserves route inputs and comparison. */}
   <div hidden={tab!==0}><RoutePlanner incomingWeather={routeWeather} onOpenWeather={()=>changeTab(3)}/></div>
   {tab===3&&<WeatherMap onApplyWeather={value=>{setRouteWeather(value);changeTab(0);}}/>}
   {(tab===1||tab===2)&&<div className="workspace">
    <section className="card form-card"><div className="section-title"><h2>{titles[tab]}</h2><span>ПАРАМЕТРЫ</span></div><form onSubmit={submit} key={tab}>
     {tab===1?<>
      <label>ID груза<input name="id" defaultValue="C-001" required maxLength={200}/></label>
      <div className="pair"><label>Тип<input name="type" defaultValue="Зерно" required maxLength={200}/></label><label>Вес · кг<input name="weight" type="number" min="0.001" step="any" defaultValue="100" required/></label></div>
      <label>SHA-256 отправителя<input name="hash" placeholder="64 шестнадцатеричных символа" required pattern="[0-9a-fA-F]{64}" minLength={64} maxLength={64}/></label>
      <p className="hint">Хеш предоставляется отправителем. Совпадение — имитация pre-clearance, а не юридическое разрешение.</p>
     </>:<>
      <label>До порта · морские мили<input name="distance" type="number" min="0.01" step="any" defaultValue="120" required/></label>
      <div className="pair"><label>Скорость · узлы<input name="speed" type="number" min="6" step="any" defaultValue="12" required/></label><label>Задержка · часы<input name="delay" type="number" min="0" step="any" defaultValue="5" required/></label></div>
      <p className="hint">Задержка отсчитывается после исходного ETA. Минимальная скорость — 6 узлов; коэффициент топлива демонстрационный.</p>
     </>}
     <button className="primary" disabled={busy}>{busy?'Выполняем запрос…':tab===1?'Проверить груз':'Рассчитать'} <span>→</span></button>
    </form></section>
    <section className="card result-card"><div className="section-title"><h2>Результат операции</h2><span className={result?result._meta.mode:''}>{result?result._meta.mode==='live'?'ОТВЕТ API':'ДЕМО':'ОЖИДАНИЕ'}</span></div>
     {error&&<p className="error" role="alert">{error}</p>}{result?._meta.warning&&<p className="warning" role="status">{result._meta.warning}</p>}
     {tab===1&&customs?<div className="clearance"><span>{customs.green_corridor?'✓':'◎'}</span><h3>{customs.green_corridor?'Pre-cleared':'Требуется проверка'}</h3><p>{customs._meta.mode==='mock'?'Демонстрационный ответ. Груз не проверен.':customs.green_corridor?'Хеш данных совпадает.':'Хеш данных не совпадает.'}</p></div>:
      tab===2&&jit?<><div className="metrics"><article><small>НОВАЯ СКОРОСТЬ</small><strong>{jit.new_speed_knots.toFixed(1)} <em>уз.</em></strong></article><article><small>ЭКОНОМИЯ CO₂</small><strong>{jit.co2_saved_tonnes.toFixed(2)} <em>т</em></strong></article></div><div className="detail"><p>Прибытие через <b>{jit.arrival_in_hours.toFixed(1)} ч</b></p><p>Остаток ожидания <b>{jit.remaining_wait_hours.toFixed(1)} ч</b></p><p>Экономия топлива <b>{jit.fuel_saved_tonnes.toFixed(2)} т</b></p></div></>:
      busy?<div className="empty">Запрашиваем данные…</div>:!error?<div className="empty"><div className="radar"><i/><b>◈</b></div><h3>Коридор готов к расчету</h3><p>Задайте параметры слева.<br/>Здесь появятся результаты операции.</p></div>:null}
     {raw&&<details><summary>JSON для интеграции</summary><pre>{raw}</pre></details>}
    </section>
   </div>}
   <footer><span>SMART CASPIAN / ПРОТОТИП</span><span>Данные и расчеты требуют эксплуатационной валидации</span></footer>
  </main>
 </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);

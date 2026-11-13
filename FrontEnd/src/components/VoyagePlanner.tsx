import {privateState} from '../auth/privateState';
import {useEffect,useRef,useState} from 'react';
import {apiErrorMessage} from '../api/errors';
import type {ForecastRouteWeather,TransportMode} from '../api/client';
import {createVoyage,getVoyage,reforecastVoyage} from '../api/voyages';
import type {VoyageConditions,VoyageResponse,ConnectionSchedule} from '../api/voyages';
import {RouteMap} from './RouteMap';

const ports=['Махачкала','Астрахань','Энзели','Решт'];
const labels={ship:'Море',rail:'Ж/д',road:'Авто'};
const STORAGE='caspian-active-voyage-v1';
const localInput=(date:Date)=>new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
const when=(value:string)=>new Date(value).toLocaleString('ru-RU',{timeZone:'UTC'})+' UTC';
const initialConditions:VoyageConditions={weather_mode:'scenario',scenario:{source:'scenario',wind_speed_ms:4,wind_gust_ms:6,wave_height_m:1},road:{congestion_percent:20,condition_severity:0,border_wait_hours:4,closed:false},port_congestion:{}};
const number=(value:number)=>value.toFixed(1);
function failure(error:unknown):string{
 return apiErrorMessage(error);
}
export function VoyagePlanner({incomingWeather,onOpenWeather}:{incomingWeather:ForecastRouteWeather|null;onOpenWeather:()=>void}){
 const [source,setSource]=useState('Махачкала'),[target,setTarget]=useState('Решт');
 const [departure,setDeparture]=useState(()=>localInput(new Date()));
 const [modes,setModes]=useState<TransportMode[]>(['ship','rail','road']);
 const [conditions,setConditions]=useState<VoyageConditions>(initialConditions);
 const [scheduled,setScheduled]=useState(false),[connectionPort,setConnectionPort]=useState('Энзели');
 const [connectionMode,setConnectionMode]=useState<TransportMode>('rail');
 const [firstDeparture,setFirstDeparture]=useState(()=>localInput(new Date(Date.now()+36*3600000)));
 const [interval,setIntervalHours]=useState(12),[handling,setHandling]=useState(2);
 const [voyage,setVoyage]=useState<VoyageResponse|null>(null);
 const [criterion,setCriterion]=useState<'fastest'|'eco'>('fastest');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const [restoring,setRestoring]=useState(true);
 const request=useRef<AbortController|null>(null);
 const lastConditions=useRef('');
 const latest=useRef<VoyageResponse|null>(null);
 useEffect(()=>()=>request.current?.abort(),[]);
 function save(value:VoyageResponse){
  latest.current=value;setVoyage(value);
  try{privateState.set(STORAGE,value.id);}catch{/* Backend remains the authoritative store. */}
 }
 useEffect(()=>{
  const controller=new AbortController();
  let id:string|null=null;try{id=privateState.get(STORAGE)??null;}catch{}
  if(!id){setRestoring(false);return ()=>controller.abort();}
  getVoyage(id,controller.signal).then(value=>{
   if(controller.signal.aborted)return;
   save(value);setSource(value.request.source);setTarget(value.request.target);
   setDeparture(localInput(new Date(value.request.departure_at)));setModes(value.request.transport_modes);
   lastConditions.current=JSON.stringify(value.conditions);setConditions(value.conditions);
   const connection=value.request.connections[0];
   if(connection){setScheduled(true);setConnectionPort(connection.terminal);setConnectionMode(connection.transport_mode);setFirstDeparture(localInput(new Date(connection.first_departure_at)));setIntervalHours(connection.interval_hours);setHandling(connection.handling_hours);}
  }).catch(err=>{if(!controller.signal.aborted)setError(failure(err));})
    .finally(()=>{if(!controller.signal.aborted)setRestoring(false);});
  return ()=>controller.abort();
 },[]);
 useEffect(()=>{
  if(incomingWeather)setConditions(old=>({...old,weather_mode:'openweather'}));
 },[incomingWeather]);
 useEffect(()=>{
  if(!voyage||conditions.weather_mode!=='openweather')return;
  const timer=window.setInterval(()=>setRevision(value=>value+1),60000);
  return ()=>window.clearInterval(timer);
 },[voyage?.id,conditions.weather_mode]);
 useEffect(()=>{
  if(!latest.current||restoring)return;
  const signature=JSON.stringify(conditions);
  if(signature===lastConditions.current&&revision===0)return;
  const controller=new AbortController();
  const timer=window.setTimeout(async()=>{
   request.current?.abort();request.current=controller;setBusy(true);setError('');
   try{
    const response=await reforecastVoyage(latest.current!.id,conditions,controller.signal);
    if(!controller.signal.aborted){lastConditions.current=signature;save(response);}
   }catch(err){if(!controller.signal.aborted)setError(failure(err));}
   finally{if(!controller.signal.aborted)setBusy(false);}
  },600);
  return ()=>{window.clearTimeout(timer);controller.abort();};
 },[conditions,revision,restoring,voyage?.id]);
 async function plan(){
  if(!modes.length){setError('Выберите хотя бы один вид транспорта.');return;}
  const controller=new AbortController();request.current?.abort();request.current=controller;
  setBusy(true);setError('');
  try{
   const connections:ConnectionSchedule[]=scheduled?[{terminal:connectionPort,transport_mode:connectionMode,first_departure_at:new Date(firstDeparture).toISOString(),interval_hours:interval,handling_hours:handling}]:[];
   const response=await createVoyage({source,target,departure_at:new Date(departure).toISOString(),transport_modes:modes,connections,conditions},controller.signal);
   if(!controller.signal.aborted){lastConditions.current=JSON.stringify(conditions);setRevision(0);save(response);}
  }catch(err){if(!controller.signal.aborted)setError(failure(err));}
  finally{if(!controller.signal.aborted)setBusy(false);}
 }
 function reset(){
  request.current?.abort();latest.current=null;setVoyage(null);setRevision(0);setError('');setBusy(false);
  try{privateState.delete(STORAGE);}catch{}
 }
 function preset(wind:number,gust:number,wave:number){setConditions(old=>({...old,weather_mode:'scenario',scenario:{source:'scenario',wind_speed_ms:wind,wind_gust_ms:gust,wave_height_m:wave}}));}
 const current=voyage?.current[criterion]??null, baseline=voyage?.baseline[criterion]??null;
 const checkpoints=current?.segments.flatMap(leg=>leg.checkpoints)??[];
 const changedHours=current&&baseline?(new Date(current.eta).getTime()-new Date(baseline.eta).getTime())/3600000:0;
 const routeChanged=current&&baseline&&JSON.stringify(current.segments.map(s=>[s.source,s.target,s.edge_id]))!==JSON.stringify(baseline.segments.map(s=>[s.source,s.target,s.edge_id]));
 const pending=voyage&&lastConditions.current!==JSON.stringify(conditions);
 return <section className="route-planner">
  <section className="card route-controls"><div className="section-title"><h2>План перевозки и прогноз ETA</h2><span>{voyage?'ПЛАН СОХРАНЁН':'НОВЫЙ ПЛАН'}</span></div>
   <div className="route-inputs"><label>Отправление<select disabled={!!voyage||busy} value={source} onChange={e=>setSource(e.target.value)}>{ports.map(p=><option key={p}>{p}</option>)}</select></label><label>Назначение<select disabled={!!voyage||busy} value={target} onChange={e=>setTarget(e.target.value)}>{ports.map(p=><option key={p}>{p}</option>)}</select></label><label>Отправление · местное время<input disabled={!!voyage||busy} type="datetime-local" value={departure} onChange={e=>setDeparture(e.target.value)}/></label><button className="primary" onClick={onOpenWeather}>Открыть погоду ↗</button></div>
   <fieldset className="transport-options" disabled={!!voyage||busy}><legend>Разрешённый транспорт исходного плана</legend>{(['ship','rail','road'] as const).map(mode=><label key={mode}><input type="checkbox" checked={modes.includes(mode)} onChange={e=>setModes(old=>e.target.checked?[...old,mode]:old.filter(m=>m!==mode))}/>{labels[mode]}</label>)}</fieldset>
   <fieldset className="connection-settings" disabled={!!voyage||busy}><legend>Расписание стыковки · сценарий</legend><label className="inline-check"><input type="checkbox" checked={scheduled} onChange={e=>setScheduled(e.target.checked)}/> Учитывать периодическое отправление</label>
    {scheduled&&<div className="route-inputs"><label>Терминал<select value={connectionPort} onChange={e=>setConnectionPort(e.target.value)}>{ports.map(p=><option key={p}>{p}</option>)}</select></label><label>Транспорт<select value={connectionMode} onChange={e=>setConnectionMode(e.target.value as TransportMode)}>{(['ship','rail','road'] as const).map(m=><option key={m} value={m}>{labels[m]}</option>)}</select></label><label>Первое отправление · местное<input type="datetime-local" value={firstDeparture} onChange={e=>setFirstDeparture(e.target.value)}/></label><div className="pair"><label>Интервал · ч<input type="number" min="1" max="168" value={interval} onChange={e=>setIntervalHours(Number(e.target.value))}/></label><label>Перегрузка · ч<input type="number" min="0" max="48" value={handling} onChange={e=>setHandling(Number(e.target.value))}/></label></div></div>}
   </fieldset>
   <div className="port-buttons">{voyage?<><button onClick={()=>setRevision(v=>v+1)} disabled={busy||restoring}>Обновить прогноз рейса</button><button onClick={reset} disabled={busy}>Новый исходный план</button></>:<button onClick={()=>void plan()} disabled={busy||restoring}>{busy?'Рассчитываем контрольные точки…':'Рассчитать и сохранить исходный план'}</button>}</div>
   <p className="hint">Исходный план хранится на сервере и не меняется при обновлении прогноза. Время в расчёте — UTC; поля ввода используют ваш местный часовой пояс. Новый план позволяет изменить маршрут, дату и расписание.</p>
  </section>
  <section className="card route-controls"><div className="section-title"><h2>Текущие условия</h2><span>ПЕРЕСЧЁТ БЕЗ ИЗМЕНЕНИЯ ПЛАНА</span></div>
   <div className="port-buttons"><button onClick={()=>preset(4,6,1)} aria-pressed={conditions.weather_mode==='scenario'&&conditions.scenario.wind_speed_ms===4}>Спокойно</button><button onClick={()=>preset(14,18,2)}>Усиление ветра</button><button onClick={()=>preset(22,27,3.2)}>Шторм · сценарий</button><button aria-pressed={conditions.weather_mode==='openweather'} onClick={()=>setConditions(old=>({...old,weather_mode:'openweather'}))}>OpenWeather по маршруту</button></div>
   {conditions.weather_mode==='scenario'?<div className="route-inputs"><label>Ветер · м/с<input type="number" min="0" max="100" step="0.1" value={conditions.scenario.wind_speed_ms} onChange={e=>setConditions({...conditions,scenario:{...conditions.scenario,wind_speed_ms:Number(e.target.value)}})}/></label><label>Порывы · м/с<input type="number" min="0" max="150" step="0.1" value={conditions.scenario.wind_gust_ms??0} onChange={e=>setConditions({...conditions,scenario:{...conditions.scenario,wind_gust_ms:Number(e.target.value)}})}/></label><label>Волны · м<input type="number" min="0" max="30" step="0.1" value={conditions.scenario.wave_height_m??0} onChange={e=>setConditions({...conditions,scenario:{...conditions.scenario,wave_height_m:Number(e.target.value)}})}/></label></div>:<p className="hint">Сервер запрашивает прогноз в контрольных точках на время прохождения каждого участка. Отдельная точка/слот вкладки «Погода» не распространяется на весь рейс. Опрос рейса раз в минуту; кэш погоды — 10 минут. Высота волн у этого продукта отсутствует.</p>}
   <div className="route-inputs">{ports.map(port=><label key={port}>Загруженность · {port} · %<input type="number" placeholder="Из графа" min="0" max="100" value={conditions.port_congestion[port]??''} onChange={e=>setConditions(old=>{const values={...old.port_congestion};if(e.target.value==='')delete values[port];else values[port]=Number(e.target.value);return {...old,port_congestion:values};})}/></label>)}</div>
   {modes.includes('road')&&<div className="route-inputs"><label>Дороги · загрузка %<input type="number" min="0" max="100" value={conditions.road.congestion_percent} onChange={e=>setConditions({...conditions,road:{...conditions.road,congestion_percent:Number(e.target.value)}})}/></label><label>Дорожные условия · 0–10<input type="number" min="0" max="10" value={conditions.road.condition_severity} onChange={e=>setConditions({...conditions,road:{...conditions.road,condition_severity:Number(e.target.value)}})}/></label><label>Ожидание на одном КПП · ч<input type="number" min="0" max="168" value={conditions.road.border_wait_hours} onChange={e=>setConditions({...conditions,road:{...conditions.road,border_wait_hours:Number(e.target.value)}})}/></label><label>Автодороги<select value={String(conditions.road.closed)} onChange={e=>setConditions({...conditions,road:{...conditions.road,closed:e.target.value==='true'}})}><option value="false">Доступны</option><option value="true">Закрыты · сценарий</option></select></label></div>}
   <p className="hint">Загруженность портов, дороги и расписания пока задаются сценарием. Для авто Махачкала — Энзели используется коридор через Грузию и Азербайджан с тремя границами.</p>
  </section>
  {error&&<p className="error" role="alert">{error} {voyage?'Исходный план сохранён. Отображаемый прогноз мог устареть.':'Исходный план ещё не создан.'}</p>}
  {(busy||pending)&&<p className="warning" role="status">Новые условия ещё не применены или выполняется обновление. На карте последний успешно сохранённый расчёт.</p>}
  <div className="route-workspace"><section className="card map-card"><div className="section-title"><h2>Маршрут и контрольные точки</h2><span>{voyage?`ОБНОВЛЕНИЕ ${voyage.revision}`:'НЕТ ПЛАНА'}</span></div><div className="port-buttons"><button aria-pressed={criterion==='fastest'} onClick={()=>setCriterion('fastest')}>Самый быстрый</button><button aria-pressed={criterion==='eco'} onClick={()=>setCriterion('eco')}>Минимум CO₂</button></div><RouteMap route={current} previous={baseline} weather={null} checkpoints={checkpoints}/></section>
   <section className="card route-summary" aria-live="polite"><div className="section-title"><h2>ETA и причины изменений</h2><span>{current?.coverage==='partial'?'НЕПОЛНЫЙ ПРОГНОЗ':current?'РАССЧИТАНО':'ОЖИДАНИЕ'}</span></div>
    {current&&baseline&&voyage?<><p className="hint">План: {voyage.id}</p><div className="detail"><p>Исходный ETA <b>{when(baseline.eta)}</b></p><p>Новый ETA <b>{when(current.eta)}</b></p><p>Отклонение от плана <b>{changedHours>=0?'+':''}{number(changedHours)} ч</b></p></div>
     <p className="route-change">{routeChanged?'Маршрут или вид транспорта изменился относительно исходного плана.':'Маршрут и виды транспорта сохранены; ETA уточнён.'}</p><div className="route-line">{current.nodes.join(' → ')}</div><div className="metrics"><article><small>ВРЕМЯ В ПУТИ</small><strong>{number(current.total_time_hours)} <em>ч</em></strong></article><article><small>CO₂ / 1 TEU</small><strong>{number(current.total_co2_emissions_kg)} <em>кг</em></strong></article></div><p>Стоимость: ${current.total_cost_usd.toLocaleString()}</p>
     {current.coverage==='partial'&&<p className="warning">Часть пути вне доступного горизонта погоды. ETA рассчитан с неполными погодными данными; неизвестные волны и ветер не считаются подтверждённым штилем.</p>}
     <ol className="route-legs">{current.segments.map((leg,index)=><li key={index}><b>{labels[leg.transport_mode]} · {leg.source} → {leg.target}</b><small>{when(leg.departure_at)} → {when(leg.arrival_at)}</small><small>Задержки {number(leg.delay_hours)} ч, ожидание стыковки {number(leg.connection_wait_hours)} ч</small></li>)}</ol>
     {[...current.reasons,...voyage.current.excluded_reasons,...voyage.current.alternative_reasons].map((reason,index)=><p key={index} className={reason.code==='weather'?'hint':'warning'}>{reason.message}{reason.hours>0?` (${number(reason.hours)} ч)`:''}</p>)}
     {current.reasons.length===0&&<p className="hint">Дополнительные причины задержки не выявлены.</p>}
     <p className="hint">План сохранён: {when(voyage.baseline.calculated_at)}. Прогноз обновлён: {when(voyage.current.calculated_at)}. Погодные/портовые оценки факторов не складываются: это отдельные контрфактические сравнения ML.</p>
     <details><summary>Контрольные точки и погода</summary><div className="checkpoint-table"><table><thead><tr><th>Точка / прохождение UTC</th><th>Слот прогноза</th><th>Ветер / порывы</th></tr></thead><tbody>{checkpoints.map((cp,i)=><tr key={i}><td>{cp.name}<br/>{when(cp.passage_at)}<br/>{cp.latitude}, {cp.longitude}</td><td>{cp.status==='scenario'?'Сценарий':cp.forecast_at?when(cp.forecast_at):'Вне горизонта'}<br/>{cp.retrieved_at?`Получен: ${when(cp.retrieved_at)}`:''}</td><td>{cp.wind_speed_ms??'—'} / {cp.wind_gust_ms??'—'} м/с<br/>Волны: {cp.wave_height_m??'нет данных'}</td></tr>)}</tbody></table></div></details>
     <details><summary>Исходный план и новый прогноз · JSON</summary><pre>{JSON.stringify(voyage,null,2)}</pre></details>
    </>:<p className="hint">Задайте маршрут и отправление, затем сохраните исходный план.</p>}
    <p className="hint">Модель обучена на синтетике. Штормовое правило MVP: ветер/порывы ≥ 20 м/с или волны &gt; 2,5 м исключают морской вариант на время прохождения. Контрольные точки и доли времени — приближённые; это не навигационная система.</p>
   </section>
  </div>
 </section>;
}

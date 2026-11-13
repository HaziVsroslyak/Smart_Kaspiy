import {WeatherDatasetPanel} from './WeatherDatasetPanel';
import {privateState} from '../auth/privateState';
import {useEffect,useRef,useState} from 'react';
import {getDemoCatalog,getDemoRun,runDemoScenario,simulateVoyageJIT,strategyRoute,timelineProgress,vesselPosition} from '../api/demo';
import type {DemoCatalog,DemoResult,DemoRunRequest,StrategyResult} from '../api/demo';
import {apiErrorMessage} from '../api/errors';
import type {Checkpoint} from '../api/voyages';
import {RouteMap} from './RouteMap';
import '../jit.css';

const STORAGE='caspian-jit-demo-run-v1';
const statusLabels:Record<StrategyResult['status'],string>={ok:'Рассчитано',blocked:'Недоступно',not_applicable:'Не применяется',insufficient_data:'Недостаточно данных'};
const when=(value:string|null)=>value?new Date(value).toLocaleString('ru-RU',{timeZone:'UTC'})+' UTC':'—';
const numeric=(value:number|null,unit='')=>value===null?'—':`${value.toFixed(2)}${unit?' '+unit:''}`;

function DemoTimeline({strategies,progress,setProgress}:{strategies:StrategyResult[];progress:number;setProgress:(value:number)=>void}){
 const points=strategies.flatMap(strategy=>strategy.timeline.map(item=>Date.parse(item.at))).filter(Number.isFinite);
 const start=points.length?Math.min(...points):0,end=points.length?Math.max(...points):0;
 const elapsed=start+(end-start)*progress/100;
 return <section className="jit-timeline" aria-label="Воспроизведение временной линии стратегий">
  <div className="section-title"><h2>Временная линия перевозки</h2><span>UTC · СИМУЛЯЦИЯ</span></div>
  {end>start?<><label>Момент симуляции · {when(new Date(elapsed).toISOString())}<input type="range" min="0" max="100" step="0.1" value={progress} onChange={event=>setProgress(Number(event.target.value))}/></label>
   {strategies.map(strategy=><div className="jit-track" key={strategy.id}>
    <div className="jit-track-label"><b>{strategy.label}</b><span>{statusLabels[strategy.status]}</span></div>
    <svg viewBox="0 0 800 62" role="img" aria-label={`${strategy.label}: ${strategy.timeline.map(item=>item.name).join(', ')}`}>
     <line x1="20" y1="20" x2="780" y2="20" stroke="#d6e4e2" strokeWidth="5"/>
     <line x1="20" y1="20" x2={20+760*progress/100} y2="20" stroke={strategy.id==='jit'?'#197c74':strategy.id==='alternative'?'#7954a8':'#879997'} strokeWidth="5"/>
     {strategy.timeline.map((item,index)=>{const x=20+760*timelineProgress(item.at,new Date(start).toISOString(),new Date(end).toISOString());return <g key={index}><circle cx={x} cy="20" r="5" fill={Date.parse(item.at)<=elapsed?'#183f49':'#fff'} stroke="#183f49"><title>{item.name} · {when(item.at)}</title></circle><text x={Math.max(50,Math.min(750,x))} y={43} textAnchor="middle" fontSize="10" fill="#48666d">{index+1}</text></g>;})}
     <circle cx={20+760*progress/100} cy="20" r="7" fill="#d4e9a7" stroke="#123a43" strokeWidth="2"><title>Выбранный момент времени</title></circle>
    </svg>
    <ol className="jit-event-labels">{strategy.timeline.map((item,index)=><li key={index}>{index+1}. {item.name}</li>)}</ol>
    <p className="hint">{strategy.timeline.filter(item=>Date.parse(item.at)<=elapsed).at(-1)?.name??'До начала перевозки'}</p>
   </div>)}
   <p className="hint">Ползунок показывает события во времени. География маршрута меняется только при выборе другой транспортной цепочки.</p>
  </>:<p className="hint">Для этого случая нет доступной временной линии. Причина указана в результатах.</p>}
 </section>;
}

export function JITPlanner(){
 const [datasetId,setDatasetId]=useState(privateState.get('caspian-weather-dataset')??'');
 const [departureAt,setDepartureAt]=useState('');
 const [catalog,setCatalog]=useState<DemoCatalog|null>(null),[scenarioId,setScenarioId]=useState('');
 const [result,setResult]=useState<DemoResult|null>(null),[strategyId,setStrategyId]=useState<StrategyResult['id']>('jit');
 const [progress,setProgress]=useState(0);
 const [offlineMap,setOfflineMap]=useState(false);
 const [seed,setSeed]=useState(42),[manual,setManual]=useState(false);
 const [activeVoyageId]=useState(()=>{try{return privateState.get('caspian-active-voyage-v1');}catch{return null;}});
 const [wind,setWind]=useState(4),[wave,setWave]=useState(1),[congestion,setCongestion]=useState(50);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[restoration,setRestoration]=useState('');
 const active=useRef<AbortController|null>(null);
 const appliedForm=useRef('');
 const [reload,setReload]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);setError('');
  async function load(){
   try{
    const value=await getDemoCatalog(controller.signal);if(controller.signal.aborted)return;
    setCatalog(value);setScenarioId(old=>old||value.scenarios[0]?.id||'');
    let id:string|null=null;try{id=privateState.get(STORAGE)??null;}catch{}
    if(id){
     try{const saved=await getDemoRun(id,controller.signal);if(!controller.signal.aborted){const restoredScenario=value.scenarios.some(item=>item.id===saved.scenario_id)?saved.scenario_id:value.scenarios[0]?.id??'';const restoredManual=saved.inputs?.wind_speed_ms!=null||saved.inputs?.wave_height_m!=null||saved.inputs?.port_congestion_percent!=null;const restoredWind=saved.inputs?.wind_speed_ms??4,restoredWave=saved.inputs?.wave_height_m??1,restoredCongestion=saved.inputs?.port_congestion_percent??50;appliedForm.current=JSON.stringify({id:restoredScenario,seed:saved.seed,manual:restoredManual,...(restoredManual?{wind:restoredWind,wave:restoredWave,congestion:restoredCongestion}:{})});setResult(saved);setScenarioId(restoredScenario);setSeed(saved.seed);setManual(restoredManual);setWind(restoredWind);setWave(restoredWave);setCongestion(restoredCongestion);setRestoration('Восстановлен последний расчёт. Исходный план сохранён на сервере.');}}
     catch(err){if(!controller.signal.aborted)setRestoration(`Прошлый расчёт не загружен: ${apiErrorMessage(err)} Выберите сценарий и запустите новый.`);}
    }
   }catch(err){if(!controller.signal.aborted)setError(apiErrorMessage(err));}
   finally{if(!controller.signal.aborted)setLoading(false);}
  }
  void load();return ()=>controller.abort();
 },[reload]);
 useEffect(()=>()=>active.current?.abort(),[]);
 async function calculate(savedVoyage=false){
  if(savedVoyage?!activeVoyageId:!scenarioId)return;
  const controller=new AbortController();active.current?.abort();active.current=controller;
  setBusy(true);setError('');setRestoration('');
  const payload:DemoRunRequest={seed};
  if(datasetId){if(!departureAt){setError('Укажите время отправления для погодного набора.');setBusy(false);return;}Object.assign(payload,{dataset_id:datasetId,departure_at:new Date(departureAt).toISOString()});}
  if(manual&&!datasetId)Object.assign(payload,{wind_speed_ms:wind,wave_height_m:wave,port_congestion_percent:congestion});
  try{
   const value=savedVoyage?await simulateVoyageJIT(activeVoyageId!,payload,controller.signal):await runDemoScenario(scenarioId,payload,controller.signal);
   if(controller.signal.aborted)return;
   appliedForm.current=JSON.stringify({id:scenarioId,seed,manual,datasetId,departureAt,...(manual?{wind,wave,congestion}:{})});
   setProgress(0);setResult(value);setStrategyId(value.strategies.find(strategy=>strategy.id==='jit')?.id??value.strategies[0]?.id??'baseline');
   try{privateState.set(STORAGE,value.id);}catch{}
  }catch(err){if(!controller.signal.aborted)setError(apiErrorMessage(err));}
  finally{if(!controller.signal.aborted)setBusy(false);}
 }
 const chosen=catalog?.scenarios.find(scenario=>scenario.id===scenarioId);
 const strategy=result?.strategies.find(item=>item.id===strategyId)??result?.strategies[0]??null;
 const route=strategyRoute(strategy),baselineRoute=strategyRoute(result?.baseline??null);
 const checkpoints:Checkpoint[]=strategy?.checkpoints.map(point=>({...point,forecast_at:null,retrieved_at:null,wind_gust_ms:null,severity:null,status:point.wind_speed_ms===null?'outside_horizon':'scenario'}))??[];
 const playbackTimes=result?.strategies.flatMap(item=>item.timeline.map(point=>Date.parse(point.at))).filter(Number.isFinite)??[];
 const playbackStart=playbackTimes.length?Math.min(...playbackTimes):0,playbackEnd=playbackTimes.length?Math.max(...playbackTimes):0;
 const vessel=vesselPosition(strategy,new Date(playbackStart+(playbackEnd-playbackStart)*progress/100).toISOString());
 const jit=result?.strategies.find(item=>item.id==='jit');
 const draft=result&&appliedForm.current!==JSON.stringify({id:scenarioId,seed,manual,datasetId,departureAt,...(manual?{wind,wave,congestion}:{})});
 const invalidOverrides=manual&&(!Number.isFinite(wind)||wind<0||wind>25||!Number.isFinite(wave)||wave<0.1||wave>4.5||!Number.isFinite(congestion)||congestion<10||congestion>100);
 return <section className="jit-demo"><WeatherDatasetPanel onSelect={setDatasetId}/>{datasetId&&<section className="card"><p>Погодный набор: {datasetId}. Логистика и обучающие данные модели остаются синтетическими.</p><label>Отправление · местное время<input type="datetime-local" value={departureAt} onChange={event=>setDepartureAt(event.target.value)} required/></label><button onClick={()=>{setDatasetId('');privateState.delete('caspian-weather-dataset');}}>Отключить набор</button></section>}
  <section className="card jit-controls"><div className="section-title"><h2>Лаборатория JIT Arrival</h2><span>СИНТЕТИЧЕСКИЕ ДАННЫЕ</span></div>
   <p className="jit-lead">Один сценарий, три стратегии. Модель прогнозирует задержки и готовность терминала, алгоритм выбирает скорость и транспортную цепочку.</p>
   {loading?<p role="status">Проверяем API и загружаем сценарии…</p>:catalog?<>
    <div className="jit-input-row"><label>Демонстрационный случай<select value={scenarioId} onChange={event=>{setScenarioId(event.target.value);setRestoration('');}} disabled={busy}>{catalog.scenarios.map(scenario=><option key={scenario.id} value={scenario.id}>{scenario.title}</option>)}</select></label><label>Seed<input type="number" min="0" max="2147483647" step="1" value={seed} onChange={event=>setSeed(Number(event.target.value))} disabled={busy}/></label><button className="primary" disabled={busy||!scenarioId||!Number.isInteger(seed)||seed<0||seed>2147483647||invalidOverrides} onClick={()=>void calculate()}>{busy?'Модель считает…':'Запустить сценарий'} <span>↗</span></button></div>
    <p>{chosen?.description}</p>
    {activeVoyageId&&<div className="port-buttons"><button disabled={busy||!Number.isInteger(seed)||seed<0||seed>2147483647||invalidOverrides} onClick={()=>void calculate(true)}>Рассчитать для сохранённого рейса</button><span className="hint">Рейс {activeVoyageId}. Расчёт использует те же seed и ручные признаки.</span></div>}
    <label className="inline-check"><input type="checkbox" checked={manual} onChange={event=>setManual(event.target.checked)} disabled={busy}/> Изменить погодные и портовые признаки</label>
    {manual&&<div className="jit-input-row"><label>Ветер · м/с<input type="number" min="0" max="25" step="0.1" value={wind} onChange={event=>setWind(Number(event.target.value))} disabled={busy}/></label><label>Волны · м<input type="number" min="0.1" max="4.5" step="0.1" value={wave} onChange={event=>setWave(Number(event.target.value))} disabled={busy}/></label><label>Загруженность порта · %<input type="number" min="10" max="100" step="1" value={congestion} onChange={event=>setCongestion(Number(event.target.value))} disabled={busy}/></label></div>}
    <p className="hint">Каждый запуск выполняет расчёт на бэкенде. Сеть и ключи погоды не требуются; одинаковый seed воспроизводит случай. Исходный план каждого запуска остаётся неизменным.</p>
   </>:<button onClick={()=>setReload(value=>value+1)}>Проверить API повторно</button>}
   {error&&<p className="error" role="alert">{error}{result?' Ниже остаётся последний успешный расчёт. Новый результат не получен.':''}</p>}
   {restoration&&<p className="hint">{restoration}</p>}
   {draft&&<p className="warning" role="status">Параметры формы ещё не применены к результату ниже. Нажмите «Запустить сценарий».</p>}
  </section>
  {result?<>
   <section className="card jit-results"><div className="section-title"><h2>{result.title}</h2><span>SEED {result.seed} · {result.data_source==='mixed'?'РЕАЛЬНАЯ ПОГОДА / ДЕМО-ЛОГИСТИКА':'СИНТЕТИКА'}</span></div><p>{result.description}</p><p className="hint">Расчёт {result.id} · {when(result.created_at)}. {result.parent_voyage_id?`По сохранённому рейсу ${result.parent_voyage_id}. `:''}{result.data_source==='mixed'?'Погода из выбранного набора; логистика и обучение модели синтетические.':'Это демонстрация на синтетике, не оценка качества реальных перевозок.'}</p>
    <p className="warning">{result.warnings[0]}</p><details><summary>Допущения модели и границы расчёта</summary>{result.warnings.slice(1).map((warning,index)=><p className="hint" key={index}>{warning}</p>)}</details>
    <div className="metrics jit-headlines"><article><small>РЕКОМЕНДОВАННАЯ СКОРОСТЬ</small><strong>{jit?.status==='ok'?numeric(jit.speed_knots,'уз.'):'—'}</strong></article><article><small>ЭКОНОМИЯ CO₂ ОТ СЖИГАНИЯ HFO</small><strong>{jit?.status==='ok'?numeric(jit.co2_saved_tonnes,'т'):'—'}</strong></article><article><small>ОСТАТОК ОЖИДАНИЯ JIT</small><strong>{jit?.status==='ok'?numeric(jit.remaining_wait_hours,'ч'):'—'}</strong></article></div>
    <div className="jit-table-wrap"><table className="jit-strategies"><thead><tr><th>Стратегия</th><th>Состояние</th><th>Скорость</th><th>ETA груза · UTC</th><th>Рейд / стыковка</th><th>Топливо / CO₂ HFO</th><th>Грузовой CO₂e</th><th>Стоимость</th></tr></thead><tbody>{result.strategies.map(item=><tr key={item.id} className={strategy?.id===item.id?'jit-selected':''}><td><button onClick={()=>setStrategyId(item.id)} aria-pressed={strategy?.id===item.id}>{item.label}</button></td><td>{statusLabels[item.status]}</td><td>{numeric(item.speed_knots,'уз.')}</td><td>{when(item.eta)}</td><td>{item.status==='ok'?`${numeric(item.berth_wait_hours,'ч')} / ${numeric(item.connection_wait_hours,'ч')}`:'—'}</td><td>{numeric(item.fuel_tonnes,'т')} / {numeric(item.co2_tonnes,'т')}</td><td>{numeric(item.cargo_co2e_kg,'кг')}</td><td>{item.status==='ok'?`$${item.cost_usd.toLocaleString('ru-RU',{maximumFractionDigits:2})}`:'—'}</td></tr>)}</tbody></table></div>
    <p className="hint">Прямой CO₂ от мазута и грузовой CO₂e имеют разные границы учёта. Они показаны отдельно и не складываются.</p>
   </section>
   <div className="route-workspace"><section className="card map-card"><div className="section-title"><h2>{strategy?.label??'Маршрут'}</h2><span>{strategy?statusLabels[strategy.status]:'ОЖИДАНИЕ'}</span></div>
    {strategy?.reason&&<p className={strategy.status==='ok'?'route-ok':'warning'}>{strategy.reason}</p>}
    <label className="inline-check"><input type="checkbox" checked={offlineMap} onChange={event=>setOfflineMap(event.target.checked)}/> Офлайн-схема вместо онлайн-карты</label>
    <RouteMap route={route} previous={baselineRoute} weather={null} checkpoints={checkpoints} offline={offlineMap} vessel={vessel}/>
    {!route&&<p className="hint">Для выбранной стратегии нет рассчитанного пути. Серым может отображаться исходный план.</p>}
   </section><section className="card route-summary"><div className="section-title"><h2>Причины и прогнозы модели</h2><span>ПРИЗНАКИ ДОСТУПНЫ</span></div>
    {result.predictions.length?result.predictions.map((prediction,index)=><article className="jit-prediction" key={`${prediction.model_id}-${index}`}><b>{prediction.model_id}</b><p>{prediction.target}: <strong>{numeric(prediction.value_hours,'ч')}</strong></p><p className="hint">Оценочный интервал: {numeric(prediction.lower_hours)}–{numeric(prediction.upper_hours)} ч. Датасет: {prediction.data_version}.</p><details><summary>Признаки этого вызова</summary><pre>{JSON.stringify(prediction.features,null,2)}</pre></details></article>):<p className="hint">Модель не вызывалась: для этого случая отсутствуют необходимые признаки или применимый участок.</p>}
    <details><summary>Качество модели на отложенной синтетике</summary><pre>{JSON.stringify(result.model_report,null,2)}</pre></details>
   </section></div>
   <section className="card jit-results"><DemoTimeline key={result.id} strategies={result.strategies} progress={progress} setProgress={setProgress}/></section>
   <section className="card jit-results"><div className="section-title"><h2>События сценария</h2><span>ОБЪЯСНЕНИЕ РЕШЕНИЯ</span></div><ol className="jit-events">{result.events.map((event,index)=><li key={index}><time>{when(event.at)}</time><div><b>{event.name}</b><p>{event.detail}</p></div></li>)}</ol><details><summary>Исходный план и результаты · JSON</summary><pre>{JSON.stringify(result,null,2)}</pre></details></section>
  </>:!loading&&<section className="card jit-empty"><h2>Выберите случай и запустите алгоритм</h2><p>Здесь появятся прогнозы ML, исходная стратегия, решение JIT и доступная альтернатива.</p></section>}
 </section>;
}

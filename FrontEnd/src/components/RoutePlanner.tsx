import {useEffect, useRef, useState} from 'react';
import axios from 'axios';
import {calculateWeatherRoute} from '../api/client';
import type {ForecastRouteWeather, RouteRequest, RouteResponse, TransportMode, RoadConditions} from '../api/client';
import {RouteMap} from './RouteMap';

const ports=['Махачкала','Астрахань','Энзели','Решт'];
const seasons=['winter','spring','summer','autumn'] as const;
const fmt=(n:number)=>n.toFixed(1);
const delta=(n:number)=>`${n>=0?'+':''}${fmt(n)}`;
export function RoutePlanner({incomingWeather,onOpenWeather}:{incomingWeather:ForecastRouteWeather|null;onOpenWeather:()=>void}) {
  const [source,setSource]=useState('Махачкала'),[target,setTarget]=useState('Решт');
  const [season,setSeason]=useState<RouteRequest['season']>(seasons[Math.floor(((new Date().getUTCMonth()+1)%12)/3)]);
  const [transportModes,setTransportModes]=useState<TransportMode[]>(['ship','rail','road']);
  const [road,setRoad]=useState<RoadConditions>({congestion_percent:20,condition_severity:0,border_wait_hours:4,closed:false});
  const [mode,setMode]=useState<'scenario'|'openweather'>('scenario');
  const [wind,setWind]=useState(4),[gust,setGust]=useState(6),[wave,setWave]=useState(1);
  const [route,setRoute]=useState<RouteResponse|null>(null),[previous,setPrevious]=useState<RouteResponse|null>(null);
  const [criterion,setCriterion]=useState<'fastest'|'eco'>('fastest');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0);
  const [checkedAt,setCheckedAt]=useState('');
  const lastSuccess=useRef<{source:string;target:string;response:RouteResponse}|null>(null);
  useEffect(()=>{
    if(incomingWeather){
      setMode('openweather');
      setSeason(seasons[Math.floor(((new Date(incomingWeather.forecast_at).getUTCMonth()+1)%12)/3)]);
    }
  },[incomingWeather]);
  useEffect(()=>{
    if(mode!=='openweather'||!incomingWeather)return;
    const timer=window.setInterval(()=>setRevision(value=>value+1),60000);
    return ()=>window.clearInterval(timer);
  },[mode,incomingWeather]);
  useEffect(()=>{
    const controller=new AbortController();
    setBusy(true);setError('');
    const timer=window.setTimeout(async()=>{
      try {
        if(!transportModes.length)throw new Error('Выберите хотя бы один вид транспорта.');
        if(mode==='openweather'&&!incomingWeather)throw new Error('Выберите точку и время во вкладке «Погода».');
        const response=await calculateWeatherRoute({source,target,season,transport_modes:transportModes,road_conditions:road,weather:mode==='openweather'?incomingWeather!:
          {source:'scenario',wind_speed_ms:wind,wind_gust_ms:gust,wave_height_m:wave}},controller.signal);
        if(controller.signal.aborted)return;
        const old=lastSuccess.current;
        // Keep the previous distinct calculation during unchanged polling responses.
        if(old?.source===source&&old.target===target){
          const signature=(value:RouteResponse)=>JSON.stringify([
            value.segments,value.eco.segments,value.weather.source,value.weather.severity,
            value.weather.wind_speed_ms,value.weather.wind_gust_ms,value.weather.wave_height_m,
            value.weather.forecast_at,value.weather.location,value.road_conditions,value.transport_modes,
          ]);
          const changed=signature(old.response)!==signature(response);
          if(changed)setPrevious(old.response);
        }else setPrevious(null);
        lastSuccess.current={source,target,response};setRoute(response);
        setCheckedAt(new Date().toLocaleTimeString('ru-RU'));
      }catch(err){
        if(controller.signal.aborted)return;
        setRoute(null);setPrevious(null);
        if(axios.isAxiosError(err)){
          const status=err.response?.status;
          setError(status===409?'Доступного маршрута нет для выбранных видов транспорта и ограничений. Разрешите альтернативный транспорт или измените условия.':
            status===422?`Параметры или время прогноза недоступны. Выберите актуальный прогноз. ${JSON.stringify(err.response?.data?.detail)}`:
            status?`API ${status}: ${JSON.stringify(err.response?.data?.detail ?? 'Ошибка расчёта')}`:
            'Нет связи с API. Новый маршрут не рассчитан. Проверьте запуск бэкенда и повторите запрос.');
        }else setError(err instanceof Error?err.message:'Ошибка расчёта');
      }finally{if(!controller.signal.aborted)setBusy(false);}
    },400);
    return ()=>{window.clearTimeout(timer);controller.abort();};
  },[source,target,season,mode,wind,gust,wave,incomingWeather,revision,transportModes,road]);
  const displayed=route?(criterion==='eco'?route.eco:route):null;
  const oldDisplayed=previous?(criterion==='eco'?previous.eco:previous):null;
  const changedPath=displayed&&oldDisplayed&&JSON.stringify(displayed.segments.map(s=>[s.source,s.target,s.edge_id]))!==JSON.stringify(oldDisplayed.segments.map(s=>[s.source,s.target,s.edge_id]));
  function preset(w:number,g:number,h:number){setMode('scenario');setWind(w);setGust(g);setWave(h);}
  return <section className="route-planner">
    <div className="route-controls card"><div className="section-title"><h2>Маршрут и условия</h2><span>{mode==='scenario'?'СЦЕНАРИЙ':'ПРОГНОЗ'}</span></div>
      <div className="route-inputs"><label>Порт отправления<select value={source} onChange={e=>setSource(e.target.value)}>{ports.map(p=><option key={p}>{p}</option>)}</select></label>
        <label>Пункт назначения<select value={target} onChange={e=>setTarget(e.target.value)}>{ports.map(p=><option key={p}>{p}</option>)}</select></label>
        <label>Сезон<select value={season} onChange={e=>setSeason(e.target.value as RouteRequest['season'])}>{seasons.map((s,i)=><option value={s} key={s}>{['Зима','Весна','Лето','Осень'][i]}</option>)}</select></label>
        <button className="primary" onClick={onOpenWeather}>Выбрать прогноз ↗</button></div>
      <fieldset className="transport-options"><legend>Виды транспорта</legend>{(['ship','rail','road'] as const).map((value,i)=><label key={value}><input type="checkbox" checked={transportModes.includes(value)} onChange={e=>setTransportModes(old=>e.target.checked?[...old,value]:old.filter(item=>item!==value))}/>{['Море','Ж/д','Авто'][i]}</label>)}</fieldset>
      {transportModes.includes('road')&&<div className="route-inputs"><label>Загруженность дорог · %<input type="number" min="0" max="100" value={road.congestion_percent} onChange={e=>setRoad({...road,congestion_percent:Number(e.target.value)})}/></label><label>Дорожные условия · 0–10<input type="number" min="0" max="10" step="0.1" value={road.condition_severity} onChange={e=>setRoad({...road,condition_severity:Number(e.target.value)})}/></label><label>Ожидание на одном КПП · ч<input type="number" min="0" max="168" step="0.5" value={road.border_wait_hours} onChange={e=>setRoad({...road,border_wait_hours:Number(e.target.value)})}/></label><label>Автодороги<select value={String(road.closed)} onChange={e=>setRoad({...road,closed:e.target.value==='true'})}><option value="false">Доступны</option><option value="true">Закрыты · сценарий</option></select></label></div>}
      <p className="hint">Дорожные условия и очереди задаются вручную. Автокоридор Махачкала — Энзели показан через Грузию и Азербайджан: ожидание учитывается на трёх границах. Допуск к перевозке и работу КПП нужно подтверждать отдельно.</p>
      <div className="port-buttons"><button aria-pressed={mode==='scenario'&&wind===4} onClick={()=>preset(4,6,1)}>Спокойно</button><button aria-pressed={mode==='scenario'&&wind===14} onClick={()=>preset(14,18,2)}>Усиление ветра</button><button aria-pressed={mode==='scenario'&&wind===22} onClick={()=>preset(22,27,3.2)}>Шторм · сценарий</button>
        {incomingWeather&&<button aria-pressed={mode==='openweather'} onClick={()=>setMode('openweather')}>Использовать OpenWeather</button>}</div>
      {mode==='scenario'?<div className="route-inputs"><label>Ветер · м/с<input type="number" min="0" max="100" step="0.1" value={wind} onChange={e=>setWind(Number(e.target.value))}/></label><label>Порывы · м/с<input type="number" min="0" max="150" step="0.1" value={gust} onChange={e=>setGust(Number(e.target.value))}/></label><label>Волны · м<input type="number" min="0" max="30" step="0.1" value={wave} onChange={e=>setWave(Number(e.target.value))}/></label><p className="hint">Ручной сценарий для демонстрации. Изменение условий автоматически пересчитывает маршрут.</p></div>:
        <p className="hint">OpenWeather · {incomingWeather?.latitude}, {incomingWeather?.longitude} · {incomingWeather?.forecast_at.replace('T',' ')}. Проверка каждые 60 с; кэш провайдера на сервере — до 10 минут. Применяется один выбранный прогноз ко всему маршруту.</p>}
    </div>
    <div className="route-workspace"><section className="card map-card"><div className="section-title"><h2>Схема перевозки</h2><span>{busy?'ПЕРЕСЧЁТ':route?'ОТВЕТ API':'НЕТ РАСЧЁТА'}</span></div>
      <div className="port-buttons"><button aria-pressed={criterion==='fastest'} onClick={()=>setCriterion('fastest')}>Самый быстрый</button><button aria-pressed={criterion==='eco'} onClick={()=>setCriterion('eco')}>Минимум CO₂</button></div>
      {busy&&route&&<p className="warning" role="status">Условия изменились или обновляются. Пока показан предыдущий результат.</p>}
      <RouteMap route={displayed} previous={oldDisplayed} weather={route?.weather??null}/>
    </section><section className="card route-summary" aria-live="polite"><div className="section-title"><h2>Состояние поездки</h2><button onClick={()=>setRevision(v=>v+1)} disabled={busy}>Обновить</button></div>
      {error&&<p role="alert" className="error">{error}</p>}
      {busy&&<p>Пересчитываем маршрут…</p>}
      {route&&displayed&&<>
        <p className={route.weather.sea_restricted?'warning':'route-ok'}>{route.weather.sea_restricted?'Морские участки исключены по правилу MVP':'Морские участки доступны по правилу MVP'}</p>
        {route.weather.reasons.length>0&&<p>{route.weather.reasons.join('; ')}. Рассчитана доступная альтернатива.</p>}
        <p className="hint">Условия расчёта: {route.weather.source==='openweather'?'OpenWeather':'ручной сценарий'} · ветер {route.weather.wind_speed_ms??'—'} м/с · порывы {route.weather.wind_gust_ms??'—'} м/с · волны {route.weather.wave_height_m??'нет данных'}{route.weather.wave_height_m!==null?' м':''}.</p>
        <div className="route-line">{displayed.nodes.join(' → ')}</div>
        <div className="metrics"><article><small>ВРЕМЯ В ПУТИ</small><strong>{fmt(displayed.total_time_hours)} <em>ч</em></strong></article><article><small>CO₂ / 1 TEU</small><strong>{fmt(displayed.total_co2_emissions_kg)} <em>кг</em></strong></article></div>
        <div className="detail"><p>Стоимость <b>${displayed.total_cost_usd.toLocaleString()}</b></p><p>Прогноз задержек <b>{fmt(displayed.total_delay_hours)} ч</b></p></div>
        {oldDisplayed&&<p className="route-change">{changedPath?'Изменился путь или вид транспорта.':'Путь и виды транспорта сохранены.'} Время: {delta(displayed.total_time_hours-oldDisplayed.total_time_hours)} ч; стоимость: {delta(displayed.total_cost_usd-oldDisplayed.total_cost_usd)} USD; CO₂: {delta(displayed.total_co2_emissions_kg-oldDisplayed.total_co2_emissions_kg)} кг к предыдущему расчёту.</p>}
        <ol className="route-legs">{displayed.segments.map((s,i)=><li key={`${s.source}-${s.target}-${i}`}><b>{s.transport_mode==='ship'?'Море':s.transport_mode==='road'?'Авто':'Ж/д'} · {s.source} → {s.target}</b><small>{fmt(s.expected_time_hours)} ч, в том числе задержка {fmt(s.delay_hours)} ч{(s.border_wait_hours??0)>0?`, из них КПП: ${fmt(s.border_wait_hours!)} ч`:s.transport_mode==='road'?', без погранперехода':''}</small></li>)}</ol>
        {displayed.segments.length===0&&<p>Отправление и назначение совпадают: перевозка не требуется.</p>}
        <p className="hint">Проверено: {checkedAt}{route.weather.retrieved_at?` · Прогноз получен: ${route.weather.retrieved_at}`:''}.</p>
        <details><summary>JSON для интеграции</summary><pre>{JSON.stringify(route,null,2)}</pre></details>
      </>}
      <p className="hint">Правило MVP: ветер/порывы ≥ 20 м/с или волны &gt; 2,5 м исключают морские рёбра. Это демонстрационная политика, не официальное закрытие портов. Задержки предсказывает модель на синтетических данных. OpenWeather не предоставляет здесь высоту волн.</p>
    </section></div>
  </section>;
}

import {WeatherDatasetPanel} from './WeatherDatasetPanel';
import {useEffect, useRef, useState} from 'react';
import axios from 'axios';
import * as L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {api} from '../api/client';
import type {ForecastRouteWeather, WeatherForecast} from '../api/client';
import {addRussianBasemap} from '../maps/russianBasemap';

// Approximate city control points, not berth coordinates or a navigation chart.
const locations = [
  {name:'Астрахань', lat:46.35, lon:48.04},
  {name:'Оля', lat:45.8, lon:47.54},
  {name:'Махачкала', lat:42.98, lon:47.5},
  {name:'Энзели', lat:37.47, lon:49.46},
  {name:'Амирабад', lat:36.85, lon:53.37},
];

export function WeatherMap({onApplyWeather}:{onApplyWeather:(weather:ForecastRouteWeather)=>void}) {
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map|null>(null);
  const badge = useRef<L.Marker|null>(null);
  const activeRequest = useRef<AbortController|null>(null);
  const loadRef = useRef<(lat:number,lon:number,name?:string)=>void>(()=>{});
  const [point,setPoint]=useState({lat:42,lon:50,name:'Точка в Каспии'});
  const [forecast,setForecast]=useState<WeatherForecast|null>(null);
  const [slotIndex,setSlotIndex]=useState(0);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [tileError,setTileError]=useState(false);
  const slot=forecast?.forecasts[slotIndex];

  async function load(lat:number,lon:number,name='Выбранная точка') {
    activeRequest.current?.abort();
    const controller=new AbortController(); activeRequest.current=controller;
    setPoint({lat,lon,name});setForecast(null);setSlotIndex(0);setError('');setBusy(true);
    badge.current?.remove(); badge.current=null;
    map.current?.panTo([lat,lon]);
    try {
      const {data}=await api.get<WeatherForecast>('/api/v1/weather/forecast',{
        params:{latitude:lat,longitude:lon},signal:controller.signal,
      });
      if (!controller.signal.aborted) setForecast(data);
    } catch(err) {
      if(controller.signal.aborted) return;
      if(axios.isAxiosError(err)) {
        const detail=err.response?.data?.detail;
        setError(err.response ? `API ${err.response.status}: ${typeof detail==='string'?detail:'Не удалось получить прогноз.'}`
          : 'Бэкенд недоступен. Запустите API на порту 8000 и проверьте его адрес. Прогноз не подменяется демо-данными.');
      } else setError('Не удалось получить прогноз. Повторите запрос.');
    } finally {if(!controller.signal.aborted)setBusy(false);}
  }
  loadRef.current=load;

  useEffect(()=>{
    if(!host.current)return;
    const instance=L.map(host.current,{scrollWheelZoom:false}).setView([41.5,50.5],5);
    map.current=instance;
    const removeBasemap=addRussianBasemap(instance,()=>setTileError(true));
    locations.forEach(place=>{
      const icon=L.divIcon({className:'port-pin',html:'<span>●</span>',iconSize:[24,24],iconAnchor:[12,12]});
      L.marker([place.lat,place.lon],{icon,title:place.name,keyboard:true})
        .bindTooltip(place.name,{direction:'top'})
        .on('click',()=>loadRef.current(place.lat,place.lon,place.name)).addTo(instance);
    });
    instance.on('click',(event:L.LeafletMouseEvent)=>loadRef.current(
      Number(event.latlng.lat.toFixed(4)),Number(event.latlng.lng.toFixed(4)),
    ));
    const observer=new ResizeObserver(()=>instance.invalidateSize());observer.observe(host.current);
    return ()=>{activeRequest.current?.abort();observer.disconnect();removeBasemap();instance.remove();map.current=null;};
  },[]);

  useEffect(()=>{
    if(!slot||!forecast||!map.current)return;
    badge.current?.remove();
    // textContent prevents provider strings from being interpreted as HTML.
    const content=document.createElement('div');content.className='weather-pin-content';
    content.textContent=`${slot.temperature_c.toFixed(1)} °C · ${slot.wind_speed_ms.toFixed(1)} м/с`;
    const icon=L.divIcon({className:'weather-pin',html:content,iconSize:[180,35],iconAnchor:[90,46]});
    badge.current=L.marker([forecast.location.latitude,forecast.location.longitude],{icon,interactive:false,zIndexOffset:1000}).addTo(map.current);
    return ()=>{badge.current?.remove();badge.current=null;};
  },[slot,forecast]);

  return <section className="weather-layout"><WeatherDatasetPanel/>
    <section className="card map-card"><div className="section-title"><h2>Каспий · погодная обстановка</h2><span>ПРОГНОЗ ПО ТОЧКЕ</span></div>
      <div className="port-buttons">{locations.map(place=><button key={place.name} onClick={()=>load(place.lat,place.lon,place.name)}>{place.name}</button>)}</div>
      <div ref={host} className="caspian-map" aria-label="Карта Каспийского моря. Выберите порт кнопкой или точку кликом."/>
      {tileError&&<p className="warning" role="status">Часть картографических тайлов недоступна. Выбор порта и запрос погоды продолжают работать.</p>}
      <p className="hint">Нажмите на карту или выберите порт. Метки портов — приблизительные контрольные точки. Значения относятся к выбранному времени прогноза, а не к текущему наблюдению. Это не навигационная карта.</p>
    </section>
    <section className="card weather-panel"><div className="section-title"><h2>{point.name}</h2><span>{forecast?'OPENWEATHER':'НЕТ ДАННЫХ'}</span></div>
      <form onSubmit={event=>{event.preventDefault();void load(point.lat,point.lon);}}>
        <div className="pair"><label>Широта<input type="number" value={point.lat} step="any" min="-90" max="90" required onChange={e=>{setPoint({...point,lat:Number(e.target.value)});setForecast(null);}}/></label>
        <label>Долгота<input type="number" value={point.lon} step="any" min="-180" max="180" required onChange={e=>{setPoint({...point,lon:Number(e.target.value)});setForecast(null);}}/></label></div>
        <button className="primary" disabled={busy}>{busy?'Получаем прогноз…':'Обновить прогноз'} <span>↗</span></button>
      </form>
      {error&&<p className="error" role="alert">{error}</p>}
      {forecast&&slot?<>
        <label className="forecast-select">Время прогноза · UTC<select value={slotIndex} onChange={e=>setSlotIndex(Number(e.target.value))}>{forecast.forecasts.map((item,index)=><option key={item.valid_at} value={index}>{item.valid_at.replace('T',' ').replace(/Z|\+00:00/,' UTC')}</option>)}</select></label>
        <div className="metrics"><article><small>ТЕМПЕРАТУРА</small><strong>{slot.temperature_c.toFixed(1)} <em>°C</em></strong></article><article><small>ВЕТЕР</small><strong>{slot.wind_speed_ms.toFixed(1)} <em>м/с</em></strong></article></div>
        <p>{slot.description}</p><div className="detail"><p>Порывы <b>{slot.wind_gust_ms==null?'Нет данных':`${slot.wind_gust_ms.toFixed(1)} м/с`}</b></p><p>Вероятность осадков <b>{Math.round(slot.precipitation_probability*100)}%</b></p><p>Дождь за 3 часа <b>{slot.rain_3h_mm} мм</b></p><p>Высота волн <b>Нет данных</b></p></div>
        <p className="hint">Получено: {forecast.retrieved_at.replace('T',' ')} · {forecast.cached?'кэш':'новый запрос'}. <a href="https://openweathermap.org/api/forecast5" target="_blank" rel="noreferrer">Источник: OpenWeather</a>. До 5 суток, шаг 3 часа. Собственная ML-модель прогнозирует задержки, не погоду.</p>
        <button className="primary" onClick={()=>onApplyWeather({source:'openweather',latitude:forecast.location.latitude,longitude:forecast.location.longitude,forecast_at:slot.valid_at})}>Применить к маршруту →</button>
        <details><summary>JSON прогноза</summary><pre>{JSON.stringify(forecast,null,2)}</pre></details>
      </>:!busy&&!error&&<div className="empty"><h3>Выберите точку на карте</h3><p>Прогноз появится после запроса.<br/>Отсутствующие данные не заменяются нулями.</p></div>}
    </section>
  </section>;
}

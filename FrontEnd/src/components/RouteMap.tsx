import {useEffect, useRef, useState} from 'react';
import * as L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type {RouteDetails, WeatherImpact} from '../api/client';
import {terminals,seaGates,segmentGeometry} from '../data/routeGeometry';
import type {Checkpoint} from '../api/voyages';
import {addRussianBasemap} from '../maps/russianBasemap';

export function RouteMap({route,previous,weather,checkpoints=[],offline=false,vessel}:{route:RouteDetails|null;previous:RouteDetails|null;weather:WeatherImpact|null;checkpoints?:Checkpoint[];offline?:boolean;vessel?:{latitude:number;longitude:number;label:string}|null}) {
  const host=useRef<HTMLDivElement>(null);
  const map=useRef<L.Map|null>(null);
  const layers=useRef<L.LayerGroup|null>(null);
  const [tileError,setTileError]=useState(false);
  useEffect(()=>{
    if(!host.current)return;
    setTileError(false);
    const instance=L.map(host.current,{scrollWheelZoom:false}).setView([41.5,49],5);
    map.current=instance;
    let removeBasemap=()=>{};
    if(offline){
      instance.getContainer().style.background='#e5e2d8';
      void import('../data/caspian-water.json').then(({default:water})=>{
        if(map.current!==instance)return;
        const rings=water.coordinates.map(ring=>ring.map(([lon,lat]):L.LatLngTuple=>[lat,lon]));
        L.polygon(rings,{color:'#8aadb3',weight:1,fillColor:'#cce7ee',fillOpacity:1,interactive:false}).addTo(instance).bringToBack();
      });
      instance.attributionControl.addAttribution('Локальная схема Natural Earth · public domain');
    }else removeBasemap=addRussianBasemap(instance,()=>setTileError(true));
    layers.current=L.layerGroup().addTo(instance);
    const observer=new ResizeObserver(()=>instance.invalidateSize());observer.observe(host.current);
    return ()=>{observer.disconnect();removeBasemap();instance.remove();map.current=null;layers.current=null;};
  },[offline]);
  useEffect(()=>{
    const group=layers.current, instance=map.current;
    if(!group||!instance)return;
    group.clearLayers();
    for(const [name,position] of Object.entries(terminals)) {
      const label=document.createElement('span');label.textContent=name;
      L.circleMarker(position,{radius:6,color:'#133c3d',fillColor:'#fff',fillOpacity:1})
        .bindTooltip(label,{permanent:true,direction:'top'}).addTo(group);
    }
    if(previous) for(const leg of previous.segments) {
      if(segmentGeometry(leg).length) L.polyline(segmentGeometry(leg),
        {color:'#697878',weight:8,opacity:0.4,dashArray:'3 9'}).addTo(group);
    }
    if(route) for(const leg of route.segments) {
      const points=segmentGeometry(leg);
      if(!points.length)continue;
      const label=document.createElement('span');
      label.textContent=`${leg.source} → ${leg.target} · ${leg.transport_mode==='ship'?'море':leg.transport_mode==='road'?'авто':'ж/д'} · ${leg.expected_time_hours.toFixed(1)} ч`;
      L.polyline(points,{
        color:leg.transport_mode==='ship'?'#007f9c':leg.transport_mode==='road'?'#7453b5':'#c06b19',weight:4,
        dashArray:leg.transport_mode==='rail'?'10 7':undefined,
      }).bindTooltip(label,{sticky:true}).addTo(group);
    }
    const seaTerminals=new Set([...(route?.segments??[]),...(previous?.segments??[])]
      .filter(leg=>leg.transport_mode==='ship').flatMap(leg=>[leg.source,leg.target]));
    for(const name of seaTerminals){
      if(!seaGates[name])continue;
      const label=document.createElement('span');label.textContent=`${name} · морской подход (схема)`;
      L.circleMarker(seaGates[name],{radius:5,color:'#007f9c',fillColor:'#fff',fillOpacity:1})
        .bindTooltip(label).addTo(group);
    }
    if(weather?.location){
      const label=document.createElement('span');
      label.textContent=`Погода: ветер ${weather.wind_speed_ms} м/с; ${weather.forecast_at}`;
      L.circleMarker([weather.location.latitude,weather.location.longitude],{radius:11,color:weather.sea_restricted?'#ba3a30':'#367d56'})
        .bindTooltip(label).addTo(group);
    }
    for(const cp of checkpoints){
      const label=document.createElement('span');
      label.textContent=`${cp.name} · прохождение ${cp.passage_at} · ${cp.status==='outside_horizon'?'прогноз недоступен':`ветер ${cp.wind_speed_ms} м/с, слот ${cp.forecast_at??'сценарий'}`}`;
      L.circleMarker([cp.latitude,cp.longitude],{radius:8,color:cp.status==='outside_horizon'?'#a36b11':'#367d56',weight:2,fillOpacity:0.6})
        .bindTooltip(label).addTo(group);
    }
    if(vessel){
      const text=document.createElement('span');text.textContent=vessel.label;
      L.circleMarker([vessel.latitude,vessel.longitude],{radius:9,color:'#123a43',fillColor:'#d4e9a7',fillOpacity:1,weight:3})
        .bindTooltip(text,{permanent:true,direction:'right'}).addTo(group);
    }
    if(route){
      const points=[...route.segments.flatMap(segmentGeometry),
        ...route.nodes.map(name=>terminals[name]).filter(point=>!!point)];
      if(points.length>1)instance.fitBounds(L.latLngBounds(points),{padding:[50,50],maxZoom:7});
      else if(points.length===1)instance.setView(points[0],7);
    }
  },[route,previous,weather,checkpoints,offline,vessel]);
  return <><div ref={host} className="caspian-map route-map" aria-label="Схема маршрута на карте Каспия"/>
    <div className="map-legend"><span className="sea">━ Море</span><span className="rail">┄ Ж/д</span><span style={{color:'#7453b5'}}>━ Авто</span><span>┄ Серый: план для сравнения</span><span>● Погодные точки</span></div>
    {tileError&&<p className="warning">Подложка карты недоступна. Схема связей и список участков доступны.</p>}
    <p className="hint">Морские линии проходят через точки в акватории; кружки обозначают морские подходы отдельно от городов. Речной подход к Астрахани через дельту не показан. Это схема перевозки; автолинии — сохранённые дороги OpenStreetMap/OSRM без проверки ограничений для грузовиков. Точные фарватеры и ж/д трассы требуют отдельных данных.</p></>;
}

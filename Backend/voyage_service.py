"""Evaluate all simple itineraries of the small MVP graph at their passage times.

Time-dependent weather restrictions and periodic departures are not FIFO edge
weights. Enumerating this four-terminal graph avoids applying static Dijkstra
weights to a schedule-dependent problem. Legacy Dijkstra remains available.
"""
from __future__ import annotations
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import networkx as nx
from routing_engine import DelayPredictor, PredictionError, RouteNotFoundError, _EdgeAttributes
from route_weather import resolve_route_weather
from weather_service import Coordinates, OpenWeatherService, WeatherForecast
from voyage_models import (VoyageRequest,VoyageConditions,VoyageSnapshot,TimedRoute,TimedLeg,Checkpoint,DelayReason)

PORTS:dict[str,tuple[float,float]]={'Астрахань':(46.35,48.04),'Махачкала':(42.98,47.5),'Энзели':(37.47,49.46),'Решт':(37.28,49.58)}
GATES={'Астрахань':(44.95,49.25),'Махачкала':(42.99,47.6),'Энзели':(37.53,49.48)}

def control_points(source:str,target:str,mode:str)->list[tuple[str,float,float,float]]:
    start=GATES[source] if mode=='ship' else PORTS[source]
    end=GATES[target] if mode=='ship' else PORTS[target]
    middle=[]
    if mode=='ship':
        middle=[('Центральный Каспий',41.2,51.2,0.5)]
    elif mode=='road' and {source,target}=={'Махачкала','Энзели'}:
        # Fractions of the saved western road itinerary, approximate progress.
        middle=[('Тбилиси',41.72,44.8,0.35),('Баку',40.4,49.85,0.72)]
        if source=='Энзели': middle=[(n,lat,lon,1-f) for n,lat,lon,f in reversed(middle)]
    return [(source,*start,0.0),*middle,(target,*end,1.0)]

class BlockedByStorm(Exception):
    pass

class UnstableETA(Exception):
    pass

def calculate_voyage(request:VoyageRequest,conditions:VoyageConditions,graph:nx.MultiDiGraph,
                     predictor:DelayPredictor,weather:OpenWeatherService|None)->VoyageSnapshot:
    network=graph.copy()
    network.remove_edges_from([(u,v,k) for u,v,k,d in network.edges(keys=True,data=True)
        if d['transport_mode'] not in request.transport_modes or (d['transport_mode']=='road' and conditions.road.closed)])
    if request.source!=request.target and not nx.has_path(network,request.source,request.target):
        raise RouteNotFoundError('No itinerary for the selected transport modes and road restrictions.')
    # Fetch unique locations once, concurrently; provider cache is shared across requests.
    forecasts:dict[tuple[float,float],WeatherForecast]={}
    if conditions.weather_mode=='openweather' and request.source!=request.target:
        if weather is None: raise ValueError('Weather service is not initialized.')
        points=sorted({(lat,lon) for u,v,d in network.edges(data=True)
                       for _,lat,lon,_ in control_points(u,v,d['transport_mode'])})
        with ThreadPoolExecutor(max_workers=4) as pool:
            values=pool.map(lambda p:weather.forecast(Coordinates(latitude=p[0],longitude=p[1])),points)
            forecasts=dict(zip(points,values))
    model_cache:dict[tuple[tuple[str,object],...],float]={}
    def predict(features:dict[str,float|str])->float:
        key=tuple(sorted(features.items()))
        if key not in model_cache:
            try:
                value=predictor.predict_delay(features)
                if isinstance(value,(bool,str)) or not math.isfinite(value) or value<0: raise ValueError('Invalid prediction')
                model_cache[key]=float(value)
            except Exception as exc: raise PredictionError('Voyage delay prediction failed.') from exc
        return model_cache[key]

    def sample(u:str,v:str,mode:str,start:datetime,duration:float)->list[Checkpoint]:
        result=[]
        for name,lat,lon,fraction in control_points(u,v,mode):
            passage=start+timedelta(hours=duration*fraction)
            if conditions.weather_mode=='scenario':
                impact=resolve_route_weather(conditions.scenario,0,None)
                result.append(Checkpoint(name=name,latitude=lat,longitude=lon,passage_at=passage,
                    wind_speed_ms=impact.wind_speed_ms,wind_gust_ms=impact.wind_gust_ms,wave_height_m=impact.wave_height_m,
                    severity=impact.severity,status='scenario'))
            else:
                forecast=forecasts[(lat,lon)]
                slot=min(forecast.forecasts,key=lambda item:abs((item.valid_at-passage).total_seconds()))
                if abs((slot.valid_at-passage).total_seconds())>5400:
                    result.append(Checkpoint(name=name,latitude=lat,longitude=lon,passage_at=passage,status='outside_horizon'))
                else:
                    peak=max(slot.wind_speed_ms,slot.wind_gust_ms or 0)
                    result.append(Checkpoint(name=name,latitude=lat,longitude=lon,passage_at=passage,
                        forecast_at=slot.valid_at,retrieved_at=forecast.retrieved_at,wind_speed_ms=slot.wind_speed_ms,
                        wind_gust_ms=slot.wind_gust_ms,severity=min(10,peak/25*10),status='forecast'))
        return result

    def evaluate(path:list[tuple[str,str,str|int]])->TimedRoute:
        now=request.departure_at;segments=[]
        for u,v,key in path:
            attr=_EdgeAttributes.model_validate(network[u][v][key]);mode=attr.transport_mode
            reasons=[];wait=0.0
            schedule=next((s for s in request.connections if s.terminal==u and s.transport_mode==mode),None)
            if schedule:
                ready=now+timedelta(hours=schedule.handling_hours)
                late=max(0,(ready-schedule.first_departure_at).total_seconds()/3600)
                departures=math.ceil(late/schedule.interval_hours)
                next_departure=schedule.first_departure_at+timedelta(hours=departures*schedule.interval_hours)
                wait=(next_departure-now).total_seconds()/3600
                code='missed_connection' if departures else 'connection_wait'
                reasons.append(DelayReason(code=code,hours=wait,message=(
                    f'Пропущена стыковка в {u}; следующий {mode}: {next_departure.isoformat()}' if departures else
                    f'Ожидание отправления {mode} в {u}: {next_departure.isoformat()}')))
            start=now+timedelta(hours=wait)
            congestion=conditions.port_congestion.get(v,attr.port_congestion)
            border=conditions.road.border_wait_hours*network[u][v][key].get('border_crossings',0) if mode=='road' else 0.0
            base_features:dict[str,float|str]={
                'weather_severity':0.0,'port_congestion':congestion,'transport_mode':mode,
                'season':('winter','spring','summer','autumn')[(start.astimezone(timezone.utc).month%12)//3],
                'road_congestion_percent':conditions.road.congestion_percent if mode=='road' else 0.0,
                'road_condition_severity':conditions.road.condition_severity if mode=='road' else 0.0,
            }
            delay=0.0;converged=False
            for _ in range(6):
                checkpoints=sample(u,v,mode,start,attr.base_time_hours+delay+border)
                if mode=='ship' and any(max(cp.wind_speed_ms or 0,cp.wind_gust_ms or 0)>=20 or (cp.wave_height_m or 0)>2.5 for cp in checkpoints):
                    bad=next(cp for cp in checkpoints if max(cp.wind_speed_ms or 0,cp.wind_gust_ms or 0)>=20 or (cp.wave_height_m or 0)>2.5)
                    raise BlockedByStorm(f'Штормовое правило MVP: {u} → {v}, {bad.name} ({bad.latitude}, {bad.longitude}), прохождение {bad.passage_at.isoformat()}; ветер {bad.wind_speed_ms}, порывы {bad.wind_gust_ms} м/с, волны {bad.wave_height_m} м. Морской вариант исключён.')
                features={**base_features,'weather_severity':max((cp.severity or 0 for cp in checkpoints),default=0)}
                next_delay=predict(features)
                if abs(delay-next_delay)<0.02:
                    converged=True;delay=next_delay;break
                delay=next_delay
            if not converged:
                raise UnstableETA(f"Не удалось стабилизировать погодный ETA для {u} → {v} за 6 итераций; вариант не выбран.")
            checkpoints=sample(u,v,mode,start,attr.base_time_hours+delay+border)
            if max((cp.severity or 0 for cp in checkpoints),default=0) != features["weather_severity"]:
                raise UnstableETA(f"Погода изменилась на границе временного слота {u} → {v}; вариант не выбран.")
            # The final timestamps must also be checked for restrictions after ETA shifts.
            if mode=='ship' and any(max(cp.wind_speed_ms or 0,cp.wind_gust_ms or 0)>=20 or (cp.wave_height_m or 0)>2.5 for cp in checkpoints):
                raise BlockedByStorm(f'Штормовое правило MVP: морской участок {u} → {v} исключён после уточнения ETA.')
            if features['weather_severity']:
                uplift=max(0,delay-predict({**features,'weather_severity':0.0}))
                reasons.append(DelayReason(code='weather',hours=uplift,message=f'Погода на участке {u} → {v}: интенсивность {features["weather_severity"]:.1f}/10; оценка фактора относительно спокойной погоды.'))
            if congestion>85:
                uplift=max(0,predict(features)-predict({**features,'port_congestion':0.0}))
                reasons.append(DelayReason(code='port_congestion',hours=uplift,message=f'Перегрузка терминала {v}: {congestion:.0f}% (сценарные данные).'))
            if border: reasons.append(DelayReason(code='border',hours=border,message=f'Ожидание на границах: {border:.1f} ч.'))
            if any(cp.status=='outside_horizon' for cp in checkpoints):
                reasons.append(DelayReason(code='forecast_gap',message='Часть времени прохождения вне горизонта OpenWeather; ETA имеет неполное погодное покрытие.'))
            total=attr.base_time_hours+delay+border+wait
            arrival=now+timedelta(hours=total)
            segments.append(TimedLeg(source=u,target=v,edge_id=key,transport_mode=mode,
                base_time_hours=attr.base_time_hours,delay_hours=delay+border+wait,expected_time_hours=total,
                border_wait_hours=border,cost_usd=attr.cost_usd,co2_emissions_kg=attr.co2_emissions_kg,
                departure_at=start,arrival_at=arrival,connection_wait_hours=wait,checkpoints=checkpoints,
                features_used=features,reasons=reasons,eta_converged=converged))
            now=arrival
        reasons=[r for leg in segments for r in leg.reasons]
        return TimedRoute(nodes=[request.source,*[v for _,v,_ in path]],segments=segments,
            total_base_time_hours=sum(s.base_time_hours for s in segments),total_delay_hours=sum(s.delay_hours for s in segments),
            total_time_hours=sum(s.expected_time_hours for s in segments),total_cost_usd=sum(s.cost_usd for s in segments),
            total_co2_emissions_kg=sum(s.co2_emissions_kg for s in segments),departure_at=request.departure_at,eta=now,
            coverage='partial' if any(r.code=='forecast_gap' for r in reasons) else 'complete',reasons=reasons)
    paths=[[]] if request.source==request.target else nx.all_simple_edge_paths(network,request.source,request.target,cutoff=3)
    routes=[];excluded=[]
    for path in paths:
        try: routes.append(evaluate(path))
        except UnstableETA as exc:
            excluded.append(DelayReason(code="forecast_gap",message=str(exc)))
        except BlockedByStorm as exc:
            if str(exc) not in {r.message for r in excluded}: excluded.append(DelayReason(code='storm_restriction',message=str(exc)))
    if not routes: raise RouteNotFoundError('No stable itinerary is available under weather restrictions at the passage times.')
    fastest=min(routes,key=lambda route:(route.total_time_hours,route.total_cost_usd))
    eco=min(routes,key=lambda route:(route.total_co2_emissions_kg,route.total_time_hours))
    alternatives:dict[tuple[str,str],DelayReason]={}
    for route in routes:
        if route is fastest:
            continue
        for reason in route.reasons:
            if reason.code in ('missed_connection','port_congestion'):
                alternatives[(reason.code,reason.message)] = DelayReason(
                    code=reason.code,hours=reason.hours,message='На альтернативном варианте: '+reason.message)
    return VoyageSnapshot(calculated_at=datetime.now(timezone.utc),fastest=fastest,eco=eco,
                          excluded_reasons=excluded,alternative_reasons=list(alternatives.values()))

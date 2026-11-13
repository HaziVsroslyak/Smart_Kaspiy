"""Synthetic JIT strategies using real fitted estimators, no network access."""
from __future__ import annotations
import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from random import Random
from uuid import uuid4
from demo_contracts import (DemoCatalog, DemoScenario, DemoRunRequest, DemoResult, StrategyResult,
    DemoSegment, DemoCheckpoint, DemoEvent, DemoTimelinePoint, PredictionTrace)
from demo_models import DemoModels
from jit_optimizer import calculate_esg, DEFAULT_FUEL_COEFFICIENT, CO2_FACTOR, MIN_SPEED_KNOTS
from voyage_models import VoyageResponse
from weather_data.contracts import Dataset, ResolveRequest
from weather_data.service import resolve

ANCHOR = datetime(2026, 11, 12, 0, tzinfo=timezone.utc)

@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    description: str
    wind: float = 4
    wave: float | None = 0.6
    congestion: float = 20
    queue: float = 0
    service: float = 2
    berths: int = 1
    remaining: float = 0
    first_slot: float = 48
    interval: float = 12
    border_hours: float = 4
    origin: str = 'Махачкала'
    distance_nm: float = 360
    speed: float = 10
    handling: float = 2
    last_mode: str | None = "rail"
    terminal_periodic: bool = True
    season: str = 'Autumn'
    road_available: bool = True

SCENARIOS = (
    Scenario('calm','Штиль и свободный порт','Готовность терминала не ограничивает прибытие. Замедление не требуется.'),
    Scenario('berth_queue','Очередь на причал','ML оценивает готовность терминала; JIT снижает скорость и ожидание на якоре.',queue=25,congestion=80,remaining=2,first_slot=65),
    Scenario('minimum_speed','Минимальная скорость','Порт занят дольше максимального перехода при 6 узлах. Остаток ожидания сохраняется.',queue=50,service=3,congestion=98,first_slot=170),
    Scenario('storm','Шторм в пути','Синтетическое штормовое окно в центральной точке исключает морской вариант.',wind=22,wave=3.2),
    Scenario('missed_train','Пропущенный поезд','Усиление ветра сдвигает готовность груза за отправление поезда; следующий слот через 48 часов.',wind=14,wave=2.0,first_slot=38,interval=48),
    Scenario('truck_border','Очередь автомобилей на границе','Три погранперехода автокоридора имеют длительное ожидание. Сравните море–ж/д и авто.',queue=16,congestion=70,remaining=2,first_slot=55,border_hours=24),
    Scenario('winter_ice','Зимняя ледовая проводка','Модельный случай Астрахани с ледовой задержкой. Параметры условные.',origin='Астрахань',distance_nm=450,speed=9,first_slot=105,season='Winter'),
    Scenario('missing_weather','Нет данных о волнах','Система не заменяет неизвестные волны нулём и не обещает безопасный JIT.',wave=None),
)

def catalog(models: DemoModels) -> DemoCatalog:
    return DemoCatalog(scenarios=[DemoScenario(id=s.id,title=s.title,description=s.description) for s in SCENARIOS],model_report=models.report)

def slot_after(ready: float, first: float, interval: float) -> float:
    """A shipment exactly at departure catches that departure."""
    count=max(0,math.ceil((ready-first-1e-9)/interval))
    return first+count*interval

def run_scenario(identity: str, request: DemoRunRequest, models: DemoModels, *,
                 scene_override: Scenario | None = None, anchor: datetime = ANCHOR, weather_dataset: Dataset | None = None) -> DemoResult:
    try: scene=next(s for s in SCENARIOS if s.id==identity)
    except StopIteration: raise KeyError(identity) from None
    if scene_override is not None: scene=scene_override
    if request.wind_speed_ms is not None: scene=replace(scene,wind=request.wind_speed_ms)
    if request.wave_height_m is not None: scene=replace(scene,wave=request.wave_height_m)
    if request.port_congestion_percent is not None:
        # Scenario input maps congestion to queue length before ML, never to a ready-made answer.
        scene=replace(scene,congestion=request.port_congestion_percent,queue=max(0,(request.port_congestion_percent-20)*0.45))
    if request.dataset_id and weather_dataset is None:
        raise ValueError('Selected weather dataset must be loaded before calculation.')
    if weather_dataset is not None:
        if request.departure_at is None:
            raise ValueError('departure_at is required with a weather dataset.')
        if request.wind_speed_ms is not None or request.wave_height_m is not None:
            raise ValueError('Manual weather overrides cannot be combined with a dataset.')
        anchor=request.departure_at.astimezone(timezone.utc)
        if weather_dataset.kind=='archive' and anchor>datetime.now(timezone.utc):
            raise ValueError('Historical reanalysis cannot forecast a future departure.')
        scene=replace(scene,season=('Winter','Spring','Summer','Autumn')[(anchor.month%12)//3])
    used_weather={}
    origin=scene.origin
    traces:list[PredictionTrace]=[]
    def predict(target: str, features: dict[str, object]) -> float:
        trace=PredictionTrace.model_validate(models.predict(target,features))
        if trace not in traces: traces.append(trace)
        return trace.value_hours
    at=lambda hours:anchor+timedelta(hours=hours)
    readiness_features={'queue_units':scene.queue,'service_hours':scene.service,
        'active_berths':scene.berths,'remaining_service_hours':scene.remaining}
    berth_ready=predict('readiness',readiness_features)
    # Unseen episode noise is fixed per seed; it is never fed into the predictor.
    truth_ready=max(0,scene.remaining+scene.queue*scene.service/scene.berths+Random(request.seed).gauss(0,0.3))
    events=[DemoEvent(name='Решение диспетчера',at=anchor,detail='Входные признаки доступны до отправления. Только синтетика.'),
            DemoEvent(name='Прогноз готовности причала',at=at(berth_ready),detail=f'ML: {berth_ready:.2f} ч; скрытая симуляторная цель: {truth_ready:.2f} ч. Цель не передана модели.')]
    warnings=['Все погода, очереди, расписания и коэффициенты в этой демонстрации синтетические.',
        'Дистанции и доли времени контрольных точек — допущения демонстрации, не навигационные данные.',
        'Топливо учитывает движение по расстоянию; топливо на якоре, во время погодного простоя и вспомогательные потребители исключены.',
        'CO₂ мазута (тонны) и грузовой CO₂e (килограммы, условные EF) имеют разные границы и не складываются.',
        'Интервалы модели калиброваны на синтетике и не гарантируют точность на реальных рейсах.']
    if identity=='winter_ice': warnings.append('Астрахань используется как модельный ледовый случай; параметры речного канала и осадка не проверяются.')
    land_features={'weather_severity':scene.wind/2.5,'port_congestion':scene.congestion,
        'transport_mode':scene.last_mode or 'rail','season':scene.season.lower(),
        'road_congestion_percent':scene.congestion if scene.last_mode=='road' else 0.0,'road_condition_severity':1.0 if scene.last_mode=='road' else 0.0}
    rail_delay=predict('land',land_features) if scene.last_mode is not None else 0.0
    road_delay=predict('land',{**land_features,'transport_mode':'road','road_congestion_percent':scene.congestion,'road_condition_severity':1.0})
    # GLEC-like illustrative cargo factors, explicitly NOT certified coefficients.
    cargo_mass=20.0; sea_ef=0.022; rail_ef=0.018; road_ef=0.08
    def point_weather(hours: float) -> tuple[float,float|None]:
        if identity=='storm':
            # A localized synthetic storm, not global bad weather at every point.
            return (scene.wind,scene.wave) if 12<=hours<=72 else (4,0.6 if scene.wave is not None else None)
        return scene.wind,scene.wave
    def checkpoints(duration: float) -> list[DemoCheckpoint]:
        gate=(44.95,49.25) if origin=='Астрахань' else (42.99,47.6)
        positions=[(origin,*gate,0),('Центральный Каспий',41.2,51.2,0.5),('Энзели',37.53,49.48,1)]
        points=[]
        for name,lat,lon,f in positions:
            passage=at(duration*f)
            if weather_dataset is None:
                wind,wave=point_weather(duration*f)
            else:
                selected=resolve(weather_dataset,ResolveRequest(latitude=lat,longitude=lon,timestamp=passage))
                record=selected.record
                # Forecast issue times after the dispatch decision are unavailable inputs.
                available=record is not None and (record.issued_at is None or record.issued_at<=anchor)
                wind=record.wind_speed_ms if available else None
                wave=record.wave_height_m if available else None
                used_weather[f'{lat},{lon},{passage.isoformat()}']={
                    'latitude':lat,'longitude':lon,'passage_at':passage.isoformat(),
                    'resolution':selected.model_dump(mode='json'), 'available_at_departure':available}
            points.append(DemoCheckpoint(name=name,latitude=lat,longitude=lon,passage_at=passage,
                wind_speed_ms=wind,wave_height_m=wave))
        return points
    def movement(speed: float) -> tuple[float,list[DemoCheckpoint],str]:
        delay=0.0
        for _ in range(6):
            cps=checkpoints(scene.distance_nm/speed+delay)
            if any(cp.wave_height_m is None or cp.wind_speed_ms is None for cp in cps): return 0,cps,'insufficient_data'
            wind=max(cp.wind_speed_ms or 0 for cp in cps);wave=max(cp.wave_height_m or 0 for cp in cps)
            if wind>25 or wave<0.1 or wave>4.5: return 0,cps,'insufficient_data'
            if wind>=20 or wave>2.5: return 0,cps,'blocked'
            next_delay=predict('sea',{'departure_port':origin,'arrival_port':'Энзели','wind_speed_ms':wind,
                'wave_height_m':wave,'port_congestion_percent':scene.congestion,'season':scene.season})
            if abs(next_delay-delay)<0.001:return scene.distance_nm/speed+next_delay,checkpoints(scene.distance_nm/speed+next_delay),'ok'
            delay=next_delay
        return 0,cps,'insufficient_data'
    def segment(u:str,v:str,mode:str,base:float,delay:float,cost:float,co2:float,border:float=0) -> DemoSegment:
        return DemoSegment(source=u,target=v,edge_id=mode,transport_mode=mode,base_time_hours=base,
            delay_hours=delay,expected_time_hours=base+delay,border_wait_hours=border,cost_usd=cost,co2_emissions_kg=co2)
    def strategy(name: str, speed: float) -> StrategyResult:
        arrival,cps,status=movement(speed)
        label='Исходная скорость и ожидание' if name=='baseline' else 'JIT на том же маршруте'
        if status!='ok':
            return StrategyResult(id=name,label=label,status=status,nodes=[origin,'Энзели',*(['Решт'] if scene.last_mode is not None else [])],reason=(
                'Шторм в контрольной точке: морской вариант исключён. Безопасность важнее экономии топлива.' if status=='blocked' else
                'Не хватает погодных данных или ETA не стабилизирован. Рекомендация скорости не выдана.'),checkpoints=cps)
        waiting=max(0,berth_ready-arrival)
        handled=max(arrival,berth_ready)+scene.handling
        # Only the selected rail chain is required; trucks do not hold the vessel.
        connection=(slot_after(handled,scene.first_slot,scene.interval) if scene.terminal_periodic else max(handled,scene.first_slot)) if scene.last_mode is not None else handled
        missed=scene.terminal_periodic and scene.last_mode is not None and handled>scene.first_slot+1e-9
        connection_wait=connection-handled
        land_base=1.0 if scene.last_mode=="road" else 2.0
        eta=connection+land_base+rail_delay if scene.last_mode is not None else handled
        fuel=DEFAULT_FUEL_COEFFICIENT*scene.distance_nm*speed**2
        sea_cargo=cargo_mass*scene.distance_nm*1.852*sea_ef
        rail_cargo=cargo_mass*40*(road_ef if scene.last_mode=="road" else rail_ef) if scene.last_mode is not None else 0.0
        reasons=[f'Причал готов через {berth_ready:.1f} ч; ожидание судна {waiting:.1f} ч.']
        if missed:reasons.append(f'Пропущен поезд в +{scene.first_slot:g} ч; следующий слот +{connection:g} ч.' if scene.last_mode=='rail' else f'Пропущен автомобильный слот +{scene.first_slot:g} ч; следующий +{connection:g} ч.')
        if identity=='winter_ice':reasons.append('Морская модель учитывает синтетическую зимнюю ледовую задержку.')
        sea_base=scene.distance_nm/speed
        return StrategyResult(id=name,label=label,status='ok',reason=' '.join(reasons),nodes=[origin,'Энзели',*(['Решт'] if scene.last_mode is not None else [])],
            segments=[segment(origin,'Энзели','ship',sea_base,arrival-sea_base+waiting+(scene.handling if scene.last_mode is None else 0),500,sea_cargo),
                *([segment('Энзели','Решт',scene.last_mode,land_base,rail_delay+scene.handling+connection_wait,100,rail_cargo)] if scene.last_mode is not None else [])],
            speed_knots=speed,sea_arrival_at=at(arrival),berth_ready_at=at(berth_ready),handling_complete_at=at(handled),
            connection_at=at(connection),eta=at(eta),total_time_hours=eta,berth_wait_hours=waiting,connection_wait_hours=connection_wait,
            fuel_tonnes=fuel,co2_tonnes=fuel*CO2_FACTOR,cargo_co2e_kg=sea_cargo+rail_cargo,cost_usd=(600 if scene.last_mode is not None else 500)+waiting*5,
            remaining_wait_hours=waiting,checkpoints=cps,timeline=[DemoTimelinePoint(name=n,at=at(t)) for n,t in [
                ('Отправление',0),('Прибытие судна',arrival),('Начало обработки',max(arrival,berth_ready)),
                ('Груз готов',handled),('Отправление поезда' if scene.last_mode=='rail' else 'Готовность авто' if scene.last_mode=='road' else 'Завершение обработки',connection),('Доставка',eta)]])
    baseline=strategy('baseline',scene.speed)
    if weather_dataset is not None:
        candidates=[strategy('jit',scene.speed-(scene.speed-MIN_SPEED_KNOTS)*i/60) for i in range(61)]
        if baseline.status!='ok' or any(item.status=='insufficient_data' for item in candidates):
            jit=StrategyResult(id='jit',label='JIT',status='insufficient_data',nodes=baseline.nodes,
                reason='Не хватает покрытия погоды для сравнения скоростей; рекомендация не выдана.',checkpoints=baseline.checkpoints)
        else:
            feasible=[item for item in candidates if item.status=='ok' and item.eta<=baseline.eta
                      and (baseline.berth_wait_hours>0.001 or item.speed_knots==scene.speed)]
            jit=min(feasible,key=lambda item:item.fuel_tonnes) if feasible else strategy('jit',scene.speed)
            esg=calculate_esg(scene.distance_nm,scene.speed,jit.speed_knots)
            jit.fuel_saved_tonnes=esg['fuel_saved_tonnes'];jit.co2_saved_tonnes=esg['co2_saved_tonnes']
            jit.reason+=' Лучший допустимый из 61 проверенной скорости; глобальный оптимум не гарантируется.'
    elif baseline.status=='ok':
        original=(baseline.sea_arrival_at-anchor).total_seconds()/3600
        # Do not intentionally delay a free-port trip solely to fill a train wait.
        desired=max(original,berth_ready)
        # Preserve the baseline's chosen connection. Handling must finish by that slot.
        cutoff=(baseline.connection_at-anchor).total_seconds()/3600-scene.handling
        target=min(desired,cutoff)
        recommended=scene.speed
        if target>original+0.001:
            lo,hi=MIN_SPEED_KNOTS,scene.speed
            # Monotone transit within a stable synthetic weather regime; re-evaluate each candidate.
            for _ in range(32):
                middle=(lo+hi)/2;arrival,_,status=movement(middle)
                if status!='ok':lo=middle;continue
                if arrival>target:lo=middle
                else:hi=middle
            recommended=hi
        jit=strategy('jit',recommended)
        if jit.status=='ok' and jit.eta>baseline.eta:
            jit=strategy('jit',scene.speed)
            jit.reason+=' Замедление отменено: иначе пропускается исходная стыковка.'
        if jit.status=='ok':
            esg=calculate_esg(scene.distance_nm,scene.speed,recommended if jit.speed_knots==recommended else scene.speed)
            jit.fuel_saved_tonnes=esg['fuel_saved_tonnes'];jit.co2_saved_tonnes=esg['co2_saved_tonnes']
    else:
        jit=StrategyResult(id='jit',label='JIT на том же маршруте',status=baseline.status,reason=baseline.reason,nodes=baseline.nodes,checkpoints=baseline.checkpoints)
    # Compare a whole land alternative, not an invented direct rail connection.
    domestic_hours=12 if origin=='Астрахань' else 0
    road_hours=32+road_delay+3*scene.border_hours+domestic_hours
    terminal_hours=1+road_delay/4 if scene.last_mode is not None else 0
    alternative_eta=road_hours+terminal_hours
    alt_nodes=([origin,'Махачкала'] if origin=='Астрахань' else [origin])+['Энзели',*(['Решт'] if scene.last_mode is not None else [])]
    alternative_segments=[]
    if origin=='Астрахань':alternative_segments.append(segment(origin,'Махачкала','road',12,0,550,cargo_mass*490.6*road_ef))
    alternative_segments.extend([segment('Махачкала','Энзели','road',32,road_delay+3*scene.border_hours,800,cargo_mass*1504.6*road_ef,3*scene.border_hours),
                                 *([segment('Энзели','Решт','road',1,road_delay/4,80,cargo_mass*39.1*road_ef)] if scene.last_mode is not None else [])])
    alternative=StrategyResult(id='alternative',label='Автокоридор через Грузию и Азербайджан',status='ok',nodes=alt_nodes,
        reason=f'Три границы, по {scene.border_hours:g} ч на каждой; модель TransitPredictor оценивает дорожную задержку.',
        segments=alternative_segments,eta=at(alternative_eta),total_time_hours=alternative_eta,
        cargo_co2e_kg=sum(s.co2_emissions_kg for s in alternative_segments),cost_usd=(880 if scene.last_mode is not None else 800)+(550 if origin=='Астрахань' else 0),
        timeline=[DemoTimelinePoint(name='Отправление авто',at=anchor),DemoTimelinePoint(name='Энзели',at=at(road_hours)),DemoTimelinePoint(name='Доставка',at=at(alternative_eta))])
    if not scene.road_available:
        alternative=StrategyResult(id='alternative',label='Автокоридор',status='blocked',nodes=alt_nodes,
            reason='Автотранспорт исключён условиями сохранённого плана или дороги закрыты.')
    if baseline.status=='ok' and scene.last_mode is not None:
        events.append(DemoEvent(name='Первый слот поезда' if scene.last_mode=='rail' else 'Готовность авто',at=at(scene.first_slot),detail=f'Сценарное расписание: интервал {scene.interval:g} ч, обработка {scene.handling:g} ч.'))
    if baseline.status=='blocked' and weather_dataset is None:events.append(DemoEvent(name='Штормовое окно',at=at(12),detail='В центральной морской точке действует синтетический шторм с +12 до +72 ч.'))
    snapshot=None
    if weather_dataset is not None:
        warnings[0]='Погода из выбранного набора; очереди, расписания, наземная погода и коэффициенты остаются синтетическими.'
        events[0].detail='Погода из набора; логистика и модели задержек демонстрационные.'
        snapshot={**weather_dataset.model_dump(mode='json',exclude={'records'}),'used_records':list(used_weather.values())}
        if weather_dataset.kind=='archive':warnings.append('Историческое воспроизведение с реанализом, не прогноз доступный диспетчеру в прошлом.')
    return DemoResult(data_source='mixed' if weather_dataset else 'synthetic',weather_snapshot=snapshot,id=str(uuid4()),scenario_id=identity,title=scene.title,description=scene.description,seed=request.seed,
        baseline=baseline,strategies=[baseline,jit,alternative],predictions=traces,events=sorted(events,key=lambda event:event.at),
        warnings=warnings,model_report=models.report,created_at=datetime.now(timezone.utc),inputs=request)


def simulate_saved_voyage(saved: VoyageResponse, request: DemoRunRequest, models: DemoModels, *, weather_dataset: Dataset | None = None) -> DemoResult:
    """Run a synthetic what-if from an immutable saved itinerary, never update it."""
    sea = next((leg for leg in saved.baseline.fastest.segments if leg.transport_mode == 'ship'), None)
    if sea is None or sea.source not in ('Махачкала','Астрахань') or sea.target != 'Энзели':
        return DemoResult(id=str(uuid4()), scenario_id='saved_voyage', title='JIT сохранённого рейса',
            description='Для этой цепочки нет поддержанного морского плеча.', seed=request.seed,
            strategies=[StrategyResult(id='jit',label='JIT',status='not_applicable',
                reason='JIT судна применяется к поддержанному морскому плечу Махачкала/Астрахань — Энзели.',
                nodes=saved.baseline.fastest.nodes)], predictions=[],events=[],warnings=['Сохранённый рейс не изменён.'],
            model_report=models.report,created_at=datetime.now(timezone.utc),parent_voyage_id=saved.id,inputs=request)
    if sea != saved.baseline.fastest.segments[0]:
        raise ValueError('Create a plan starting at the sea departure terminal for this synthetic JIT experiment.')
    subsequent = saved.baseline.fastest.segments[1:]
    if len(subsequent)>1 or (subsequent and subsequent[0].target != 'Решт'):
        raise ValueError('Synthetic JIT supports Enzeli or Rasht as the final destination.')
    mode = subsequent[0].transport_mode if subsequent else None
    schedule = next((s for s in saved.request.connections if s.terminal=='Энзели' and s.transport_mode==mode),None)
    start = saved.request.departure_at
    if request.departure_at is not None and request.departure_at != start:
        raise ValueError("For a saved voyage departure_at must match its immutable schedule.")
    if weather_dataset is not None and request.departure_at is None:
        request=request.model_copy(update={"departure_at":start})
    first = (schedule.first_departure_at-start).total_seconds()/3600 if schedule else 0
    conditions = saved.conditions
    if conditions.weather_mode != 'scenario' and weather_dataset is None:
        raise ValueError('Switch the saved voyage to scenario weather before a synthetic-only JIT experiment.')
    congestion=conditions.port_congestion.get('Энзели',45)
    scene=replace(SCENARIOS[0], origin=sea.source, distance_nm=450 if sea.source=='Астрахань' else 360,
        speed=9 if sea.source=='Астрахань' else 10, wind=conditions.scenario.wind_speed_ms,
        wave=conditions.scenario.wave_height_m,congestion=congestion,queue=max(0,(congestion-20)*0.45),
        first_slot=first, interval=schedule.interval_hours if schedule else 12,
        handling=schedule.handling_hours if schedule else 2, last_mode=mode,
        terminal_periodic=schedule is not None,border_hours=conditions.road.border_wait_hours,
        season=('Winter','Spring','Summer','Autumn')[(start.astimezone(timezone.utc).month % 12)//3],
        road_available='road' in saved.request.transport_modes and not conditions.road.closed,
        title='JIT сохранённого рейса',description='Синтетический what-if; исходный план и его прогноз не изменяются.')
    result=run_scenario('calm',request,models,scene_override=scene,anchor=start,weather_dataset=weather_dataset)
    result.scenario_id='saved_voyage';result.parent_voyage_id=saved.id
    result.warnings.append('Дистанция и исходная скорость взяты из демонстрационного профиля судна, не из AIS. Это новый опыт с исходной стратегией, а не замена baseline рейса.')
    return result

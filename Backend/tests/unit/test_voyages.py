import copy
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import networkx as nx
from voyage_models import VoyageRequest,VoyageConditions,ConnectionSchedule
from voyage_service import calculate_voyage
from voyage_store import VoyageStore
from weather_service import WeatherForecast,ForecastSlot

START=datetime(2026,11,12,tzinfo=timezone.utc)
class Predictor:
    def __init__(self):self.calls=[]
    def predict_delay(self,features):
        self.calls.append(dict(features))
        return float(features['weather_severity'])+float(features['port_congestion'])/10
class Weather:
    def __init__(self,wind=None):self.calls=[];self.wind=wind or (lambda lat,lon,time:4)
    def forecast(self,location):
        self.calls.append((location.latitude,location.longitude))
        slots=[]
        for index in range(40):
            time=START+timedelta(hours=3*index)
            slots.append(ForecastSlot(valid_at=time,temperature_c=10,wind_speed_ms=self.wind(location.latitude,location.longitude,time),
                humidity_percent=60,pressure_hpa=1013,precipitation_probability=0,rain_3h_mm=0,snow_3h_mm=0,description='test'))
        return WeatherForecast(location=location,retrieved_at=START,forecasts=slots)

def network():
    graph=nx.MultiDiGraph()
    graph.add_edge('Махачкала','Энзели',key='ship',transport_mode='ship',base_time_hours=10.0,cost_usd=100.0,co2_emissions_kg=50.0,port_congestion=20.0)
    graph.add_edge('Энзели','Решт',key='rail',transport_mode='rail',base_time_hours=2.0,cost_usd=20.0,co2_emissions_kg=5.0,port_congestion=20.0)
    return graph

def plan():
    return VoyageRequest(source='Махачкала',target='Решт',departure_at=START,
        connections=[ConnectionSchedule(terminal='Энзели',transport_mode='rail',first_departure_at=START+timedelta(hours=16),interval_hours=12,handling_hours=1)])

class VoyageTests(unittest.TestCase):
    def test_passage_slots_features_and_no_mutation(self):
        request=plan();conditions=VoyageConditions(weather_mode='openweather')
        weather=Weather();predictor=Predictor();graph=network();before=copy.deepcopy(graph)
        snapshot=calculate_voyage(request,conditions,graph,predictor,weather)
        ship,rail=snapshot.fastest.segments
        self.assertEqual(ship.checkpoints[1].name,'Центральный Каспий')
        self.assertEqual(ship.checkpoints[1].forecast_at,START+timedelta(hours=6))
        self.assertEqual(rail.departure_at,START+timedelta(hours=16))
        self.assertEqual(rail.checkpoints[0].forecast_at,START+timedelta(hours=15))
        self.assertEqual(ship.features_used['weather_severity'],1.6)
        self.assertEqual(ship.features_used['port_congestion'],20)
        self.assertEqual(len(weather.calls),len(set(weather.calls)))
        self.assertTrue(nx.utils.graphs_equal(before,graph))
        for leg in snapshot.fastest.segments:
            duration=(leg.arrival_at-leg.departure_at).total_seconds()/3600
            self.assertAlmostEqual(duration+leg.connection_wait_hours,leg.expected_time_hours)
        self.assertAlmostEqual(snapshot.fastest.total_time_hours,(snapshot.fastest.eta-START).total_seconds()/3600)

    def test_port_delay_misses_connection_and_preserves_baseline_on_disk(self):
        request=plan();graph=network();predictor=Predictor()
        baseline=calculate_voyage(request,request.conditions,graph,predictor,None)
        updated=VoyageConditions(port_congestion={'Энзели':95})
        current=calculate_voyage(request,updated,graph,predictor,None)
        self.assertIn('port_congestion',[r.code for r in current.fastest.reasons])
        self.assertIn('missed_connection',[r.code for r in current.fastest.reasons])
        self.assertEqual(current.fastest.segments[1].departure_at,START+timedelta(hours=28))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'voyages.sqlite3'
            first=VoyageStore(path).create(request,baseline)
            saved=VoyageStore(path).update(first.id,current,updated,0)
            restored=VoyageStore(path).get(first.id)
            self.assertEqual(restored.baseline,baseline)
            self.assertEqual(restored.request,request)
            self.assertGreater(restored.eta_change_hours,0)
            self.assertEqual(saved.revision,1)
            with self.assertRaises(RuntimeError):VoyageStore(path).update(first.id,baseline,request.conditions,0)
            self.assertEqual(VoyageStore(path).get(first.id).current,current)

    def test_storm_at_midpoint_changes_route_not_all_sea_globally(self):
        graph=network()
        graph.add_edge('Махачкала','Решт',key='road',transport_mode='road',base_time_hours=30.0,cost_usd=200.0,co2_emissions_kg=100.0,port_congestion=20.0)
        request=plan();conditions=VoyageConditions(weather_mode='openweather')
        calm=calculate_voyage(request,conditions,graph,Predictor(),Weather())
        weather=Weather(lambda lat,lon,time:22 if lat==41.2 and time==START+timedelta(hours=6) else 4)
        storm=calculate_voyage(request,conditions,graph,Predictor(),weather)
        self.assertEqual(calm.fastest.segments[0].transport_mode,'ship')
        self.assertEqual(storm.fastest.segments[0].transport_mode,'road')
        self.assertTrue(storm.excluded_reasons)
        self.assertEqual(storm.excluded_reasons[0].code,'storm_restriction')

    def test_weather_shift_updates_downstream_checkpoint_times(self):
        request=plan();request.connections=[]
        conditions=VoyageConditions(weather_mode='openweather')
        calm=calculate_voyage(request,conditions,network(),Predictor(),Weather())
        wind=calculate_voyage(request,conditions,network(),Predictor(),Weather(lambda lat,lon,time:14))
        self.assertGreater(wind.fastest.eta,calm.fastest.eta)
        self.assertGreater(wind.fastest.segments[1].checkpoints[0].passage_at,calm.fastest.segments[1].checkpoints[0].passage_at)
        self.assertNotEqual(wind.fastest.segments[1].checkpoints[0].forecast_at,calm.fastest.segments[1].checkpoints[0].forecast_at)

    def test_no_extrapolation_outside_forecast_horizon(self):
        request=plan();request.departure_at=START+timedelta(days=7);request.connections=[]
        snapshot=calculate_voyage(request,VoyageConditions(weather_mode='openweather'),network(),Predictor(),Weather())
        self.assertEqual(snapshot.fastest.coverage,'partial')
        for leg in snapshot.fastest.segments:
            for cp in leg.checkpoints:
                self.assertEqual(cp.status,'outside_horizon')
                self.assertIsNone(cp.wind_speed_ms)
                self.assertIsNone(cp.forecast_at)

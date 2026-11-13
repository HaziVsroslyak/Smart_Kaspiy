"""Bounded imports, provider adapter and conservative point/time selection."""
import csv
import hashlib
import io
import json
import math
from datetime import datetime,timezone
from urllib.parse import urlencode
from urllib.request import urlopen
from uuid import uuid4
from .contracts import Dataset,WeatherRecord,ImportRequest,FetchRequest,ResolveRequest,Resolution

LIMIT=5*1024*1024

def records_from_rows(rows):
    if not isinstance(rows,list) or not 1<=len(rows)<=20000:
        raise ValueError('Expected 1–20000 weather records.')
    records=[];seen=set()
    for index,row in enumerate(rows,1):
        try:
            value=WeatherRecord.model_validate(row)
            value.timestamp=value.timestamp.astimezone(timezone.utc)
            if value.issued_at is not None:
                value.issued_at=value.issued_at.astimezone(timezone.utc)
            key=(value.timestamp,value.latitude,value.longitude)
            if key in seen: raise ValueError('Duplicate point and timestamp.')
            seen.add(key);records.append(value)
        except (ValueError,TypeError) as exc:
            raise ValueError(f'Row {index}: {exc}') from None
    return sorted(records,key=lambda r:(r.timestamp,r.latitude,r.longitude))

def make_dataset(rows,source_name,source_url,provenance,kind):
    records=records_from_rows(rows)
    canonical=json.dumps([r.model_dump(mode='json') for r in records],sort_keys=True,separators=(',',':'))
    return Dataset(id=str(uuid4()),source_name=source_name,source_url=source_url,provenance=provenance,kind=kind,retrieved_at=datetime.now(timezone.utc),content_hash=hashlib.sha256(canonical.encode()).hexdigest(),records=records)

def import_dataset(payload:ImportRequest)->Dataset:
    if len(payload.content.encode('utf-8'))>LIMIT: raise ValueError('File exceeds 5 MiB.')
    if payload.format=='json': rows=json.loads(payload.content)
    else:
        reader=csv.DictReader(io.StringIO(payload.content.lstrip('\ufeff')))
        if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames): raise ValueError('Missing or duplicate CSV columns.')
        rows=[]
        for row in reader:
            if len(rows)>=20000: raise ValueError('More than 20000 records.')
            if None in row: raise ValueError('CSV row has extra columns.')
            rows.append({k:None if v is None or v.strip()=='' else v for k,v in row.items()})
    return make_dataset(rows,payload.source_name,payload.source_url,'uploaded_unverified','upload')

def fetch_dataset(payload:FetchRequest)->Dataset:
    if not 0<=(payload.end_date-payload.start_date).days<=30: raise ValueError('Date interval must be 1–31 days.')
    endpoint='https://archive-api.open-meteo.com/v1/archive' if payload.kind=='archive' else 'https://api.open-meteo.com/v1/forecast'
    mapping={'wind_speed_ms':'wind_speed_10m','wind_gust_ms':'wind_gusts_10m','wind_direction_deg':'wind_direction_10m','temperature_c':'temperature_2m','precipitation_mm':'precipitation','surface_pressure_hpa':'surface_pressure'}
    query=urlencode(dict(latitude=payload.latitude,longitude=payload.longitude,start_date=payload.start_date.isoformat(),end_date=payload.end_date.isoformat(),hourly=','.join(mapping.values()),wind_speed_unit='ms',timezone='UTC',cell_selection='sea'))
    with urlopen(endpoint+'?'+query,timeout=15) as response:
        raw=response.read(LIMIT+1)
    if len(raw)>LIMIT: raise ValueError('Provider response too large.')
    data=json.loads(raw)
    if data.get('error'): raise ValueError('Provider rejected the date range or location.')
    hourly=data['hourly'];times=hourly['time'];rows=[]
    for i,time in enumerate(times):
        row={'timestamp':time+'Z' if not time.endswith('Z') else time,'latitude':data['latitude'],'longitude':data['longitude']}
        for name,key in mapping.items():
            values=hourly.get(key)
            row[name]=values[i] if values is not None else None
        rows.append(row)
    dataset=make_dataset(rows,'Open-Meteo reanalysis' if payload.kind=='archive' else 'Open-Meteo forecast',endpoint+'?'+query,'provider',payload.kind)
    dataset.requested_latitude=payload.latitude
    dataset.requested_longitude=payload.longitude
    dataset.precipitation_interval_hours=1
    return dataset

def distance_km(a,b):
    lat1,lat2=map(math.radians,(a.latitude,b.latitude));dl=math.radians(a.longitude-b.longitude)
    h=math.sin((lat1-lat2)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dl/2)**2
    return 6371*2*math.asin(min(1,math.sqrt(h)))

def resolve(dataset:Dataset,point:ResolveRequest)->Resolution:
    nearby=[r for r in dataset.records if distance_km(r,point)<=25]
    if not nearby or not min(r.timestamp for r in nearby)<=point.timestamp<=max(r.timestamp for r in nearby):
        return Resolution(status='missing',gaps=['No spatial/time coverage; extrapolation disabled.'])
    candidates=[r for r in nearby if abs((r.timestamp-point.timestamp).total_seconds())<=10800]
    if not candidates:return Resolution(status='missing',gaps=['No record within 3 hours.'])
    record=min(candidates,key=lambda r:(abs((r.timestamp-point.timestamp).total_seconds()),distance_km(r,point)))
    gaps=[name for name in ('wind_speed_ms','wave_height_m') if getattr(record,name) is None]
    return Resolution(status='missing' if gaps else 'complete',record=record,gaps=gaps)

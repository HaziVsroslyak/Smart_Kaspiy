import {afterEach,describe,expect,it,vi} from 'vitest';
import {api} from './client';
import {createVoyage,getVoyage,reforecastVoyage} from './voyages';
import type {VoyageConditions,VoyageRequest} from './voyages';
afterEach(()=>vi.restoreAllMocks());
const conditions:VoyageConditions={weather_mode:'openweather',scenario:{source:'scenario',wind_speed_ms:4,wind_gust_ms:null,wave_height_m:null},road:{congestion_percent:20,condition_severity:0,border_wait_hours:4,closed:false},port_congestion:{}};
describe('persistent voyage API',()=>{
 it('creates a plan with its departure and preserves the payload',async()=>{
  const payload:VoyageRequest={source:'Махачкала',target:'Решт',departure_at:'2026-11-12T10:00:00Z',transport_modes:['ship','rail'],connections:[],conditions};
  const post=vi.spyOn(api,'post').mockResolvedValue({data:{id:'saved'}});
  expect(await createVoyage(payload)).toEqual({id:'saved'});
  expect(post).toHaveBeenCalledWith('/api/v1/voyages',payload,{signal:undefined,timeout:90000});
 });
 it('reforecasts conditions without sending a replacement baseline',async()=>{
  const post=vi.spyOn(api,'post').mockResolvedValue({data:{id:'saved'}});
  await reforecastVoyage('saved',conditions);
  expect(post).toHaveBeenCalledWith('/api/v1/voyages/saved/reforecast',{conditions},{signal:undefined,timeout:90000});
 });
 it('loads a saved plan and propagates failure without a mock',async()=>{
  const get=vi.spyOn(api,'get').mockResolvedValueOnce({data:{id:'saved'}}).mockRejectedValueOnce(new Error('Network'));
  expect(await getVoyage('saved')).toEqual({id:'saved'});
  expect(get).toHaveBeenCalledWith('/api/v1/voyages/saved',{signal:undefined});
  await expect(getVoyage('saved')).rejects.toThrow('Network');
 });
});

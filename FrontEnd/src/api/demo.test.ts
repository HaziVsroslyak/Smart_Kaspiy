import {afterEach,describe,expect,it,vi} from 'vitest';
import {api} from './client';
import {getDemoCatalog,getDemoRun,runDemoScenario,simulateVoyageJIT,strategyRoute,timelineProgress,vesselPosition} from './demo';
import type {StrategyResult} from './demo';
afterEach(()=>vi.restoreAllMocks());

describe('synthetic JIT demo API',()=>{
 it('checks capability before requesting the catalog',async()=>{
  const get=vi.spyOn(api,'get').mockResolvedValueOnce({data:{capabilities:['synthetic_jit_v1']}}).mockResolvedValueOnce({data:{scenarios:[],model_report:{}}});
  expect(await getDemoCatalog()).toEqual({scenarios:[],model_report:{}});
  expect(get.mock.calls.map(call=>call[0])).toEqual(['/api/v1/health','/api/v1/demo/scenarios']);
 });
 it('reports an outdated backend without issuing unsupported requests',async()=>{
  const get=vi.spyOn(api,'get').mockResolvedValue({data:{status:'ready'}});
  await expect(getDemoCatalog()).rejects.toThrow('не поддерживает демонстратор');
  expect(get).toHaveBeenCalledTimes(1);
 });
 it('sends seed and overrides to the backend calculation',async()=>{
  const post=vi.spyOn(api,'post').mockResolvedValue({data:{id:'computed'}});
  const controller=new AbortController();
  expect(await runDemoScenario('port queue',{seed:42,port_congestion_percent:95},controller.signal)).toEqual({id:'computed'});
  expect(post).toHaveBeenCalledWith('/api/v1/demo/scenarios/port%20queue/run',{seed:42,port_congestion_percent:95},{signal:controller.signal,timeout:90000});
 });
 it('simulates the active saved voyage with the same seed and overrides',async()=>{
  const post=vi.spyOn(api,'post').mockResolvedValue({data:{id:'computed',parent_voyage_id:'saved voyage'}});
  const controller=new AbortController();
  expect(await simulateVoyageJIT('saved voyage',{seed:7,wind_speed_ms:14},controller.signal)).toEqual({id:'computed',parent_voyage_id:'saved voyage'});
  expect(post).toHaveBeenCalledWith('/api/v1/voyages/saved%20voyage/jit/simulate',{seed:7,wind_speed_ms:14},{signal:controller.signal,timeout:90000});
 });
 it('restores a server calculation and never falls back to fixed successful data',async()=>{
  const get=vi.spyOn(api,'get').mockResolvedValueOnce({data:{id:'saved'}}).mockRejectedValueOnce(new Error('Network'));
  expect(await getDemoRun('saved')).toEqual({id:'saved'});
  expect(get).toHaveBeenCalledWith('/api/v1/demo/runs/saved',{signal:undefined});
  await expect(getDemoRun('saved')).rejects.toThrow('Network');
  vi.spyOn(api,'post').mockRejectedValue(new Error('Network'));
  await expect(runDemoScenario('calm',{seed:42})).rejects.toThrow('Network');
 });
});

describe('demo visualization data',()=>{
 const strategy={id:'jit',status:'ok',nodes:['Махачкала','Энзели'],segments:[{source:'Махачкала',target:'Энзели',edge_id:'ship',transport_mode:'ship',base_time_hours:20,delay_hours:3,expected_time_hours:23,cost_usd:500,co2_emissions_kg:140}],total_time_hours:25,cost_usd:500} as StrategyResult;
 it('preserves computed segments and full elapsed time for the route map',()=>{
  expect(strategyRoute(strategy)).toEqual({nodes:strategy.nodes,segments:strategy.segments,total_base_time_hours:20,total_delay_hours:3,total_time_hours:25,total_cost_usd:500,total_co2_emissions_kg:140});
 });
 it('does not draw blocked strategies as a calculated route',()=>{
  expect(strategyRoute({...strategy,status:'blocked'})).toBeNull();
  expect(strategyRoute(null)).toBeNull();
 });
 it('clamps timeline markers and rejects invalid timestamps',()=>{
  expect(timelineProgress('2026-11-12T12:00:00Z','2026-11-12T00:00:00Z','2026-11-13T00:00:00Z')).toBe(0.5);
  expect(timelineProgress('2026-11-11T12:00:00Z','2026-11-12T00:00:00Z','2026-11-13T00:00:00Z')).toBe(0);
  expect(timelineProgress('2026-11-14T12:00:00Z','2026-11-12T00:00:00Z','2026-11-13T00:00:00Z')).toBe(1);
  expect(timelineProgress('invalid','2026-11-12T00:00:00Z','2026-11-13T00:00:00Z')).toBe(0);
 });
 it('moves the ship along the sea geometry and keeps it at port after arrival',()=>{
  const moving={...strategy,sea_arrival_at:'2026-11-14T00:00:00Z',timeline:[{name:'Start',at:'2026-11-12T00:00:00Z'}]};
  const start=vesselPosition(moving,'2026-11-12T00:00:00Z')!;
  const middle=vesselPosition(moving,'2026-11-13T00:00:00Z')!;
  const end=vesselPosition(moving,'2026-11-15T00:00:00Z')!;
  expect(start.latitude).toBe(42.99);
  expect(middle.latitude).toBeLessThan(start.latitude);
  expect(middle.latitude).toBeGreaterThan(end.latitude);
  expect(end.latitude).toBe(37.53);
  expect(vesselPosition({...moving,status:'blocked'},'2026-11-13T00:00:00Z')).toBeNull();
 });
});

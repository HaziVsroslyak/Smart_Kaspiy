import {api} from './client';
import type {RouteDetails, RouteSegment} from './client';
import {segmentGeometry} from '../data/routeGeometry';

export interface DemoScenario {id:string;title:string;description:string}
export interface DemoRunRequest {dataset_id?:string;departure_at?:string;seed?:number;wind_speed_ms?:number;wave_height_m?:number;port_congestion_percent?:number}
export interface PredictionTrace {model_id:string;target:string;value_hours:number;lower_hours:number;upper_hours:number;features:Record<string,unknown>;data_version:string}
export interface DemoCheckpoint {name:string;latitude:number;longitude:number;passage_at:string;wind_speed_ms:number|null;wave_height_m:number|null}
export interface StrategyResult {
 id:'baseline'|'jit'|'alternative';label:string;status:'ok'|'blocked'|'not_applicable'|'insufficient_data';reason:string;
 nodes:string[];segments:RouteSegment[];speed_knots:number|null;sea_arrival_at:string|null;berth_ready_at:string|null;
 handling_complete_at:string|null;connection_at:string|null;eta:string|null;total_time_hours:number|null;
 berth_wait_hours:number;connection_wait_hours:number;fuel_tonnes:number|null;co2_tonnes:number|null;cargo_co2e_kg:number|null;
 cost_usd:number;remaining_wait_hours:number;checkpoints:DemoCheckpoint[];timeline:{name:string;at:string}[];
 fuel_saved_tonnes:number|null;co2_saved_tonnes:number|null;
}
export interface DemoEvent {name:string;at:string;detail:string}
export interface DemoResult {
 id:string;scenario_id:string;title:string;description:string;data_source:'synthetic'|'mixed';seed:number;
 parent_voyage_id?:string|null;
 inputs?:DemoRunRequest;
 baseline:StrategyResult|null;strategies:StrategyResult[];predictions:PredictionTrace[];events:DemoEvent[];
 warnings:string[];model_report:Record<string,unknown>;created_at:string;
}
export interface DemoCatalog {scenarios:DemoScenario[];model_report:Record<string,unknown>}

export async function getDemoCatalog(signal?:AbortSignal):Promise<DemoCatalog>{
 const {data:health}=await api.get<{capabilities?:string[]}>('/api/v1/health',{signal});
 if(!health.capabilities?.includes('synthetic_jit_v1'))throw new Error('Этот бэкенд не поддерживает демонстратор JIT. Запустите актуальную версию Backend и обновите страницу.');
 const {data}=await api.get<DemoCatalog>('/api/v1/demo/scenarios',{signal});return data;
}
export async function runDemoScenario(id:string,payload:DemoRunRequest,signal?:AbortSignal):Promise<DemoResult>{
 const {data}=await api.post<DemoResult>(`/api/v1/demo/scenarios/${encodeURIComponent(id)}/run`,payload,{signal,timeout:90000});return data;
}
export async function simulateVoyageJIT(id:string,payload:DemoRunRequest,signal?:AbortSignal):Promise<DemoResult>{
 const {data}=await api.post<DemoResult>(`/api/v1/voyages/${encodeURIComponent(id)}/jit/simulate`,payload,{signal,timeout:90000});return data;
}
export async function getDemoRun(id:string,signal?:AbortSignal):Promise<DemoResult>{
 const {data}=await api.get<DemoResult>(`/api/v1/demo/runs/${encodeURIComponent(id)}`,{signal});return data;
}
export function strategyRoute(strategy:StrategyResult|null):RouteDetails|null{
 if(!strategy||strategy.status!=='ok'||!strategy.segments.length)return null;
 return {nodes:strategy.nodes,segments:strategy.segments,
  total_base_time_hours:strategy.segments.reduce((sum,leg)=>sum+leg.base_time_hours,0),
  total_delay_hours:strategy.segments.reduce((sum,leg)=>sum+leg.delay_hours,0),
  total_time_hours:strategy.total_time_hours??strategy.segments.reduce((sum,leg)=>sum+leg.expected_time_hours,0),
  total_cost_usd:strategy.cost_usd,total_co2_emissions_kg:strategy.segments.reduce((sum,leg)=>sum+leg.co2_emissions_kg,0)};
}
export function timelineProgress(at:string,start:string,end:string):number{
 const from=Date.parse(start),to=Date.parse(end),value=Date.parse(at);
 if(!Number.isFinite(from)||!Number.isFinite(to)||!Number.isFinite(value)||to<=from)return 0;
 return Math.max(0,Math.min(1,(value-from)/(to-from)));
}

export function vesselPosition(strategy:StrategyResult|null,at:string):{latitude:number;longitude:number;label:string}|null{
 if(!strategy||strategy.status!=='ok'||!strategy.sea_arrival_at)return null;
 const sea=strategy.segments.find(leg=>leg.transport_mode==='ship');
 const departure=strategy.timeline[0]?.at;
 if(!sea||!departure)return null;
 const geometry=segmentGeometry(sea);
 if(geometry.length<2)return null;
 const progress=timelineProgress(at,departure,strategy.sea_arrival_at);
 const distances=geometry.slice(1).map((point,index)=>{
  const before=geometry[index],scale=Math.cos((before[0]+point[0])*Math.PI/360);
  return Math.hypot(point[0]-before[0],(point[1]-before[1])*scale);
 });
 let remaining=distances.reduce((sum,value)=>sum+value,0)*progress;
 for(let index=0;index<distances.length;index++){
  if(remaining<=distances[index]||index===distances.length-1){
   const f=distances[index]?Math.min(1,remaining/distances[index]):0;
   const a=geometry[index],b=geometry[index+1];
   return {latitude:a[0]+(b[0]-a[0])*f,longitude:a[1]+(b[1]-a[1])*f,
    label:progress>=1?'Судно у порта · симуляция':`Судно · ${Math.round(progress*100)}% перехода`};
  }
  remaining-=distances[index];
 }
 return null;
}

import type {RoadConditions, RouteDetails, RouteSegment, TransportMode} from './client';
import {api} from './client';
export interface VoyageConditions {weather_mode:'openweather'|'scenario';scenario:{source:'scenario';wind_speed_ms:number;wind_gust_ms:number|null;wave_height_m:number|null};road:RoadConditions;port_congestion:Record<string,number>}
export interface ConnectionSchedule {terminal:string;transport_mode:TransportMode;first_departure_at:string;interval_hours:number;handling_hours:number}
export interface VoyageRequest {source:string;target:string;departure_at:string;transport_modes:TransportMode[];connections:ConnectionSchedule[];conditions:VoyageConditions}
export interface Checkpoint {name:string;latitude:number;longitude:number;passage_at:string;forecast_at:string|null;retrieved_at:string|null;wind_speed_ms:number|null;wind_gust_ms:number|null;wave_height_m:number|null;severity:number|null;status:'forecast'|'scenario'|'outside_horizon'}
export interface DelayReason {code:string;message:string;hours:number}
export interface TimedLeg extends RouteSegment {departure_at:string;arrival_at:string;connection_wait_hours:number;checkpoints:Checkpoint[];features_used:Record<string,string|number>;reasons:DelayReason[];eta_converged:boolean}
export interface TimedRoute extends RouteDetails {segments:TimedLeg[];departure_at:string;eta:string;coverage:'complete'|'partial';reasons:DelayReason[]}
export interface VoyageSnapshot {calculated_at:string;fastest:TimedRoute;eco:TimedRoute;excluded_reasons:DelayReason[];alternative_reasons:DelayReason[];training_data:'synthetic'}
export interface VoyageResponse {id:string;request:VoyageRequest;conditions:VoyageConditions;baseline:VoyageSnapshot;current:VoyageSnapshot;eta_change_hours:number;route_changed:boolean;revision:number}
export async function createVoyage(payload:VoyageRequest,signal?:AbortSignal):Promise<VoyageResponse>{
 const {data}=await api.post<VoyageResponse>('/api/v1/voyages',payload,{signal,timeout:90000});return data;
}
export async function getVoyage(id:string,signal?:AbortSignal):Promise<VoyageResponse>{
 const {data}=await api.get<VoyageResponse>(`/api/v1/voyages/${encodeURIComponent(id)}`,{signal});return data;
}
export async function reforecastVoyage(id:string,conditions:VoyageConditions,signal?:AbortSignal):Promise<VoyageResponse>{
 const {data}=await api.post<VoyageResponse>(`/api/v1/voyages/${encodeURIComponent(id)}/reforecast`,{conditions},{signal,timeout:90000});return data;
}

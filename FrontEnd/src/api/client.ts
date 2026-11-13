import axios from 'axios';

export type ForecastRouteWeather = {source:'openweather';latitude:number;longitude:number;forecast_at:string};
export type RouteWeather = ForecastRouteWeather | {source:'scenario';wind_speed_ms:number;wind_gust_ms?:number|null;wave_height_m?:number|null};
export type TransportMode = 'ship'|'rail'|'road';
export interface RoadConditions {congestion_percent:number;condition_severity:number;border_wait_hours:number;closed:boolean}
export interface RouteRequest { transport_modes?:TransportMode[];road_conditions?:RoadConditions; source: string; target: string; current_weather?: number; season?: 'winter'|'spring'|'summer'|'autumn'; weather?:RouteWeather }
export interface RouteSegment {source:string;target:string;edge_id:string|number;transport_mode:TransportMode;border_wait_hours?:number;base_time_hours:number;delay_hours:number;expected_time_hours:number;cost_usd:number;co2_emissions_kg:number}
export interface RouteDetails {nodes:string[];segments:RouteSegment[];total_base_time_hours:number;total_delay_hours:number;total_time_hours:number;total_cost_usd:number;total_co2_emissions_kg:number}
export interface WeatherImpact {source:'openweather'|'scenario'|'manual';severity:number;wind_speed_ms:number|null;wind_gust_ms:number|null;wave_height_m:number|null;forecast_at:string|null;retrieved_at:string|null;location:{latitude:number;longitude:number}|null;sea_restricted:boolean;reasons:string[];scope:string;policy:string}
export interface RouteResponse extends RouteDetails {road_conditions?:RoadConditions;transport_modes?:TransportMode[];eco:RouteDetails;weather:WeatherImpact}
export interface CargoPayload { weight: number; type: string; id: string }
export interface CustomsRequest { cargo_payload: CargoPayload; provided_hash: string }
export interface LegacyCustomsRequest { cargo_data: {weight: number; type: string; sender: string; recipient: string}; provided_hash: string }
export interface CustomsResponse { status: 'Pre-cleared'|'Requires inspection'; green_corridor: boolean }
export interface JITRequest { distance_nm: number; current_speed_knots: number; port_delay_hours: number }
export interface JITResponse { new_speed_knots: number; arrival_in_hours: number; berth_available_in_hours: number; remaining_wait_hours: number; baseline_fuel_tonnes: number; optimized_fuel_tonnes: number; fuel_saved_tonnes: number; co2_saved_tonnes: number; fuel_coefficient: number }
export interface ResultMeta { mode: 'live'|'mock'; warning?: string }
export interface WeatherSlot {valid_at:string;temperature_c:number;wind_speed_ms:number;wind_direction_deg:number|null;wind_gust_ms:number|null;humidity_percent:number;pressure_hpa:number;precipitation_probability:number;rain_3h_mm:number;snow_3h_mm:number;description:string;wave_height_m:null}
export interface WeatherForecast {provider:'OpenWeather';product:'5-day/3-hour';location:{latitude:number;longitude:number};retrieved_at:string;step_hours:3;cached:boolean;wave_height_available:false;forecasts:WeatherSlot[]}
export type ApiResult<T> = T & {_meta: ResultMeta};
export const api = axios.create({baseURL: import.meta.env.VITE_API_BASE_URL || '', timeout: 12000, withCredentials:true});
let csrfToken = '';
export function setCsrfToken(value:string){csrfToken=value;}
api.interceptors.request.use(config=>{
 if(!['get','head','options'].includes((config.method??'get').toLowerCase())&&csrfToken)config.headers.set('X-CSRF-Token',csrfToken);
 return config;
});
api.interceptors.response.use(response=>response,error=>{
 if(error.response?.status===401){csrfToken='';if(typeof window!=='undefined')window.dispatchEvent(new Event('caspian-auth-expired'));}
 return Promise.reject(error);
});
export async function calculateRoute(payload:RouteRequest):Promise<ApiResult<RouteResponse>>{
 const {data}=await api.post<RouteResponse>('/api/v1/route/calculate',payload);return {...data,_meta:{mode:'live'}};
}
// The weather-driven planner must not display a canned route as a weather recalculation.
export async function calculateWeatherRoute(payload:RouteRequest,signal?:AbortSignal):Promise<RouteResponse>{
 const {data}=await api.post<RouteResponse>('/api/v1/route/calculate',payload,{signal});return data;
}
export async function clearCustoms(payload:CustomsRequest|LegacyCustomsRequest):Promise<ApiResult<CustomsResponse>>{
 const {data}=await api.post<CustomsResponse>('/api/v1/customs/clear',payload);return {...data,_meta:{mode:'live'}};
}
export async function optimizeJIT(payload:JITRequest):Promise<ApiResult<JITResponse>>{
 const {data}=await api.post<JITResponse>('/api/v1/optimize/jit',payload);return {...data,_meta:{mode:'live'}};
}

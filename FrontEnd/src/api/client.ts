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
export const api = axios.create({baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000', timeout: 12000});

function fallbackReason(error: unknown): string {
  if (axios.isAxiosError(error) && error.response && error.response.status < 500) {
    // Validation errors and missing routes must not look like successful mock calls.
    throw new Error(`API ${error.response.status}: ${JSON.stringify(error.response.data.detail ?? error.response.data)}`);
  }
  return 'API недоступен. Показан фиксированный пример, не результат расчета ваших данных.';
}

export async function calculateRoute(payload: RouteRequest): Promise<ApiResult<RouteResponse>> {
  try { const {data} = await api.post<RouteResponse>('/api/v1/route/calculate', payload); return {...data, _meta:{mode:'live'}}; }
  catch (error) {
    const example:RouteDetails={nodes:['Махачкала','Энзели','Решт'],segments:[
      {source:'Махачкала',target:'Энзели',edge_id:'ship',transport_mode:'ship',base_time_hours:20,delay_hours:16,expected_time_hours:36,cost_usd:500,co2_emissions_kg:140},
      {source:'Энзели',target:'Решт',edge_id:'rail',transport_mode:'rail',base_time_hours:2,delay_hours:4.5,expected_time_hours:6.5,cost_usd:100,co2_emissions_kg:8},
    ],total_base_time_hours:22,total_delay_hours:20.5,total_time_hours:42.5,total_cost_usd:600,total_co2_emissions_kg:148};
    return {...example,eco:example,weather:{source:'manual',severity:0,wind_speed_ms:null,wind_gust_ms:null,wave_height_m:null,forecast_at:null,retrieved_at:null,location:null,sea_restricted:false,reasons:[],scope:'fixed_mock',policy:'fixed_mock'},_meta:{mode:'mock',warning:fallbackReason(error)}};
  }
}

// The weather-driven planner must not display a canned route as a weather recalculation.
export async function calculateWeatherRoute(payload:RouteRequest, signal?:AbortSignal):Promise<RouteResponse> {
  const {data}=await api.post<RouteResponse>('/api/v1/route/calculate',payload,{signal});
  return data;
}
export async function clearCustoms(payload: CustomsRequest|LegacyCustomsRequest): Promise<ApiResult<CustomsResponse>> {
  try { const {data} = await api.post<CustomsResponse>('/api/v1/customs/clear', payload); return {...data, _meta:{mode:'live'}}; }
  catch (error) { return {status:'Requires inspection',green_corridor:false,_meta:{mode:'mock',warning:fallbackReason(error)}}; }
}
export async function optimizeJIT(payload: JITRequest): Promise<ApiResult<JITResponse>> {
  try { const {data} = await api.post<JITResponse>('/api/v1/optimize/jit', payload); return {...data, _meta:{mode:'live'}}; }
  catch (error) { return {new_speed_knots:8,arrival_in_hours:15,berth_available_in_hours:15,remaining_wait_hours:0,baseline_fuel_tonnes:1.728,optimized_fuel_tonnes:0.768,fuel_saved_tonnes:0.96,co2_saved_tonnes:2.98944,fuel_coefficient:0.0001,_meta:{mode:'mock',warning:fallbackReason(error)}}; }
}

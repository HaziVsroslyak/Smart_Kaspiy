import {afterEach,describe,it,expect,vi} from 'vitest';
import {api,calculateRoute,calculateWeatherRoute,clearCustoms,optimizeJIT} from './client';
afterEach(()=>vi.restoreAllMocks());
describe('API fallback',()=>{
 it('does not replace a failed weather recalculation with a mock',async()=>{
  vi.spyOn(api,'post').mockRejectedValue(new Error('Network'));
  await expect(calculateWeatherRoute({source:'Махачкала',target:'Решт',weather:{source:'scenario',wind_speed_ms:22}})).rejects.toThrow('Network');
 });
 it('forwards forecast reference and cancellation signal',async()=>{
  const request={source:'Махачкала',target:'Решт',weather:{source:'openweather' as const,latitude:42,longitude:50,forecast_at:'2026-11-12T03:00:00Z'}};
  const controller=new AbortController();
  const post=vi.spyOn(api,'post').mockResolvedValue({data:{nodes:['Махачкала','Решт']}});
  await calculateWeatherRoute(request,controller.signal);
  expect(post).toHaveBeenCalledWith('/api/v1/route/calculate',request,{signal:controller.signal});
 });
 it('returns live data',async()=>{vi.spyOn(api,'post').mockResolvedValue({data:{nodes:['А','Б'],total_time_hours:1,total_cost_usd:2}});expect((await calculateRoute({source:'А',target:'Б',current_weather:1}))._meta.mode).toBe('live');});
 it('labels network mocks and never clears cargo',async()=>{vi.spyOn(api,'post').mockRejectedValue(new Error('Network'));expect((await calculateRoute({source:'А',target:'Б',current_weather:1}))._meta.mode).toBe('mock');const customs=await clearCustoms({cargo_payload:{id:'1',type:'test',weight:1},provided_hash:'0'.repeat(64)});expect(customs.green_corridor).toBe(false);expect(customs._meta.mode).toBe('mock');expect((await optimizeJIT({distance_nm:120,current_speed_knots:12,port_delay_hours:5})).co2_saved_tonnes).toBe(2.98944);});
 it('keeps validation errors visible',async()=>{vi.spyOn(api,'post').mockRejectedValue({isAxiosError:true,response:{status:422,data:{detail:'invalid'}}});await expect(optimizeJIT({distance_nm:0,current_speed_knots:1,port_delay_hours:0})).rejects.toThrow('422');});
});

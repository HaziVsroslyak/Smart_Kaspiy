import {afterEach,describe,expect,it,vi} from 'vitest';
import {api} from './client';
import {fetchWeather,importWeather,getWeatherDataset} from './weatherDatasets';
afterEach(()=>vi.restoreAllMocks());
describe('weather datasets',()=>{
 it('preserves uploaded source and content',async()=>{const post=vi.spyOn(api,'post').mockResolvedValue({data:{id:'x',records:[{wave_height_m:null}]}});const result=await importWeather('csv','timestamp,latitude,longitude','Station','https://example.org');expect(post).toHaveBeenCalledWith('/api/v1/weather/datasets/import',{format:'csv',content:'timestamp,latitude,longitude',source_name:'Station',source_url:'https://example.org'});expect(result.records[0].wave_height_m).toBeNull();});
 it('keeps archives distinct from forecasts',async()=>{const post=vi.spyOn(api,'post').mockResolvedValue({data:{id:'x'}});const input={latitude:42,longitude:48,start_date:'2025-01-01',end_date:'2025-01-02',kind:'archive' as const};await fetchWeather(input);expect(post).toHaveBeenCalledWith('/api/v1/weather/datasets/fetch',input,{timeout:45000});});
 it('does not fabricate data when access or provider fails',async()=>{const error=new Error('unavailable');vi.spyOn(api,'get').mockRejectedValue(error);await expect(getWeatherDataset('x')).rejects.toBe(error);});
});

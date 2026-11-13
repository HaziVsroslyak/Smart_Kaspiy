import {afterEach,describe,it,expect,vi} from 'vitest';
import {api,calculateRoute,clearCustoms,optimizeJIT,setCsrfToken} from './client';
afterEach(()=>{vi.restoreAllMocks();setCsrfToken('');});
describe('secured API',()=>{
 it.each([401,403,422,500])('preserves HTTP %s without mocks',async status=>{
  const error={isAxiosError:true,response:{status,data:{detail:'rejected'}}};
  vi.spyOn(api,'post').mockRejectedValue(error);
  await expect(calculateRoute({source:'A',target:'B'})).rejects.toBe(error);
  await expect(clearCustoms({cargo_payload:{id:'1',type:'test',weight:1},provided_hash:'0'.repeat(64)})).rejects.toBe(error);
  await expect(optimizeJIT({distance_nm:120,current_speed_knots:12,port_delay_hours:5})).rejects.toBe(error);
 });
 it('does not replace network failures',async()=>{
  vi.spyOn(api,'post').mockRejectedValue(new Error('Network'));
  await expect(calculateRoute({source:'A',target:'B'})).rejects.toThrow('Network');
 });
 it('uses credentialed same-origin requests',()=>expect(api.defaults.withCredentials).toBe(true));
});

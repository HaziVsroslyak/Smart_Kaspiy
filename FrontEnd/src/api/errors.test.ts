import {describe,expect,it} from 'vitest';
import {apiErrorMessage} from './errors';
const error=(status:number,detail:unknown)=>({isAxiosError:true,response:{status,data:{detail}}});
describe('API version mismatch diagnostics',()=>{
 it('identifies missing endpoints on an old backend',()=>{
  expect(apiErrorMessage(error(404,'Not Found'))).toContain('устаревшая версия');
 });
 it('identifies rejected new request fields',()=>{
  expect(apiErrorMessage(error(422,[{type:'extra_forbidden',loc:['body','transport_modes']}]))).toContain('устаревшая версия');
 });
 it('distinguishes a missing saved voyage from a missing endpoint',()=>{
  expect(apiErrorMessage(error(404,'Voyage not found.'))).toContain('отсутствует в базе');
 });
 it('keeps normal validation separate from forecast availability',()=>{
  expect(apiErrorMessage(error(422,[{type:'greater_than',loc:['body','interval_hours']}]))).toContain('параметры расчёта');
 });
});

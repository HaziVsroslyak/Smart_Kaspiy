import axios from 'axios';

export function apiErrorMessage(error:unknown):string {
  if(!axios.isAxiosError(error))return error instanceof Error?error.message:'Ошибка расчёта';
  if(!error.response)return 'Нет связи с API. Проверьте запуск бэкенда и его адрес.';
  const {status,data}=error.response;
  const detail=data?.detail;
  const oldFields=Array.isArray(detail)&&detail.some(item=>item.type==='extra_forbidden'&&
    item.loc?.some((field:unknown)=>field==='transport_modes'||field==='road_conditions'));
  if((status===404&&detail==='Not Found')||oldFields)
    return 'Запущена устаревшая версия бэкенда или выбран неверный адрес API. Остановите старый сервер и запустите Backend/start-dev.ps1, затем обновите страницу.';
  if(status===404&&detail==='Voyage not found.')
    return 'Сохранённый рейс отсутствует в базе этого сервера. Создайте новый исходный план или подключитесь к серверу, где он был сохранён.';
  if(status===409)return `Обновление не выполнено: ${typeof detail==='string'?detail:'Нет доступного маршрута при выбранных условиях.'}`;
  if(status===422)return `Проверьте параметры расчёта: ${typeof detail==='string'?detail:JSON.stringify(detail)}`;
  return `API ${status}: ${typeof detail==='string'?detail:'Ошибка сервера'}`;
}

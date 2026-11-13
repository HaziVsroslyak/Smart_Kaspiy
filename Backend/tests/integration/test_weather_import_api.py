import json
from tests.integration.test_security import SecurityTests

class WeatherImportAPITests(SecurityTests):
 def test_private_weather_import(self):
  headers=self.login()
  for name in ('alice','bob'):
   response=self.client.post('/api/v1/admin/users',headers=headers,json={'login':name,'email':name+'@example.com','password':'TemporaryPassword123!'})
   self.assertEqual(response.status_code,201,response.text)
  def enter(name):
   self.client.cookies.clear();h=self.login(name,'TemporaryPassword123!')
   response=self.client.post('/api/v1/auth/password',headers=h,json={'current_password':'TemporaryPassword123!','new_password':'ChangedPassword123!'})
   self.assertEqual(response.status_code,200,response.text)
   return {'Origin':'https://localhost','X-CSRF-Token':response.json()['csrf_token']}
  alice=enter('alice')
  payload={'format':'json','source_name':'manual file','content':json.dumps([{'timestamp':'2024-01-01T00:00:00Z','latitude':42,'longitude':50,'wind_speed_ms':12}])}
  response=self.client.post('/api/v1/weather/datasets/import',headers=alice,json=payload)
  self.assertEqual(response.status_code,201,response.text)
  identity=response.json()['id']
  point={'latitude':42,'longitude':50,'timestamp':'2024-01-01T00:00:00Z'}
  result=self.client.post(f'/api/v1/weather/datasets/{identity}/resolve',headers=alice,json=point)
  self.assertEqual(result.json()['gaps'],['wave_height_m'])
  enter('bob')
  self.assertEqual(self.client.get(f'/api/v1/weather/datasets/{identity}').status_code,404)
  self.assertEqual(self.client.get('/api/v1/weather/datasets').json(),[])

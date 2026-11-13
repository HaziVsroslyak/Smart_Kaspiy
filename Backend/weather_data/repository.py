"""Private immutable datasets; root can inspect, other accounts cannot share uploads."""
from fastapi import HTTPException
from auth.service import current_actor
from auth.context import request_actor
from .contracts import Dataset

class WeatherRepository:
    def __init__(self,database):self.database=database
    def save(self,dataset:Dataset)->Dataset:
        actor=request_actor.get()
        if actor is None:raise HTTPException(401,'Authentication required.')
        with self.database.transaction() as db:
            user=current_actor(db,actor,writing=True)
            db.execute('INSERT INTO weather_datasets VALUES (?,?,?)',(dataset.id,user.id,dataset.model_dump_json()))
        return dataset
    def get(self,identity:str)->Dataset:
        actor=request_actor.get()
        if actor is None:raise HTTPException(401,'Authentication required.')
        with self.database.connect() as db:
            user=current_actor(db,actor)
            row=db.execute('SELECT owner_id,payload FROM weather_datasets WHERE id=?',(identity,)).fetchone()
            if row is None or (row[0]!=user.id and user.role!='root'):raise HTTPException(404,'Weather dataset not found.')
            return Dataset.model_validate_json(row[1])
    def list(self)->list[Dataset]:
        actor=request_actor.get()
        if actor is None:raise HTTPException(401,'Authentication required.')
        with self.database.connect() as db:
            user=current_actor(db,actor)
            rows=db.execute('SELECT payload FROM weather_datasets WHERE owner_id=? OR ? ORDER BY rowid DESC LIMIT 100',(user.id,user.role=='root')).fetchall()
            return [Dataset.model_validate_json(row[0]) for row in rows]

"""Durable immutable baselines and versioned reforecasts, using stdlib SQLite."""
from __future__ import annotations
from contextlib import closing
import sqlite3
from pathlib import Path
from uuid import uuid4
from voyage_models import VoyageRequest, VoyageConditions, VoyageSnapshot, VoyageResponse

class VoyageStore:
    def __init__(self,path:Path) -> None:
        self.path=path
        path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS voyages (id TEXT PRIMARY KEY, request TEXT NOT NULL, baseline TEXT NOT NULL, current TEXT NOT NULL, conditions TEXT NOT NULL, revision INTEGER NOT NULL)')

    def create(self,request:VoyageRequest,snapshot:VoyageSnapshot) -> VoyageResponse:
        identity=str(uuid4())
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO voyages VALUES (?,?,?,?,?,0)',(identity,request.model_dump_json(),snapshot.model_dump_json(),snapshot.model_dump_json(),request.conditions.model_dump_json()))
        return self.get(identity)

    def get(self,identity:str) -> VoyageResponse:
        with closing(sqlite3.connect(self.path)) as db, db:
            row=db.execute('SELECT request,baseline,current,conditions,revision FROM voyages WHERE id=?',(identity,)).fetchone()
        if row is None: raise KeyError(identity)
        request=VoyageRequest.model_validate_json(row[0]); baseline=VoyageSnapshot.model_validate_json(row[1]); current=VoyageSnapshot.model_validate_json(row[2])
        before=[(s.source,s.target,s.edge_id) for s in baseline.fastest.segments]
        after=[(s.source,s.target,s.edge_id) for s in current.fastest.segments]
        return VoyageResponse(id=identity,request=request,conditions=VoyageConditions.model_validate_json(row[3]),baseline=baseline,current=current,revision=row[4],eta_change_hours=(current.fastest.eta-baseline.fastest.eta).total_seconds()/3600,route_changed=before!=after)

    def update(self,identity:str,snapshot:VoyageSnapshot,conditions:VoyageConditions,expected_revision:int) -> VoyageResponse:
        with closing(sqlite3.connect(self.path)) as db, db:
            result=db.execute('UPDATE voyages SET current=?, conditions=?, revision=revision+1 WHERE id=? AND revision=?',(snapshot.model_dump_json(),conditions.model_dump_json(),identity,expected_revision))
            if result.rowcount != 1: raise RuntimeError('A newer reforecast has already been saved. Reload the voyage.')
        return self.get(identity)

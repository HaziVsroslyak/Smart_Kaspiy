"""Durable immutable baselines and versioned reforecasts, using stdlib SQLite."""
from __future__ import annotations
from pathlib import Path
from uuid import uuid4
from storage import Database
from demo_contracts import DemoResult
from voyage_models import VoyageRequest, VoyageConditions, VoyageSnapshot, VoyageResponse
from auth.context import request_actor, accessed_resources
from auth.service import current_actor, audit
from fastapi import HTTPException

class VoyageStore:
    def __init__(self,path:Path) -> None:
        self.path=path
        self.database = Database(path)
        self.database.migrate()

    def create(self,request:VoyageRequest,snapshot:VoyageSnapshot) -> VoyageResponse:
        identity=str(uuid4())
        with self.database.transaction() as db:
            actor=request_actor.get()
            if actor: current_actor(db,actor,writing=True)
            db.execute('INSERT INTO voyages VALUES (?,?,?,?,?,0)',(identity,request.model_dump_json(),snapshot.model_dump_json(),snapshot.model_dump_json(),request.conditions.model_dump_json()))
            db.execute("INSERT INTO resource_owners(resource_type,resource_id,owner_id) VALUES ('voyage',?,?)",(identity,actor.user.id if actor else None))
        return self.get(identity)

    def save_demo(self, result: DemoResult) -> None:
        if not isinstance(result, DemoResult):
            raise TypeError('Expected a DemoResult')
        # Immutable runs; repeated computation creates a new run rather than replacing a baseline.
        with self.database.transaction() as db:
            actor=request_actor.get()
            if actor:
                current_actor(db,actor,writing=True)
                if result.parent_voyage_id: self._authorize(db,'voyage',result.parent_voyage_id,writing=True)
            db.execute('INSERT INTO demo_runs VALUES (?,?)', (result.id, result.model_dump_json()))
            db.execute("INSERT INTO resource_owners(resource_type,resource_id,owner_id,parent_voyage_id) VALUES ('demo',?,?,?)",(result.id,actor.user.id if actor else None,result.parent_voyage_id))

    def get_demo(self, identity: str) -> DemoResult:
        with self.database.connect() as db:
            self._authorize(db,'demo',identity)
            row = db.execute('SELECT result FROM demo_runs WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        return DemoResult.model_validate_json(row[0])

    def get(self,identity:str) -> VoyageResponse:
        with self.database.connect() as db:
            self._authorize(db,'voyage',identity)
            row=db.execute('SELECT request,baseline,current,conditions,revision FROM voyages WHERE id=?',(identity,)).fetchone()
        if row is None: raise KeyError(identity)
        request=VoyageRequest.model_validate_json(row[0]); baseline=VoyageSnapshot.model_validate_json(row[1]); current=VoyageSnapshot.model_validate_json(row[2])
        before=[(s.source,s.target,s.edge_id) for s in baseline.fastest.segments]
        after=[(s.source,s.target,s.edge_id) for s in current.fastest.segments]
        return VoyageResponse(id=identity,request=request,conditions=VoyageConditions.model_validate_json(row[3]),baseline=baseline,current=current,revision=row[4],eta_change_hours=(current.fastest.eta-baseline.fastest.eta).total_seconds()/3600,route_changed=before!=after)

    def update(self,identity:str,snapshot:VoyageSnapshot,conditions:VoyageConditions,expected_revision:int) -> VoyageResponse:
        with self.database.transaction() as db:
            self._authorize(db,'voyage',identity,writing=True)
            result=db.execute('UPDATE voyages SET current=?, conditions=?, revision=revision+1 WHERE id=? AND revision=?',(snapshot.model_dump_json(),conditions.model_dump_json(),identity,expected_revision))
            if result.rowcount != 1: raise RuntimeError('A newer reforecast has already been saved. Reload the voyage.')
        return self.get(identity)

    def _authorize(self,db,kind: str,identity: str,*,writing: bool=False) -> None:
        actor=request_actor.get()
        if actor is None:
            return  # Framework-independent internal calls, never an HTTP identity fallback.
        user=current_actor(db,actor,writing=writing)
        row=db.execute('SELECT owner_id FROM resource_owners WHERE resource_type=? AND resource_id=?',(kind,identity)).fetchone()
        if row is None or (row[0] is None and user.role!='root') or (user.role=='logistician' and row[0]!=user.id):
            raise HTTPException(404,'Resource not found.')
        resources=accessed_resources.get()
        if resources is not None and (kind,identity) not in resources:
            resources.append((kind,identity))

    def recheck_resources(self,resources: list[tuple[str,str]]) -> None:
        with self.database.connect() as db:
            for kind,identity in tuple(resources): self._authorize(db,kind,identity)

    def list_voyages(self) -> list[dict[str,object]]:
        actor=request_actor.get()
        if actor is None: raise HTTPException(401,'Authentication required.')
        with self.database.connect() as db:
            user=current_actor(db,actor)
            rows=db.execute("SELECT resource_id,owner_id,ownership_revision FROM resource_owners WHERE resource_type='voyage' ORDER BY resource_id").fetchall()
            visible=[row for row in rows if user.role=='root' or (row[1] is not None and (user.role=='admin' or row[1]==user.id))]
            for row in visible: self._authorize(db,'voyage',row[0])
            return [dict(zip(('id','owner_id','ownership_revision'),row)) for row in visible]

    def transfer(self,identity: str,destination: str,expected_revision: int) -> dict[str,object]:
        actor=request_actor.get()
        if actor is None: raise HTTPException(401,'Authentication required.')
        with self.database.transaction() as db:
            user=current_actor(db,actor)
            if user.role!='root': raise HTTPException(403,'Root required.')
            target=db.execute("SELECT 1 FROM users WHERE id=? AND role='logistician' AND status='active'",(destination,)).fetchone()
            if not target: raise HTTPException(422,'Destination must be an active logistician.')
            row=db.execute("SELECT owner_id,ownership_revision FROM resource_owners WHERE resource_type='voyage' AND resource_id=?",(identity,)).fetchone()
            if row is None: raise HTTPException(404,'Voyage not found.')
            if row[1]!=expected_revision: raise HTTPException(409,'Ownership has changed. Reload the voyage list.')
            db.execute("UPDATE resource_owners SET owner_id=?,ownership_revision=ownership_revision+1 WHERE resource_type='voyage' AND resource_id=?",(destination,identity))
            db.execute("UPDATE resource_owners SET owner_id=?,ownership_revision=ownership_revision+1 WHERE parent_voyage_id=?",(destination,identity))
            audit(db,user.id,'voyage_transferred',identity,{'previous_owner':row[0],'new_owner':destination})
        return {'id':identity,'owner_id':destination,'ownership_revision':expected_revision+1}

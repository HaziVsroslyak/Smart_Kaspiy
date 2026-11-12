import roadRoutes from './road-routes.json';
import type {RouteSegment} from '../api/client';

export type MapPoint = [latitude:number, longitude:number];
export const terminals:Record<string,MapPoint>={
  'Астрахань':[46.35,48.04], 'Махачкала':[42.98,47.5],
  'Энзели':[37.47,49.46], 'Решт':[37.28,49.58],
};

// Offshore display gates, deliberately separate from inland city markers.
// The river/delta approach to Astrakhan is not represented by a sea chord.
export const seaGates:Record<string,MapPoint>={
  'Астрахань':[44.95,49.25],
  'Махачкала':[42.99,47.60],
  'Энзели':[37.53,49.48],
};
// Schematic water corridors, not surveyed fairways. Keep southbound corridors
// offshore of the Absheron peninsula and approach Anzali from the north.
const lanes:Record<string,MapPoint[]>={
  'Астрахань|Энзели':[
    seaGates['Астрахань'],[44,49.8],[42.5,50.5],[41.2,51.2],
    [40.2,51.2],[39.2,51],[38.2,50.3],[37.75,49.8],seaGates['Энзели'],
  ],
  'Махачкала|Энзели':[
    seaGates['Махачкала'],[42.8,48.1],[42.2,49.2],[41.2,51.2],
    [40.2,51.2],[39.2,51],[38.2,50.3],[37.75,49.8],seaGates['Энзели'],
  ],
};

export function segmentGeometry(leg:Pick<RouteSegment,'source'|'target'|'transport_mode'>):MapPoint[]{
  if(leg.transport_mode==='road'){
    const routes:Record<string,{coordinates:number[][]}>=roadRoutes;
    const forward=routes[`${leg.source}|${leg.target}`]?.coordinates;
    const reverse=routes[`${leg.target}|${leg.source}`]?.coordinates;
    return (forward??reverse?.slice().reverse()??[]).map(([lat,lon])=>[lat,lon]);
  }
  if(leg.transport_mode==='ship'){
    const forward=lanes[`${leg.source}|${leg.target}`];
    const reverse=lanes[`${leg.target}|${leg.source}`];
    // Do not invent a straight sea line for an unsupported terminal pair.
    return (forward??reverse?.slice().reverse()??[]).map(point=>[...point]);
  }
  const start=terminals[leg.source],end=terminals[leg.target];
  return start&&end?[[...start],[...end]]:[];
}

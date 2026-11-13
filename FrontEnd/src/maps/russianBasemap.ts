import type {Map as LeafletMap, Layer} from 'leaflet';
import type {StyleSpecification} from 'maplibre-gl';
import {russianStyle} from './russianStyle';
import 'maplibre-gl/dist/maplibre-gl.css';

const attribution='© <a href="https://openfreemap.org/">OpenFreeMap</a> · <a href="https://openmaptiles.org/">OpenMapTiles</a> · <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

export function addRussianBasemap(map:LeafletMap,onError:()=>void):()=>void {
 let disposed=false;
 let layer:Layer|undefined;
 map.attributionControl.addAttribution(attribution);
 // Defer WebGL and its worker until an online map is actually mounted.
 void Promise.all([
  import('@maplibre/maplibre-gl-leaflet'), import('maplibre-gl'),
  import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'), import('./liberty-base.json'),
 ]).then(([binding,gl,worker,style])=>{
  if(disposed)return;
  gl.setWorkerUrl(worker.default);
  const vector=binding.maplibreGL({style:russianStyle(style.default as StyleSpecification)});
  layer=vector;
  vector.addTo(map);
  vector.getMaplibreMap().on('error',()=>{if(!disposed)onError();});
 }).catch(()=>{if(!disposed)onError();});
 return ()=>{
  disposed=true;
  if(layer&&map.hasLayer(layer))map.removeLayer(layer);
  map.attributionControl.removeAttribution(attribution);
 };
}

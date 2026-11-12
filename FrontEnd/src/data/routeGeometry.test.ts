import {describe,it,expect} from 'vitest';
import water from './caspian-water.json';
import {segmentGeometry} from './routeGeometry';
import roads from './road-routes.json';

type XY=number[];
function inRing([x,y]:XY,ring:XY[]):boolean{
  let inside=false;
  for(let i=0,j=ring.length-1;i<ring.length;j=i++){
    const a=ring[i],b=ring[j];
    if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])inside=!inside;
  }
  return inside;
}
const cross=(a:XY,b:XY,c:XY)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
function intersects(a:XY,b:XY,c:XY,d:XY):boolean{
  return cross(a,b,c)*cross(a,b,d)<0&&cross(c,d,a)*cross(c,d,b)<0;
}
describe('sea corridor geometry',()=>{
 it('draws every road edge with saved road geometry and supports reverse trips',()=>{
  for(const key of Object.keys(roads)){
   const [source,target]=key.split('|');
   const forward=segmentGeometry({source,target,transport_mode:'road'});
   expect(forward.length).toBeGreaterThan(10);
   expect(segmentGeometry({source:target,target:source,transport_mode:'road'})).toEqual(forward.slice().reverse());
  }
 });
 for(const source of ['Астрахань','Махачкала']){
  it(`${source}: all vertices are water and no leg crosses the coastline`,()=>{
   const points=segmentGeometry({source,target:'Энзели',transport_mode:'ship'}).map(([lat,lon])=>[lon,lat]);
   expect(points.length).toBeGreaterThan(2);
   for(const point of points){
    expect(inRing(point,water.coordinates[0]),JSON.stringify(point)).toBe(true);
    expect(water.coordinates.slice(1).some(ring=>inRing(point,ring))).toBe(false);
   }
   for(let i=1;i<points.length;i++) for(const ring of water.coordinates) for(let j=1;j<ring.length;j++){
    expect(intersects(points[i-1],points[i],ring[j-1],ring[j]),`coast crossing: ${points[i-1]} → ${points[i]}`).toBe(false);
   }
   const reverse=segmentGeometry({source:'Энзели',target:source,transport_mode:'ship'});
   expect(reverse).toEqual(segmentGeometry({source,target:'Энзели',transport_mode:'ship'}).reverse());
  });
 }
 it('never falls back to a land-crossing chord for an unknown sea connection',()=>{
  expect(segmentGeometry({source:'Астрахань',target:'Решт',transport_mode:'ship'})).toEqual([]);
 });
});

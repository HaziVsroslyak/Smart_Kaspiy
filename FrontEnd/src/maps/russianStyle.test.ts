import {describe,it,expect} from 'vitest';
import type {StyleSpecification} from 'maplibre-gl';
import {russianName,russianStyle} from './russianStyle';
import base from './liberty-base.json';
describe('Russian basemap labels',()=>{
 it('localizes all named layers in the shipped OpenFreeMap style',()=>{
  const localized=russianStyle(base as StyleSpecification);
  const named=localized.layers.filter(layer=>layer.type==='symbol'&&layer.layout?.['text-field']===russianName);
  expect(named.length).toBeGreaterThan(10);
  expect(JSON.stringify(named)).toContain('name:ru');
  expect(localized.sources).toEqual(base.sources);
 });
 it('preserves road references and never mutates the base style',()=>{
  const input:StyleSpecification={version:8,sources:{},layers:[
   {id:'city',type:'symbol',source:'test',layout:{'text-field':['get','name']}},
   {id:'road',type:'symbol',source:'test',layout:{'text-field':['get','ref']}},
  ]};
  const output=russianStyle(input);
  expect(output.layers[0]).not.toBe(input.layers[0]);
  expect(output.layers[1]).toBe(input.layers[1]);
  expect((input.layers[0] as {layout:object}).layout).toEqual({'text-field':['get','name']});
 });
});


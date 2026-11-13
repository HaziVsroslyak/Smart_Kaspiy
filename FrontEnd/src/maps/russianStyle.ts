import type {ExpressionSpecification, StyleSpecification} from 'maplibre-gl';

// OpenMapTiles carries language-specific names. Keep local names when Russian
// attribution is absent rather than inventing a translation for unknown objects.
export const russianName: ExpressionSpecification = ['coalesce',
 ['get','name:ru'], ['get','name_ru'],
 ['match',['coalesce',['get','name:en'],['get','name_en'],['get','name'],''],
  'Russia','Россия','Iran','Иран','Azerbaijan','Азербайджан','Georgia','Грузия',
  'Kazakhstan','Казахстан','Turkmenistan','Туркменистан','Armenia','Армения',
  'Turkey','Турция','Türkiye','Турция','Uzbekistan','Узбекистан',
  'Caspian Sea','Каспийское море','Black Sea','Чёрное море',
  ['coalesce',['get','name'],['get','name:latin'],'']]];

function referencesName(value: unknown): boolean {
 if(!Array.isArray(value))return false;
 return value[0]==='get'&&typeof value[1]==='string'&&value[1].startsWith('name') || value.some(referencesName);
}

export function russianStyle(style: StyleSpecification): StyleSpecification {
 return {...style,layers:style.layers.map(layer=>{
  if(layer.type!=='symbol'||!layer.layout)return layer;
  const field=layer.layout['text-field'];
  if(!referencesName(field)&&!(typeof field==='string'&&field.includes('{name')))return layer;
  return {...layer,layout:{...layer.layout,'text-field':russianName}};
 })};
}

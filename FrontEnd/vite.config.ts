import {defineConfig} from 'vite';

export default defineConfig({
  server:{proxy:{'/api':'http://127.0.0.1:8000','/docs':'http://127.0.0.1:8000','/openapi.json':'http://127.0.0.1:8000'}},
  build:{rollupOptions:{output:{manualChunks(id){
    if(id.includes('/src/data/road-routes.json'))return 'road-geometry';
  }}}},
});

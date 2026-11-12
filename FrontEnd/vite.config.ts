import {defineConfig} from 'vite';

export default defineConfig({
  build:{rollupOptions:{output:{manualChunks(id){
    if(id.includes('/src/data/road-routes.json'))return 'road-geometry';
  }}}},
});

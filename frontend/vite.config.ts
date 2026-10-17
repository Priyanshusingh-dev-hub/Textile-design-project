import { defineConfig } from 'vite'; import react from '@vitejs/plugin-react';
// strictPort: the engine accepts changes only from LoomLab's own origins (backend/app/origin_guard.py),
// and the dev server's is http://localhost:5173, so it must not drift to 5174 when 5173 is taken
export default defineConfig({plugins:[react()],server:{port:5173,strictPort:true,proxy:{'/api':'http://localhost:8003'}}});

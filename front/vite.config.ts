import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteStaticCopy } from 'vite-plugin-static-copy'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // 成片合成用的 ffmpeg.wasm 内核随站点一起部署到 /ffmpeg/（约 31 MB，仅在用户点「合成导出」时才下载）
    viteStaticCopy({
      targets: [{ src: 'node_modules/@ffmpeg/core/dist/esm/ffmpeg-core.{js,wasm}', dest: 'ffmpeg' }],
    }),
  ],
  appType: 'spa',
  server: {
    port: 7788,
    open: true,
  },
  optimizeDeps: {
    // @ffmpeg/ffmpeg 内部用 new Worker(new URL(...)) 加载 worker，预打包会破坏这个相对路径
    exclude: ['@ffmpeg/ffmpeg', '@ffmpeg/util'],
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})

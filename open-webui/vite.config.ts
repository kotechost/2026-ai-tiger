import { sveltekit } from '@sveltejs/kit/vite'
import { defineConfig } from 'vite'
import { viteStaticCopy } from 'vite-plugin-static-copy'

export default defineConfig({

  plugins: [
    sveltekit(),

    viteStaticCopy({
      targets: [
        {
          src: 'node_modules/onnxruntime-web/dist/*.jsep.*',
          dest: 'wasm'
        }
      ]
    })
  ],

  define: {
    APP_VERSION: JSON.stringify(process.env.npm_package_version),
    APP_BUILD_HASH: JSON.stringify(process.env.APP_BUILD_HASH || 'dev-build')
  },

  build: {
    sourcemap: true
  },

  worker: {
    format: 'es'
  },

  esbuild: {
    pure: process.env.ENV === 'dev'
      ? []
      : ['console.log', 'console.debug', 'console.error']
  },

  server: {
    port: 5173,

    watch: {
        ignored: ['**/data/**']
    },

    proxy: {

      '/api': {
        target: 'http://localhost:3000',
        changeOrigin: true
      },

      '/ollama': {
        target: 'http://localhost:11434',
        changeOrigin: true
      }

    }
  }

})
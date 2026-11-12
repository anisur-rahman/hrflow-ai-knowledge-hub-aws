import { createApp } from 'vue'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Tooltip from 'primevue/tooltip'
import Aura from '@primeuix/themes/aura'
import { definePreset } from '@primeuix/themes'
import 'primeicons/primeicons.css'
import './style.css'
import App from './App.vue'
import router from './router'
import { errorMessage } from './services/api'
import { bootstrap } from './services/session'

const HRFlow = definePreset(Aura, {
  semantic: {
    primary: {
      50: '{blue.50}', 100: '{blue.100}', 200: '{blue.200}', 300: '{blue.300}', 400: '{blue.400}',
      500: '{blue.600}', 600: '{blue.700}', 700: '{blue.800}', 800: '{blue.900}', 900: '{blue.950}', 950: '{blue.950}',
    },
  },
})

async function start() {
  try {
    await bootstrap() // config + auth (incl. the Cognito redirect) before the router's first navigation
  } catch (error) {
    const box = document.createElement('p')
    box.className = 'boot-error'
    box.textContent = `Could not start the application: ${errorMessage(error)}`
    document.getElementById('app')?.replaceChildren(box)
    return
  }
  createApp(App)
    .use(PrimeVue, { theme: { preset: HRFlow, options: { darkModeSelector: '.app-dark' } } })
    .use(ToastService)
    .use(ConfirmationService)
    .use(router)
    .directive('tooltip', Tooltip)
    .mount('#app')
}

start()

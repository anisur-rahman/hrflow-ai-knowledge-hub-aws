import { computed, ref, shallowRef } from 'vue'
import { getMe, loadConfig, type AppConfig, type Me } from './api'
import { initAuth, isSignedIn } from './auth'

/** App-wide state: public config (loaded before sign-in) and the signed-in user's profile. */
export const appConfig = shallowRef<AppConfig | null>(null)
export const profile = ref<Me | null>(null)
export const isAdmin = computed(() => !!profile.value?.is_admin)

export function config(): AppConfig {
  if (!appConfig.value) throw new Error('Configuration not loaded')
  return appConfig.value
}

export async function bootstrap() {
  appConfig.value = await loadConfig()
  await initAuth(appConfig.value) // completes the Cognito redirect if we are returning from sign-in
  await loadProfile()
}

export async function loadProfile() {
  profile.value = isSignedIn.value ? await getMe() : null
}

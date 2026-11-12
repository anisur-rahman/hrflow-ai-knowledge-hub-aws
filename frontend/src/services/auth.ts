import { computed, ref } from 'vue'
import { User, UserManager, WebStorageStateStore } from 'oidc-client-ts'
import type { AppConfig } from './api'

const API_KEY_STORAGE = 'hrflow_api_key'
let manager: UserManager | null = null
let config: AppConfig | null = null

const user = ref<User | null>(null)
const apiKey = ref(readStorage(API_KEY_STORAGE))
export const sessionExpired = ref(false)

export const isSignedIn = computed(() =>
  config?.auth_mode === 'cognito' ? !!user.value && !user.value.expired : !!apiKey.value)

export async function initAuth(appConfig: AppConfig) {
  config = appConfig
  if (appConfig.auth_mode !== 'cognito' || !appConfig.cognito) return
  const origin = window.location.origin
  manager = new UserManager({
    authority: appConfig.cognito.authority,
    client_id: appConfig.cognito.client_id,
    redirect_uri: `${origin}/`,
    post_logout_redirect_uri: `${origin}/`,
    response_type: 'code', // authorization code + PKCE, no client secret in the browser
    scope: 'openid email profile',
    automaticSilentRenew: true,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  })
  manager.events.addUserLoaded((loaded) => { user.value = loaded; sessionExpired.value = false })
  manager.events.addUserUnloaded(() => { user.value = null })
  manager.events.addAccessTokenExpired(() => { sessionExpired.value = true })

  const params = new URLSearchParams(window.location.search)
  if (params.has('code') && params.has('state')) {
    user.value = await manager.signinRedirectCallback()
    window.history.replaceState({}, document.title, window.location.pathname)
  } else {
    const stored = await manager.getUser()
    user.value = stored && !stored.expired ? stored : null
  }
}

export function authHeaders(): Record<string, string> {
  if (config?.auth_mode === 'cognito') return user.value ? { Authorization: `Bearer ${user.value.access_token}` } : {}
  return apiKey.value ? { 'X-API-Key': apiKey.value } : {}
}

export async function signIn() {
  await manager?.signinRedirect()
}

export function useApiKey(key: string) {
  apiKey.value = key.trim()
  writeStorage(API_KEY_STORAGE, apiKey.value)
}

export function handleUnauthorized() {
  sessionExpired.value = true
}

export async function signOut() {
  if (manager && config?.cognito) {
    await manager.removeUser()
    // Cognito's hosted UI has its own logout endpoint (not advertised in OIDC discovery).
    const url = new URL('/logout', config.cognito.domain)
    url.searchParams.set('client_id', config.cognito.client_id)
    url.searchParams.set('logout_uri', `${window.location.origin}/`)
    window.location.assign(url.toString())
    return
  }
  useApiKey('')
}

function readStorage(key: string): string {
  try { return window.localStorage.getItem(key) ?? '' } catch { return '' }
}

function writeStorage(key: string, value: string) {
  try {
    if (value) window.localStorage.setItem(key, value)
    else window.localStorage.removeItem(key)
  } catch { /* storage unavailable: key lasts for this page only */ }
}

<script setup lang="ts">
import { watch } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'
import Button from 'primevue/button'
import Message from 'primevue/message'
import LoginView from './views/LoginView.vue'
import { isSignedIn, sessionExpired, signIn, signOut } from './services/auth'
import { config, isAdmin, loadProfile, profile } from './services/session'

const router = useRouter()
const cfg = config()

// API-key sign-in/out happens in place (Cognito sign-in is a full-page redirect handled in bootstrap).
watch(isSignedIn, async () => {
  await loadProfile()
  if (profile.value) await router.replace('/')
})
</script>

<template>
  <Toast position="top-right" />
  <ConfirmDialog />
  <LoginView v-if="!isSignedIn || !profile" :config="cfg" />
  <div v-else class="shell">
    <aside>
      <div class="brand"><i class="pi pi-sparkles" /> HRFlow <span>AI Hub</span></div>
      <p class="aside-title">KNOWLEDGE</p>
      <RouterLink v-if="isAdmin" to="/dashboard" class="nav"><i class="pi pi-chart-bar" /> <span>Dashboard</span></RouterLink>
      <RouterLink to="/documents" class="nav">
        <i class="pi pi-folder-open" /> <span>{{ isAdmin ? 'Documents' : 'Policy library' }}</span>
      </RouterLink>
      <RouterLink to="/chat" class="nav"><i class="pi pi-comments" /> <span>Policy assistant</span></RouterLink>
      <div class="sidebar-bottom">
        <div class="user"><i class="pi pi-user" /> {{ profile.username }}</div>
        <small>{{ profile.groups.join(', ') || 'no groups' }}</small>
        <Button label="Sign out" icon="pi pi-sign-out" text size="small" class="signout" @click="signOut" />
      </div>
    </aside>
    <main>
      <Message v-if="sessionExpired" severity="warn" class="mb">
        Your session has expired.
        <Button v-if="cfg.auth_mode === 'cognito'" label="Sign in again" link @click="signIn" />
        <Button v-else label="Change API key" link @click="signOut" />
      </Message>
      <Message v-if="cfg.ai_provider === 'mock'" severity="info" class="mb" closable>
        Local demo mode: answers are retrieved excerpts and embeddings are token hashes, not Bedrock AI.
      </Message>
      <RouterView />
    </main>
  </div>
</template>

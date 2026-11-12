<script setup lang="ts">
import { ref } from 'vue'
import Button from 'primevue/button'
import Password from 'primevue/password'
import type { AppConfig } from '../services/api'
import { signIn, useApiKey } from '../services/auth'

defineProps<{ config: AppConfig }>()
const key = ref('')
</script>

<template>
  <div class="login">
    <div class="login-card">
      <div class="brand dark"><i class="pi pi-sparkles" /> HRFlow <span>AI Hub</span></div>
      <h1>HR &amp; Operations Knowledge Hub</h1>
      <p class="muted">Ask policy questions with cited answers, and manage the documents behind them.</p>
      <Button v-if="config.auth_mode === 'cognito'" label="Sign in with your company account" icon="pi pi-sign-in"
              class="full" @click="signIn" />
      <form v-else class="stack" @submit.prevent="useApiKey(key)">
        <label for="api-key">Local demo API key</label>
        <Password v-model="key" input-id="api-key" :feedback="false" toggle-mask fluid placeholder="API_KEY from .env" />
        <Button type="submit" label="Continue" :disabled="!key" />
        <small class="muted">Local development only. AWS deployments use Amazon Cognito sign-in.</small>
      </form>
    </div>
  </div>
</template>

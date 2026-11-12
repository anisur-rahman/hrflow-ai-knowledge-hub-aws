<script setup lang="ts">
import { ref } from 'vue'
import Button from 'primevue/button'
import AIChatbot from '../components/AIChatbot.vue'

const chatbot = ref<InstanceType<typeof AIChatbot> | null>(null)
</script>

<template>
  <header class="page-head">
    <div>
      <p class="eyebrow">EMPLOYEE SELF-SERVICE</p>
      <h1>Policy assistant</h1>
      <p class="muted">Answers come only from published policies you are allowed to see, with page citations.</p>
    </div>
    <Button label="New conversation" icon="pi pi-plus" outlined size="small" @click="chatbot?.reset()" />
  </header>
  <AIChatbot ref="chatbot" />
</template>

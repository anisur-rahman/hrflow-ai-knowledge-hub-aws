<script setup lang="ts">
import { onMounted } from 'vue'
import DocumentList from '../components/DocumentList.vue'
import DocumentUpload from '../components/DocumentUpload.vue'
import { useDocuments } from '../services/documents'
import { isAdmin } from '../services/session'

const store = useDocuments()
onMounted(() => store.refresh())
</script>

<template>
  <header class="page-head">
    <div>
      <p class="eyebrow">KNOWLEDGE LIBRARY</p>
      <h1>{{ isAdmin ? 'Documents' : 'Policy library' }}</h1>
      <p class="muted">{{ isAdmin
        ? 'Upload PDFs, follow extraction status, and approve AI categories and summaries.'
        : 'Published policies available to you.' }}</p>
    </div>
  </header>
  <DocumentUpload v-if="isAdmin" @uploaded="store.refresh(true)" />
  <DocumentList :store="store" show-filter>
    <template v-if="isAdmin" #empty>No documents yet. Upload a policy PDF to get started.</template>
  </DocumentList>
</template>

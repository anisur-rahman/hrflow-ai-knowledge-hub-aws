<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import { RouterLink } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import DocumentList from '../components/DocumentList.vue'
import { IN_FLIGHT, errorMessage, getAuditEvents, getStats, type AuditEvent, type Stats } from '../services/api'
import { useDocuments } from '../services/documents'

const toast = useToast()
const store = useDocuments()
const stats = ref<Stats | null>(null)
const events = ref<AuditEvent[]>([])

const ACTIONS: Record<string, string> = {
  'document.created': 'uploaded', 'document.approved': 'published', 'document.rejected': 'rejected',
  'document.reprocess_requested': 'requested reprocessing of', 'document.deleted': 'deleted',
  'document.source_opened': 'opened', 'chat.asked': 'asked the assistant a question',
}

const count = (...statuses: string[]) =>
  statuses.reduce((sum, s) => sum + (stats.value?.documents_by_status[s as keyof Stats['documents_by_status']] ?? 0), 0)
const cards = computed(() => [
  { label: 'Needs review', value: count('pending_review'), icon: 'pi-eye' },
  { label: 'Published', value: count('published'), icon: 'pi-check-circle' },
  { label: 'Processing', value: count(...IN_FLIGHT), icon: 'pi-spinner' },
  { label: 'Failed', value: count('failed'), icon: 'pi-exclamation-triangle' },
  { label: 'Questions (7 days)', value: stats.value?.questions_7d ?? 0, icon: 'pi-comments' },
  { label: 'Unanswered (7 days)', value: stats.value?.unanswered_7d ?? 0, icon: 'pi-question-circle',
    hint: 'No authorized evidence was found: a sign of missing or unpublished policies.' },
])

function describe(event: AuditEvent): string {
  const title = (event.details.title as string | undefined)
    ?? store.documents.value.find((d) => d.id === event.document_id)?.title ?? ''
  return `${ACTIONS[event.action] ?? event.action} ${title}`.trim()
}

async function load() {
  try {
    const [loadedStats, loadedEvents] = await Promise.all([getStats(), getAuditEvents(12), store.refresh()])
    stats.value = loadedStats
    events.value = loadedEvents
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Could not load the dashboard', detail: errorMessage(error), life: 6000 })
  }
}

onMounted(load)
</script>

<template>
  <header class="page-head">
    <div>
      <p class="eyebrow">HR OPERATIONS</p>
      <h1>Dashboard</h1>
      <p class="muted">Review AI-processed documents before employees can use them, and watch how the assistant is doing.</p>
    </div>
    <div class="row">
      <RouterLink to="/documents"><Button label="Upload documents" icon="pi pi-upload" /></RouterLink>
      <Button icon="pi pi-refresh" outlined aria-label="Refresh dashboard" @click="load" />
    </div>
  </header>

  <div class="stats">
    <div v-for="c in cards" :key="c.label" class="card stat" v-tooltip.top="c.hint">
      <i :class="['pi', c.icon]" /><strong>{{ c.value }}</strong><span>{{ c.label }}</span>
    </div>
  </div>

  <DocumentList :store="store" title="Review queue" :only="['pending_review']" :rows="5">
    <template #empty>Nothing waiting for review.</template>
  </DocumentList>
  <DocumentList :store="store" title="Needs attention" :only="['failed', 'ocr_pending', 'processing']" :rows="5">
    <template #empty>No failed or in-progress documents.</template>
  </DocumentList>

  <section class="card">
    <h2>Recent activity</h2>
    <ul class="activity">
      <li v-for="e in events" :key="e.id">
        <span class="muted">{{ new Date(e.created_at).toLocaleString() }}</span>
        <span><strong>{{ e.actor }}</strong> {{ describe(e) }}</span>
      </li>
      <li v-if="!events.length" class="muted">No activity yet.</li>
    </ul>
  </section>
</template>

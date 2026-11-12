<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import SelectButton from 'primevue/selectbutton'
import { IN_FLIGHT, type DocumentRecord, type Status } from '../services/api'
import type { DocumentStore } from '../services/documents'
import { config, isAdmin } from '../services/session'
import ReviewDialog from './ReviewDialog.vue'

const props = withDefaults(defineProps<{
  store: DocumentStore
  title?: string
  only?: Status[] // fixed status filter (e.g. the dashboard's review queue)
  showFilter?: boolean
  rows?: number
}>(), { title: 'Documents', only: undefined, showFilter: false, rows: 10 })

const STATUS: Record<Status, { label: string; severity: string }> = {
  awaiting_upload: { label: 'Uploading', severity: 'secondary' },
  queued: { label: 'Queued', severity: 'info' },
  processing: { label: 'Extracting', severity: 'info' },
  ocr_pending: { label: 'OCR running', severity: 'info' },
  pending_review: { label: 'Needs review', severity: 'warn' },
  published: { label: 'Published', severity: 'success' },
  rejected: { label: 'Rejected', severity: 'secondary' },
  failed: { label: 'Failed', severity: 'danger' },
}
const FILTERS: { label: string; value: string; statuses: Status[] | null }[] = [
  { label: 'All', value: 'all', statuses: null },
  { label: 'Needs review', value: 'review', statuses: ['pending_review'] },
  { label: 'Published', value: 'published', statuses: ['published'] },
  { label: 'Problems', value: 'problems', statuses: ['failed', 'rejected'] },
]

const filter = ref('all')
const reviewing = ref<DocumentRecord | null>(null)
const rowsShown = computed(() => {
  const statuses = props.only ?? FILTERS.find((f) => f.value === filter.value)?.statuses
  const docs = props.store.documents.value
  return statuses ? docs.filter((d) => statuses.includes(d.status)) : docs
})
const inFlight = (doc: DocumentRecord) => IN_FLIGHT.includes(doc.status)

function saved(doc: DocumentRecord) {
  props.store.replace(doc)
  reviewing.value = null
}
</script>

<template>
  <section class="card">
    <div class="section-head">
      <h2>{{ title }}</h2>
      <div class="row">
        <SelectButton v-if="showFilter && isAdmin" v-model="filter" :options="FILTERS" option-label="label" option-value="value"
                      :allow-empty="false" size="small" />
        <Button icon="pi pi-refresh" text rounded aria-label="Refresh" :loading="store.loading.value" @click="store.refresh()" />
      </div>
    </div>
    <DataTable :value="rowsShown" :loading="store.loading.value" data-key="id" :paginator="rowsShown.length > rows" :rows="rows"
               striped-rows>
      <template #empty>
        <div class="empty"><slot name="empty">{{ isAdmin ? 'No documents here.' : 'No policies have been published for you yet.' }}</slot></div>
      </template>
      <Column header="Document" style="min-width: 16rem">
        <template #body="{ data }">
          <div class="doc-title"><i class="pi pi-file-pdf" /> <strong>{{ data.title }}</strong>
            <span v-if="data.version_label" class="muted"> · v{{ data.version_label }}</span></div>
          <p class="doc-summary">{{ data.summary || data.status_detail || '—' }}</p>
        </template>
      </Column>
      <Column field="category" header="Category" class="hide-sm" />
      <Column v-if="isAdmin" header="Status">
        <template #body="{ data }">
          <Tag :value="STATUS[data.status as Status].label" :severity="STATUS[data.status as Status].severity"
               :icon="inFlight(data) ? 'pi pi-spin pi-spinner' : undefined" v-tooltip.top="data.status_detail || undefined" />
        </template>
      </Column>
      <Column v-if="isAdmin" header="Visible to" class="hide-sm">
        <template #body="{ data }"><span class="muted">{{ data.allowed_groups.join(', ') }}</span></template>
      </Column>
      <Column header="Updated" class="hide-sm">
        <template #body="{ data }"><span class="muted">{{ new Date(data.updated_at).toLocaleDateString() }}</span></template>
      </Column>
      <Column header="" style="width: 1%; white-space: nowrap">
        <template #body="{ data }">
          <Button v-if="isAdmin && ['pending_review', 'published', 'rejected'].includes(data.status)"
                  :label="data.status === 'pending_review' ? 'Review' : 'Edit'" size="small"
                  :outlined="data.status !== 'pending_review'" @click="reviewing = data" />
          <Button v-if="!inFlight(data)" icon="pi pi-external-link" text rounded size="small" aria-label="Open PDF"
                  v-tooltip.top="'Open PDF'" @click="store.open(data)" />
          <Button v-if="isAdmin" icon="pi pi-replay" text rounded size="small" aria-label="Reprocess"
                  v-tooltip.top="'Reprocess'" :disabled="inFlight(data)" @click="store.reprocess(data)" />
          <Button v-if="isAdmin" icon="pi pi-trash" text rounded size="small" severity="danger" aria-label="Delete"
                  v-tooltip.top="'Delete'" :disabled="data.status === 'processing'" @click="store.remove(data)" />
        </template>
      </Column>
    </DataTable>
    <ReviewDialog :document="reviewing" :config="config()" @close="reviewing = null" @saved="saved" />
  </section>
</template>

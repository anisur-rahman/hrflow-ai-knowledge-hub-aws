<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import InputText from 'primevue/inputtext'
import MultiSelect from 'primevue/multiselect'
import Message from 'primevue/message'
import { useToast } from 'primevue/usetoast'
import { errorMessage, openSource, reviewDocument, type AppConfig, type DocumentRecord } from '../services/api'

const props = defineProps<{ document: DocumentRecord | null; config: AppConfig }>()
const emit = defineEmits<{ close: []; saved: [DocumentRecord] }>()
const toast = useToast()

const category = ref('')
const summary = ref('')
const versionLabel = ref('')
const groups = ref<string[]>([])
const saving = ref(false)

watch(() => props.document, (doc) => {
  if (!doc) return
  category.value = doc.category ?? 'Uncategorized'
  summary.value = doc.summary ?? ''
  versionLabel.value = doc.version_label ?? ''
  groups.value = [...doc.allowed_groups]
}, { immediate: true })

const visible = computed({ get: () => !!props.document, set: (open) => { if (!open) emit('close') } })
const groupOptions = computed(() => [...new Set([...props.config.groups, ...groups.value])])
const edited = computed(() => !!props.document && summary.value.trim() !== (props.document.ai_summary ?? '').trim())
const canApprove = computed(() => summary.value.trim().length > 0 && groups.value.length > 0)

async function submit(action: 'approve' | 'reject') {
  if (!props.document) return
  saving.value = true
  try {
    const saved = await reviewDocument(props.document.id, action === 'approve'
      ? { action, category: category.value, summary: summary.value.trim(), allowed_groups: groups.value,
          version_label: versionLabel.value.trim() || undefined }
      : { action })
    toast.add({ severity: 'success', summary: action === 'approve' ? 'Published' : 'Rejected', detail: saved.title, life: 3000 })
    emit('saved', saved)
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Review failed', detail: errorMessage(error), life: 6000 })
  } finally {
    saving.value = false
  }
}

async function preview() {
  if (!props.document) return
  try { await openSource(props.document.id) } catch (error) {
    toast.add({ severity: 'error', summary: 'Could not open PDF', detail: errorMessage(error), life: 5000 })
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" modal :header="document ? `Review: ${document.title}` : ''" :style="{ width: 'min(760px, 95vw)' }">
    <div v-if="document" class="stack">
      <Message severity="secondary" :closable="false">
        AI proposed <strong>{{ document.ai_category }}</strong> from {{ document.page_count }} pages
        ({{ document.extraction_method === 'textract' ? 'Textract OCR' : 'digital text' }}, {{ document.chunk_count }} sections).
        Check the summary against the PDF before publishing; employees only see published documents.
      </Message>
      <div class="grid2">
        <label class="field">Category
          <Select v-model="category" :options="config.categories" fluid />
        </label>
        <label class="field">Version
          <InputText v-model="versionLabel" placeholder="e.g. 2026.1" maxlength="50" fluid />
        </label>
      </div>
      <label class="field">Who can see it
        <MultiSelect v-model="groups" :options="groupOptions" display="chip" placeholder="Select groups" fluid />
      </label>
      <label class="field">Summary <small v-if="edited" class="muted">(edited from the AI proposal)</small>
        <Textarea v-model="summary" rows="6" maxlength="2000" auto-resize fluid />
      </label>
      <details v-if="edited" class="muted"><summary>Original AI summary</summary><p>{{ document.ai_summary }}</p></details>
    </div>
    <template #footer>
      <Button label="Open PDF" icon="pi pi-external-link" text @click="preview" />
      <span class="spacer" />
      <Button v-if="document?.status !== 'rejected'" label="Reject" severity="danger" outlined :loading="saving" @click="submit('reject')" />
      <Button :label="document?.status === 'published' ? 'Save & keep published' : 'Approve & publish'" icon="pi pi-check"
              :disabled="!canApprove" :loading="saving" @click="submit('approve')" />
    </template>
  </Dialog>
</template>

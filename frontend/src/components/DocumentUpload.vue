<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import MultiSelect from 'primevue/multiselect'
import { useToast } from 'primevue/usetoast'
import { errorMessage, uploadDocument, type DocumentRecord } from '../services/api'
import { config } from '../services/session'

const emit = defineEmits<{ uploaded: [DocumentRecord] }>()
const toast = useToast()
const cfg = config()

const file = ref<File | null>(null)
const input = ref<HTMLInputElement | null>(null)
const groups = ref<string[]>([...cfg.default_groups])
const version = ref('')
const uploading = ref(false)
const maxMb = computed(() => Math.round(cfg.max_upload_bytes / (1024 * 1024)))

function pick(event: Event) {
  const picked = (event.target as HTMLInputElement).files?.[0] ?? null
  file.value = null
  if (!picked) return
  if (!picked.name.toLowerCase().endsWith('.pdf')) toast.add({ severity: 'warn', summary: 'PDF files only', life: 4000 })
  else if (picked.size > cfg.max_upload_bytes) toast.add({ severity: 'warn', summary: `The limit is ${maxMb.value} MB`, life: 4000 })
  else file.value = picked
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  try {
    const doc = await uploadDocument(file.value, groups.value, version.value)
    toast.add({ severity: 'success', summary: 'Uploaded', detail: `${doc.title} is being processed`, life: 4000 })
    file.value = null
    version.value = ''
    if (input.value) input.value.value = ''
    emit('uploaded', doc)
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Upload failed', detail: errorMessage(error), life: 6000 })
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <section class="card">
    <h2>Upload policy document</h2>
    <p class="muted">PDF up to {{ maxMb }} MB.
      {{ cfg.storage_provider === 's3'
        ? 'The file goes straight to a private S3 bucket; extraction, OCR and AI processing run in the background.'
        : 'Stored locally and processed in the background.' }}</p>
    <div class="upload">
      <input ref="input" type="file" accept="application/pdf,.pdf" aria-label="PDF file" @change="pick" />
      <InputText v-model="version" placeholder="Version (optional)" maxlength="50" class="version" />
      <MultiSelect v-model="groups" :options="cfg.groups" display="chip" placeholder="Visible to" class="groups" />
      <Button label="Upload & process" icon="pi pi-upload" :loading="uploading" :disabled="!file || !groups.length" @click="upload" />
    </div>
  </section>
</template>

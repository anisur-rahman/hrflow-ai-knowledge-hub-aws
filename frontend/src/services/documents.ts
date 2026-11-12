import { onBeforeUnmount, ref } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import {
  IN_FLIGHT, deleteDocument, errorMessage, listDocuments, openSource, reprocessDocument, type DocumentRecord,
} from './api'

export type DocumentStore = ReturnType<typeof useDocuments>

/** Document list with polling while anything is processing, plus the row actions. */
export function useDocuments() {
  const toast = useToast()
  const confirm = useConfirm()
  const documents = ref<DocumentRecord[]>([])
  const loading = ref(false)
  let timer: number | undefined

  const fail = (summary: string, error: unknown) =>
    toast.add({ severity: 'error', summary, detail: errorMessage(error), life: 6000 })

  async function refresh(quiet = false) {
    if (!quiet) loading.value = true
    try {
      documents.value = await listDocuments()
    } catch (error) {
      if (!quiet) fail('Could not load documents', error)
    } finally {
      loading.value = false
      window.clearTimeout(timer)
      if (documents.value.some((d) => IN_FLIGHT.includes(d.status))) timer = window.setTimeout(() => refresh(true), 3000)
    }
  }

  function replace(updated: DocumentRecord) {
    documents.value = documents.value.map((d) => (d.id === updated.id ? updated : d))
  }

  async function reprocess(doc: DocumentRecord) {
    try {
      replace(await reprocessDocument(doc.id))
      toast.add({ severity: 'info', summary: 'Reprocessing', detail: doc.title, life: 3000 })
      await refresh(true)
    } catch (error) {
      fail('Could not reprocess', error)
    }
  }

  function remove(doc: DocumentRecord) {
    confirm.require({
      header: 'Delete document',
      message: `Delete "${doc.title}" and its search index? Employees will no longer get answers from it.`,
      icon: 'pi pi-trash',
      rejectProps: { label: 'Cancel', severity: 'secondary', outlined: true },
      acceptProps: { label: 'Delete', severity: 'danger' },
      accept: async () => {
        try {
          await deleteDocument(doc.id)
          documents.value = documents.value.filter((d) => d.id !== doc.id)
        } catch (error) {
          fail('Delete failed', error)
        }
      },
    })
  }

  async function open(doc: DocumentRecord, page?: number) {
    try { await openSource(doc.id, page) } catch (error) { fail('Could not open PDF', error) }
  }

  onBeforeUnmount(() => window.clearTimeout(timer))
  return { documents, loading, refresh, replace, reprocess, remove, open }
}

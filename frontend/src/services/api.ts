import axios from 'axios'
import { authHeaders, handleUnauthorized } from './auth'

export interface AppConfig {
  auth_mode: 'apikey' | 'cognito'
  cognito: { authority: string; client_id: string; domain: string } | null
  ai_provider: 'mock' | 'bedrock'
  storage_provider: 'local' | 's3'
  max_upload_bytes: number
  admin_group: string
  groups: string[]
  default_groups: string[]
  categories: string[]
  demo_api_key: string | null // only for local demos using the default key
}

export interface Me { username: string; groups: string[]; is_admin: boolean }

export type Status =
  | 'awaiting_upload' | 'queued' | 'processing' | 'ocr_pending' | 'pending_review' | 'published' | 'rejected' | 'failed'

export interface DocumentRecord {
  id: string
  title: string
  version_label: string | null
  status: Status
  status_detail: string | null
  category: string | null
  summary: string | null
  ai_category: string | null
  ai_summary: string | null
  allowed_groups: string[]
  page_count: number | null
  chunk_count: number | null
  size_bytes: number | null
  extraction_method: string | null
  uploaded_by: string
  reviewed_by: string | null
  reviewed_at: string | null
  created_at: string
  updated_at: string
}

export interface Source {
  document_id: string
  title: string
  version: string | null
  page: number
  heading: string | null
  excerpt: string
  score: number
}

export interface ChatTurn { role: 'user' | 'assistant'; content: string }
export interface ChatReply { answer: string; mode: string; sources: Source[] }
export interface ReviewChanges {
  action: 'approve' | 'reject'
  category?: string
  summary?: string
  version_label?: string
  allowed_groups?: string[]
}

export interface Stats {
  documents_by_status: Partial<Record<Status, number>>
  searchable_chunks: number
  questions_7d: number
  unanswered_7d: number
}

export interface AuditEvent {
  id: string
  actor: string
  action: string
  document_id: string | null
  details: Record<string, unknown>
  created_at: string
}

interface LinkTarget { url: string; fields?: Record<string, string>; requires_auth: boolean }

export const IN_FLIGHT: Status[] = ['awaiting_upload', 'queued', 'processing', 'ocr_pending']

const http = axios.create({ baseURL: '/api', timeout: 60_000 })
http.interceptors.request.use((request) => {
  for (const [name, value] of Object.entries(authHeaders())) request.headers.set(name, value)
  return request
})
http.interceptors.response.use(undefined, (error) => {
  if (axios.isAxiosError(error) && error.response?.status === 401) handleUnauthorized()
  return Promise.reject(error)
})

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg ?? 'Invalid input').join('; ')
    if (error.response?.status === 401) return 'Your session has expired. Please sign in again.'
    if (error.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}

export const loadConfig = async () => (await axios.get<AppConfig>('/api/config')).data
export const getMe = async () => (await http.get<Me>('/me')).data
export const listDocuments = async () => (await http.get<DocumentRecord[]>('/documents')).data
export const reviewDocument = async (id: string, changes: ReviewChanges) =>
  (await http.patch<DocumentRecord>(`/documents/${id}/review`, changes)).data
export const reprocessDocument = async (id: string) => (await http.post<DocumentRecord>(`/documents/${id}/reprocess`)).data
export const deleteDocument = async (id: string) => { await http.delete(`/documents/${id}`) }
export const getStats = async () => (await http.get<Stats>('/admin/stats')).data
export const getAuditEvents = async (limit = 15) =>
  (await http.get<AuditEvent[]>('/admin/audit-events', { params: { limit } })).data
export const askAssistant = async (question: string, history: ChatTurn[]) =>
  (await http.post<ChatReply>('/chat', { question, history })).data

/** Two-step upload: the API creates the record and returns a target (presigned S3 POST in AWS). */
export async function uploadDocument(file: File, allowedGroups: string[], versionLabel: string) {
  const { data } = await http.post<{ document: DocumentRecord; upload: LinkTarget }>('/documents', {
    filename: file.name, size_bytes: file.size, allowed_groups: allowedGroups, version_label: versionLabel || null,
  })
  const form = new FormData()
  for (const [name, value] of Object.entries(data.upload.fields ?? {})) form.append(name, value)
  form.append('file', file) // S3 requires the file to be the last field
  // Never send our bearer token to S3; only the API's own upload endpoint needs it.
  await axios.post(data.upload.url, form, { headers: data.upload.requires_auth ? authHeaders() : {}, timeout: 120_000 })
  return data.document
}

/** Opens the authorized source PDF at the cited page. */
export async function openSource(documentId: string, page?: number) {
  const viewer = window.open('', '_blank') // open synchronously so pop-up blockers allow it
  try {
    const { data } = await http.get<LinkTarget>(`/documents/${documentId}/source`)
    let url = data.url
    if (data.requires_auth) {
      const blob = await axios.get<Blob>(data.url, { headers: authHeaders(), responseType: 'blob' })
      url = URL.createObjectURL(blob.data)
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    }
    const target = page ? `${url}#page=${page}` : url
    if (viewer) viewer.location.href = target
    else window.location.assign(target)
  } catch (error) {
    viewer?.close()
    throw error
  }
}

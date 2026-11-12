<script setup lang="ts">
import { nextTick, ref } from 'vue'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import { askAssistant, errorMessage, openSource, type ChatTurn, type Source } from '../services/api'

const toast = useToast()

interface Message extends ChatTurn { sources?: Source[] }
const messages = ref<Message[]>([])
const question = ref('')
const busy = ref(false)
const thread = ref<HTMLElement | null>(null)
const suggestions = [
  'Can I buy an ergonomic desk chair, and how much can I claim?',
  'When must I submit receipts?',
  'Is internet reimbursed for remote employees?',
]

async function ask(text = question.value) {
  const q = text.trim()
  if (q.length < 3 || busy.value) return
  // The API takes complete user/assistant pairs, most recent last.
  const history: ChatTurn[] = messages.value.slice(-10).map(({ role, content }) => ({ role, content }))
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  busy.value = true
  await scroll()
  try {
    const reply = await askAssistant(q, history)
    messages.value.push({ role: 'assistant', content: reply.answer, sources: reply.sources })
  } catch (error) {
    messages.value.pop()
    question.value = q
    toast.add({ severity: 'error', summary: 'The assistant could not answer', detail: errorMessage(error), life: 6000 })
  } finally {
    busy.value = false
    await scroll()
  }
}

async function scroll() {
  await nextTick()
  thread.value?.scrollTo({ top: thread.value.scrollHeight, behavior: 'smooth' })
}

async function cite(source: Source) {
  try { await openSource(source.document_id, source.page) } catch (error) {
    toast.add({ severity: 'error', summary: 'Could not open source', detail: errorMessage(error), life: 5000 })
  }
}

function onKey(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); ask() }
}

defineExpose({ reset: () => { messages.value = [] }, hasMessages: () => messages.value.length > 0 })
</script>

<template>
  <section class="card chat">
    <div ref="thread" class="thread" aria-live="polite">
      <div v-if="!messages.length" class="empty">
        <i class="pi pi-comments big" />
        <p>Ask about expenses, remote work, leave, IT or compliance policies.</p>
        <div class="suggestions">
          <Button v-for="s in suggestions" :key="s" :label="s" severity="secondary" outlined size="small" @click="ask(s)" />
        </div>
      </div>
      <div v-for="(m, i) in messages" :key="i" :class="['bubble', m.role]">
        <p class="text">{{ m.content }}</p>
        <div v-if="m.role === 'assistant' && m.sources" class="sources">
          <span v-if="!m.sources.length" class="muted">No supporting policy found.</span>
          <button v-for="(s, j) in m.sources" :key="j" class="source" v-tooltip.top="s.excerpt" @click="cite(s)">
            <i class="pi pi-file-pdf" />
            {{ s.title }}<template v-if="s.version"> v{{ s.version }}</template> · p. {{ s.page }}
            <span v-if="s.heading" class="muted"> · {{ s.heading }}</span>
          </button>
        </div>
      </div>
      <div v-if="busy" class="bubble assistant"><i class="pi pi-spin pi-spinner" /> Searching policies…</div>
    </div>
    <div class="composer">
      <Textarea v-model="question" rows="2" auto-resize maxlength="1500" fluid :disabled="busy"
                placeholder="Ask a policy question… (Enter to send, Shift+Enter for a new line)" @keydown="onKey" />
      <Button icon="pi pi-send" aria-label="Send" :disabled="busy || question.trim().length < 3" @click="ask()" />
    </div>
    <small class="muted">AI answers can be wrong. Check the cited page before acting on amounts, limits or deadlines.</small>
  </section>
</template>

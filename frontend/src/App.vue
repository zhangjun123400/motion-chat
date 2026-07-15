<template>
  <div class="flex h-screen">
    <aside class="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
      <div class="p-4 border-b border-gray-800">
        <h1 class="text-lg font-bold">🤖 动作设计工具</h1>
        <div class="text-[10px] text-gray-600 mt-0.5">v2 — 进度可见</div>
      </div>
      <div class="flex-1 overflow-y-auto">
        <div
          v-for="s in sessions"
          :key="s.session_id"
          @click="select(s.session_id)"
          class="p-3 mx-1 rounded cursor-pointer transition-colors mb-1"
          :class="currentId === s.session_id
            ? 'bg-blue-600/20 text-blue-300 border border-blue-800/50'
            : 'hover:bg-gray-800 text-gray-400 border border-transparent'"
        >
          <div class="text-sm font-medium truncate">{{ s.title }}</div>
          <div class="text-xs text-gray-500 mt-1">{{ s.artifact_count ?? 0 }} 个动作</div>
        </div>
        <p v-if="sessions.length === 0" class="text-gray-500 text-sm p-2">暂无会话</p>
      </div>
      <div class="p-3 border-t border-gray-800">
        <button @click="newSession" class="w-full py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium">
          + 新会话
        </button>
      </div>
    </aside>

    <main class="flex-1 flex flex-col min-w-0">
      <div class="flex-1 overflow-y-auto">
        <div v-if="!currentId" class="text-center text-gray-500 mt-32">
          <p class="text-5xl mb-4">🐕</p>
          <p class="text-lg">选择已有会话或创建新会话</p>
          <p class="text-sm mt-2 text-gray-600">通过自然语言描述来生成机器狗动作</p>
        </div>

        <template v-else>
          <div class="space-y-4 p-4">
            <div v-if="messages.length === 0 && !streaming" class="text-center text-gray-500 mt-16">
              <p class="text-4xl mb-4">🐕</p>
              <p>描述你想要的动作：</p>
              <p class="text-sm mt-2 text-gray-600">"生成一只开心小跑的小狗"</p>
            </div>

            <div v-for="(msg, i) in messages" :key="i"
              :class="msg.role === 'user' ? 'flex justify-end' : ''"
            >
              <div
                :class="msg.role === 'user'
                  ? 'bg-blue-600 text-white max-w-[75%] rounded-2xl rounded-br-md px-4 py-3 text-sm'
                  : 'text-gray-300 max-w-[85%] text-sm'"
              >
                {{ msg.content }}
              </div>
            </div>

            <!-- Progress timeline -->
            <div v-if="streaming" class="bg-gray-900/60 border border-gray-800 rounded-lg p-4">
              <div class="text-xs font-medium text-gray-400 mb-3 uppercase tracking-wider">执行进度</div>
              <div class="space-y-2">
                <div v-for="s in stages" :key="s.key" class="flex items-center gap-3">
                  <span v-if="s.state === 'done'" class="text-green-400 text-sm">✅</span>
                  <span v-else-if="s.state === 'active'" class="flex items-center justify-center w-4 h-4">
                    <span class="inline-block w-3 h-3 bg-yellow-500 rounded-full animate-pulse"></span>
                  </span>
                  <span v-else class="text-gray-600 text-sm">○</span>
                  <span :class="s.state === 'active' ? 'text-yellow-400 text-sm' : s.state === 'done' ? 'text-green-400 text-sm' : 'text-gray-600 text-sm'">
                    {{ s.label }}
                    <span v-if="s.state === 'active' && s.detail" class="text-gray-500 ml-1">— {{ s.detail }}</span>
                  </span>
                </div>
              </div>
            </div>

            <!-- Thinking output (collapsible) -->
            <div v-if="streaming && thinking" class="text-gray-500 text-xs bg-gray-900/30 rounded p-3 max-h-[200px] overflow-y-auto font-mono leading-relaxed whitespace-pre-wrap">
              {{ thinking.slice(-2000) }}
            </div>
          </div>

          <div v-if="result" class="px-4 pb-4 space-y-1">
            <!-- Code Viewer -->
            <div class="mt-3 border border-gray-700 rounded-lg overflow-hidden">
              <div class="flex items-center justify-between px-3 py-2 bg-gray-800 border-b border-gray-700">
                <span class="text-xs text-gray-400 font-mono">generate.py</span>
                <button @click="copyCode" class="text-xs text-blue-400 hover:text-blue-300">{{ copied ? '已复制' : '复制代码' }}</button>
              </div>
              <div class="max-h-[300px] overflow-y-auto bg-gray-950">
                <pre class="p-3 text-xs leading-relaxed text-gray-300 font-mono whitespace-pre-wrap">{{ code || result.script }}</pre>
              </div>
            </div>

            <!-- GIF Preview -->
            <div v-if="result.gif_url" class="mt-3 border border-gray-700 rounded-lg overflow-hidden">
              <div class="px-3 py-2 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
                <span class="text-xs text-gray-400">🎬 动作预览</span>
                <a :href="result.gif_url" download class="text-xs text-blue-400 hover:text-blue-300">下载 GIF</a>
              </div>
              <div class="bg-black flex justify-center p-2">
                <img :src="result.gif_url" class="max-w-full" style="max-height: 360px" alt="动作预览" />
              </div>
            </div>

            <!-- Quality Card -->
            <div v-if="result.quality" class="mt-3 border rounded-lg overflow-hidden"
              :class="result.quality.overall === 'PASS' ? 'border-green-800/50' : 'border-red-800/50'"
            >
              <div class="px-3 py-2 border-b flex items-center justify-between"
                :class="result.quality.overall === 'PASS' ? 'bg-green-900/20 border-green-800/50' : 'bg-red-900/20 border-red-800/50'"
              >
                <span class="text-sm font-medium" :class="result.quality.overall === 'PASS' ? 'text-green-400' : 'text-red-400'">
                  📊 质检 {{ result.quality.overall === 'PASS' ? '✅ 通过' : '❌ 未通过' }}
                </span>
                <span class="text-xs text-gray-500">重试: {{ result.stats?.retry_count ?? 0 }}次</span>
              </div>
              <div class="p-3 space-y-1 text-sm bg-gray-900/50">
                <div class="flex items-center gap-2">
                  <span :class="(result.quality.check?.violations ?? 1) === 0 ? 'text-green-400' : 'text-red-400'">{{ (result.quality.check?.violations ?? 1) === 0 ? '✅' : '❌' }}</span>
                  <span class="text-gray-400">关节限位</span>
                  <span class="text-gray-600 text-xs">{{ result.quality.check?.violations ?? '?' }} violations</span>
                </div>
                <div class="flex items-center gap-2">
                  <span :class="!result.quality.diagnose?.penetration ? 'text-green-400' : 'text-red-400'">{{ !result.quality.diagnose?.penetration ? '✅' : '❌' }}</span>
                  <span class="text-gray-400">足地接触</span>
                  <span class="text-gray-600 text-xs">穿透 {{ result.quality.diagnose?.max_penetration_cm ?? 0 }}cm</span>
                </div>
                <div class="flex items-center gap-2">
                  <span :class="result.quality.smoothness?.passed ? 'text-green-400' : 'text-red-400'">{{ result.quality.smoothness?.passed ? '✅' : '❌' }}</span>
                  <span class="text-gray-400">平滑度</span>
                  <span class="text-gray-600 text-xs">max Δ={{ result.quality.smoothness?.max_joint_delta ?? '?' }}/帧</span>
                </div>
                <div v-if="result.quality.errors?.length" class="mt-2 pt-2 border-t border-gray-800">
                  <div v-for="e in result.quality.errors" :key="e" class="text-xs text-red-400/80">{{ e }}</div>
                </div>
              </div>
            </div>

            <!-- Downloads -->
            <div v-if="result.csv_url" class="flex gap-2 mt-2">
              <a :href="result.csv_url" download class="text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded text-blue-400">📥 下载 CSV</a>
              <a :href="result.gif_url" download class="text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded text-blue-400">📥 下载 GIF</a>
            </div>
          </div>
        </template>
      </div>

      <div v-if="currentId" class="p-4 border-t border-gray-800">
        <form @submit.prevent="handleSend" class="flex gap-2">
          <input
            v-model="inputText"
            :disabled="streaming"
            type="text"
            placeholder="描述你想生成的动作..."
            class="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
          />
          <button type="submit" :disabled="streaming || !inputText.trim()"
            class="px-5 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium transition-colors">
            {{ streaming ? '⏳' : '发送' }}
          </button>
        </form>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'

const sessions = ref([])
const currentId = ref(null)
const currentConv = ref(null)
const messages = ref([])
const streaming = ref(false)
const thinking = ref('')
const status = ref('')
const code = ref('')
const result = ref(null)
const inputText = ref('')
const copied = ref(false)

const STAGE_DEFS = [
  { key: 'llm', label: 'LLM 分析动作需求' },
  { key: 'exec', label: '执行生成脚本' },
  { key: 'quality', label: '质检流水线' },
  { key: 'render', label: '渲染 GIF' },
]

const stages = reactive(STAGE_DEFS.map(s => ({ ...s, state: 'pending', detail: '' })))

function resetStages() {
  stages.forEach((s, i) => { s.state = i === 0 ? 'active' : 'pending'; s.detail = '' })
}

function advanceStage(statusText) {
  // Map status text to stage
  if (statusText.includes('分析') || statusText.includes('动作需求')) {
    stages.forEach(s => s.state = 'pending')
    stages[0].state = 'active'
    stages[0].detail = statusText
  } else if (statusText.includes('提取代码')) {
    stages[0].state = 'done'
    stages[1].state = 'pending'
  } else if (statusText.includes('执行') || statusText.includes('尝试')) {
    stages[1].state = 'active'
    stages[1].detail = statusText
  } else if (statusText.includes('质检') || statusText.includes('修复')) {
    stages[1].state = 'done'
    stages[2].state = 'active'
    stages[2].detail = statusText
  } else if (statusText.includes('渲染') || statusText.includes('GIF')) {
    stages[2].state = 'done'
    stages[3].state = 'active'
    stages[3].detail = statusText
  }
}

async function fetchSessions() {
  const res = await fetch('/api/sessions')
  sessions.value = await res.json()
}

async function newSession() {
  const res = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: '新会话' }),
  })
  const { session_id } = await res.json()
  await fetchSessions()
  await select(session_id)
}

async function select(id) {
  currentId.value = id
  const res = await fetch(`/api/sessions/${id}`)
  currentConv.value = await res.json()
  messages.value = currentConv.value?.messages ?? []
  thinking.value = ''
  status.value = ''

  // Reconstruct result from stored artifacts (for when user revisits a session)
  const artifacts = currentConv.value?.artifacts
  if (artifacts && artifacts.length > 0) {
    const last = artifacts[artifacts.length - 1]
    result.value = {
      artifact_id: last.artifact_id,
      csv_url: `/api/files/${id}/${last.artifact_id}/motion.csv`,
      gif_url: `/api/files/${id}/${last.artifact_id}/motion.gif`,
      quality: last.quality_report || null,
      stats: last.stats || {},
    }
    // Fetch script content
    try {
      const scr = await fetch(`/api/files/${id}/${last.artifact_id}/generate.py`)
      if (scr.ok) {
        code.value = await scr.text()
      }
    } catch {}
  } else {
    result.value = null
    code.value = ''
  }
}

async function handleSend() {
  const msg = inputText.value.trim()
  if (!msg || streaming.value || !currentId.value) return
  inputText.value = ''

  messages.value = [...messages.value, { role: 'user', content: msg }]
  streaming.value = true
  thinking.value = ''
  code.value = ''
  result.value = null
  status.value = ''
  resetStages()

  const res = await fetch(`/api/chat/${currentId.value}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: msg }),
  })

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventType = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const data = line.slice(6).replace(/\\n/g, '\n').replace(/\\"/g, '"')
        if (eventType === 'status') { status.value = data; advanceStage(data) }
        else if (eventType === 'thinking') thinking.value += data
        else if (eventType === 'code') code.value = data
        else if (eventType === 'done') {
          try { result.value = JSON.parse(data) } catch { result.value = data }
        }
      }
    }
  }

  streaming.value = false
  status.value = ''

  // Refresh to get assistant message
  if (result.value) {
    const r = await fetch(`/api/sessions/${currentId.value}`)
    currentConv.value = await r.json()
    messages.value = currentConv.value?.messages ?? []
  }
}

async function copyCode() {
  const c = code.value || result.value?.script || ''
  await navigator.clipboard.writeText(c)
  copied.value = true
  setTimeout(() => copied.value = false, 2000)
}

onMounted(() => fetchSessions())
</script>

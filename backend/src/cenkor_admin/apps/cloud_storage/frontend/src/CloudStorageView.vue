<template>
  <div class="p-6 max-w-5xl mx-auto">
    <h1 class="text-2xl font-semibold mb-6">☁️ 云存储</h1>

    <div class="card mb-6">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">当前激活</h2>
        <button class="btn-ghost text-sm" @click="loadConfig()">刷新</button>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-sm text-ink-500">Provider:</span>
        <select v-model="active" class="input flex-1" @change="activate">
          <option v-for="p in providers" :key="p" :value="p">
            {{ providerLabel(p) }} {{ config.providers[p]?.has_secret ? '✓' : '(未配置)' }}
          </option>
        </select>
        <p class="text-xs text-ink-400">切换激活 provider 前需先在该 provider 标签页配置并保存凭据。</p>
      </div>
    </div>

    <div class="card mb-6">
      <h2 class="font-semibold mb-3">通用设置</h2>
      <label class="flex items-center gap-3 cursor-pointer">
        <input type="checkbox" v-model="keepLocalBackup" class="w-4 h-4" />
        <div>
          <div class="text-sm font-medium">保留本地备份 (MinIO)</div>
          <div class="text-xs text-ink-400">开启后，上传到云存储的文件会同时在本地 MinIO 留一份副本作备份。</div>
        </div>
      </label>
      <div class="mt-3">
        <button class="btn-primary" @click="saveSettings">保存设置</button>
      </div>
    </div>

    <div class="card mb-6">
      <div class="flex gap-1 mb-4 border-b border-ink-200">
        <button
          v-for="p in providers" :key="p"
          class="px-3 py-1.5 text-sm border-b-2"
          :class="tab === p ? 'border-ink-900 text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-700'"
          @click="tab = p"
        >{{ providerLabel(p) }} <span v-if="config.providers[p]?.has_secret" class="text-green-600">●</span></button>
      </div>

      <div v-if="!config.providers[tab]?.has_secret" class="space-y-3">
        <p class="text-sm text-ink-500">此 provider 尚未配置凭据。填写并保存后，再到上方「当前激活」切换。</p>
        <div class="grid grid-cols-2 gap-3">
          <input v-model="form.access_key" class="input" placeholder="AccessKey / Operator" />
          <input v-model="form.secret_key" class="input" type="password" placeholder="SecretKey / Password" />
          <input v-model="form.bucket" class="input" placeholder="Bucket 名称" />
          <input v-model="form.region" class="input" :placeholder="regionHint(tab)" />
          <input v-model="form.endpoint" class="input col-span-2" :placeholder="endpointHint(tab)" />
          <input v-model="form.cdn_domain" class="input col-span-2" placeholder="CDN 域名（可选）" />
          <input v-model="form.prefix" class="input col-span-2" placeholder="路径前缀（可选）" />
        </div>
        <div class="flex gap-2">
          <button class="btn-primary" @click="saveCreds">保存凭据</button>
          <button class="btn-ghost" @click="testConnection">测试连接</button>
        </div>
        <div v-if="testResult" class="text-sm" :class="testResult.ok ? 'text-green-600' : 'text-red-600'">
          {{ testResult.ok ? '✓ 连接成功' : '✗ ' + testResult.error }}
        </div>
      </div>

      <div v-else class="space-y-2">
        <div class="text-sm text-ink-500">已配置：</div>
        <div class="grid grid-cols-2 gap-2 text-sm bg-ink-50 p-3 rounded-lg">
          <div><span class="text-ink-400">AccessKey:</span> {{ config.providers[tab].access_key_masked }}</div>
          <div><span class="text-ink-400">SecretKey:</span> {{ config.providers[tab].secret_key_masked }}</div>
          <div><span class="text-ink-400">Bucket:</span> {{ config.providers[tab].bucket }}</div>
          <div><span class="text-ink-400">Region:</span> {{ config.providers[tab].region || '-' }}</div>
          <div class="col-span-2 break-all"><span class="text-ink-400">Endpoint:</span> {{ config.providers[tab].endpoint }}</div>
          <div class="col-span-2 break-all" v-if="config.providers[tab].cdn_domain"><span class="text-ink-400">CDN:</span> {{ config.providers[tab].cdn_domain }}</div>
        </div>
        <div class="flex gap-2">
          <button class="btn-primary" @click="editMode = true">编辑凭据</button>
          <button class="btn-ghost text-red-600" @click="deleteCreds">删除凭据</button>
          <button class="btn-ghost" @click="testConnection">测试连接</button>
        </div>
        <div v-if="editMode" class="border-t pt-3 mt-3 space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <input v-model="form.access_key" class="input" placeholder="AccessKey" />
            <input v-model="form.secret_key" class="input" type="password" placeholder="SecretKey（留空保留）" />
            <input v-model="form.bucket" class="input" placeholder="Bucket" />
            <input v-model="form.region" class="input" placeholder="Region" />
            <input v-model="form.endpoint" class="input col-span-2" placeholder="Endpoint" />
            <input v-model="form.cdn_domain" class="input col-span-2" placeholder="CDN 域名" />
            <input v-model="form.prefix" class="input col-span-2" placeholder="路径前缀" />
          </div>
          <div class="flex gap-2">
            <button class="btn-primary" @click="saveCreds">保存</button>
            <button class="btn-ghost" @click="editMode = false; form = {}">取消</button>
          </div>
        </div>
        <div v-if="testResult" class="text-sm" :class="testResult.ok ? 'text-green-600' : 'text-red-600'">
          {{ testResult.ok ? '✓ 连接成功' : '✗ ' + testResult.error }}
        </div>
      </div>
    </div>

    <div v-if="active" class="card mb-6">
      <h2 class="font-semibold mb-3">健康检查</h2>
      <button class="btn-ghost text-sm" @click="runHealth">检查所有 provider</button>
      <div v-if="health" class="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div v-for="(r, p) in health.results" :key="p" class="flex items-center gap-2 p-2 rounded"
          :class="r.ok ? 'bg-green-50' : 'bg-red-50'">
          <span :class="r.ok ? 'text-green-700' : 'text-red-700'">{{ r.ok ? '✓' : '✗' }}</span>
          <span class="font-medium">{{ providerLabel(p) }}</span>
          <span v-if="!r.ok" class="text-red-600 text-xs">— {{ r.error }}</span>
        </div>
      </div>
    </div>

    <div v-if="active" class="card">
      <h2 class="font-semibold mb-3">文件浏览</h2>
      <div class="flex gap-2 mb-3">
        <input v-model="browseBucket" class="input" placeholder="Bucket" />
        <input v-model="browsePrefix" class="input flex-1" placeholder="prefix（可选）" />
        <button class="btn-primary" @click="listFiles">列出</button>
      </div>
      <div v-if="files && files.length === 0" class="text-ink-400 text-sm py-4 text-center">无文件</div>
      <table v-else-if="files && files.length > 0" class="w-full text-sm">
        <thead class="bg-ink-50 text-ink-500 text-left">
          <tr>
            <th class="px-3 py-2">Key</th>
            <th class="px-3 py-2 text-right">大小</th>
            <th class="px-3 py-2">修改时间</th>
            <th class="px-3 py-2 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in files" :key="f.key" class="border-t">
            <td class="px-3 py-2 break-all">{{ f.key }}</td>
            <td class="px-3 py-2 text-right text-ink-500">{{ formatSize(f.size) }}</td>
            <td class="px-3 py-2 text-ink-500 text-xs">{{ f.last_modified || '-' }}</td>
            <td class="px-3 py-2 text-right">
              <button class="text-xs text-blue-600 mr-2" @click="getUrl(f.key)">复制外链</button>
              <button class="text-xs text-red-600" @click="del(f.key)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="active" class="card mt-6">
      <h2 class="font-semibold mb-3">迁移：MinIO → 当前 provider</h2>
      <p class="text-sm text-ink-500 mb-3">把现有 MinIO 桶里的对象复制到当前激活的 provider。</p>
      <div class="flex gap-2">
        <input v-model="migBucket" class="input" placeholder="源 Bucket" />
        <input v-model="migPrefix" class="input flex-1" placeholder="prefix（可选）" />
        <button class="btn-primary" @click="startMigration">开始迁移</button>
      </div>
      <div v-if="migJob" class="mt-3 text-sm">
        <div class="flex items-center gap-2">
          <span>状态：</span>
          <span class="font-medium">{{ migJob.status }}</span>
          <span v-if="migJob.total" class="text-ink-500">— {{ migJob.done }}/{{ migJob.total }} (失败 {{ migJob.failed }})</span>
        </div>
        <div v-if="migJob.status === 'running' || migJob.status === 'pending'" class="text-blue-600">迁移进行中…</div>
        <div v-if="migJob.status === 'done'" class="text-green-600">✓ 迁移完成</div>
        <div v-if="migJob.status === 'failed' || migJob.status === 'partial'" class="text-red-600">✗ {{ migJob.error || '部分失败' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const providers = ['tencent', 'aliyun', 'qiniu', 'upyun']
const providerLabels = { tencent: '腾讯云 COS', aliyun: '阿里云 OSS', qiniu: '七牛云 Kodo', upyun: '又拍云' }
function providerLabel(p) { return providerLabels[p] || p }

const config = ref({ active_provider: 'tencent', keep_local_backup: true, providers: {} })
const active = ref('tencent')
const tab = ref('tencent')
const editMode = ref(false)
const form = ref({})
const testResult = ref(null)
const health = ref(null)
const browseBucket = ref('')
const browsePrefix = ref('')
const files = ref(null)
const migBucket = ref('')
const migPrefix = ref('')
const migJob = ref(null)
const keepLocalBackup = ref(true)

function regionHint(p) {
  return { tencent: 'ap-shanghai / ap-guangzhou / ap-beijing', aliyun: 'oss-cn-hangzhou', qiniu: 'z0 / z1 / z2 / cn-east-2', upyun: '（又拍无需 region）' }[p] || 'Region'
}
function endpointHint(p) {
  return { tencent: 'https://cos.<region>.myqcloud.com', aliyun: 'https://oss-<region>.aliyuncs.com', qiniu: 'https://s3-<region>.qiniucs.com', upyun: 'https://v0.api.upyun.com' }[p] || 'Endpoint'
}
function formatSize(b) {
  if (!b) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++ }
  return b.toFixed(2) + ' ' + u[i]
}

// 统一走框架注入的 window.__PLUGIN_API__（从 auth store 实时取 token，
// 且底层复用主程序 axios，带 401 自动刷新），避免手搓 token 读错 localStorage key。
async function api(method, path, body) {
  return await window.__PLUGIN_API__(method, path, body)
}

async function loadConfig() {
  config.value = await api('GET', '/api/v1/cloud_storage/config')
  active.value = config.value.active_provider
  tab.value = config.value.active_provider
  keepLocalBackup.value = !!config.value.keep_local_backup
  if (config.value.providers[active.value]?.bucket && !browseBucket.value) {
    browseBucket.value = config.value.providers[active.value].bucket
  }
  if (config.value.providers[active.value]?.bucket && !migBucket.value) {
    migBucket.value = config.value.providers[active.value].bucket
  }
}
async function saveSettings() {
  await api('PUT', '/api/v1/cloud_storage/config', { keep_local_backup: keepLocalBackup.value })
  alert('设置已保存')
  await loadConfig()
}

async function saveCreds() {
  if (!form.value.access_key || !form.value.secret_key || !form.value.bucket) {
    alert('AccessKey / SecretKey / Bucket 必填')
    return
  }
  if (!form.value.endpoint && tab.value !== 'upyun') {
    alert('请填写 Endpoint')
    return
  }
  await api('PUT', `/api/v1/cloud_storage/config/${tab.value}/creds`, form.value)
  alert('已保存')
  editMode.value = false
  await loadConfig()
}
async function activate() {
  try {
    await api('POST', '/api/v1/cloud_storage/config/activate', { provider: active.value })
    await loadConfig()
  } catch (e) {
    alert(e.message || '激活失败')
  }
}
async function deleteCreds() {
  if (!confirm('确定删除该 provider 的凭据？')) return
  await api('DELETE', `/api/v1/cloud_storage/config/${tab.value}/creds`)
  await loadConfig()
}
async function testConnection() {
  testResult.value = null
  const data = await api('GET', '/api/v1/cloud_storage/health')
  testResult.value = data.results[tab.value]
}
async function runHealth() {
  health.value = null
  health.value = await api('GET', '/api/v1/cloud_storage/health')
}
async function listFiles() {
  files.value = []
  const q = new URLSearchParams({ bucket: browseBucket.value, prefix: browsePrefix.value })
  const data = await api('GET', `/api/v1/cloud_storage/files?${q}`)
  files.value = data.items
}
async function getUrl(key) {
  const data = await api('POST', '/api/v1/cloud_storage/presign', { bucket: browseBucket.value, key, method: 'get', expires: 3600 })
  navigator.clipboard.writeText(data.url)
  alert('外链已复制：\n' + data.url)
}
async function del(key) {
  if (!confirm(`确定删除 ${key}？`)) return
  await api('DELETE', `/api/v1/cloud_storage/files?bucket=${encodeURIComponent(browseBucket.value)}&key=${encodeURIComponent(key)}`)
  await listFiles()
}
async function startMigration() {
  if (!confirm('迁移会比较耗时，是否继续？')) return
  const q = new URLSearchParams({ bucket: migBucket.value, prefix: migPrefix.value })
  const data = await api('POST', `/api/v1/cloud_storage/migrate?${q}`)
  migJob.value = { id: data.job_id, status: 'pending', total: 0, done: 0, failed: 0 }
  pollMigration()
}
async function pollMigration() {
  if (!migJob.value) return
  const data = await api('GET', `/api/v1/cloud_storage/migrate/${migJob.value.id}`)
  migJob.value = data
  if (data.status === 'running' || data.status === 'pending') {
    setTimeout(pollMigration, 2000)
  }
}

onMounted(loadConfig)
</script>

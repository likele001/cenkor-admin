<template>
  <PageShell>
    <template #actions>
      <el-button :icon="ArrowLeft" @click="back()">返回</el-button>
    </template>

    <el-descriptions v-loading="loading" :column="3" border style="margin-bottom: 16px">
      <el-descriptions-item label="编号">{{ customer.code }}</el-descriptions-item>
      <el-descriptions-item label="客户名称">{{ customer.name }}</el-descriptions-item>
      <el-descriptions-item label="简称">{{ customer.short_name || '—' }}</el-descriptions-item>
      <el-descriptions-item label="类型">{{ customer.customer_type === 'company' ? '企业' : '个人' }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="statusTagType(customer.status)" size="small">{{ statusLabel(customer.status) }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="信用额度">{{ fmtMoney(customer.credit_limit) }} {{ customer.currency }}</el-descriptions-item>
      <el-descriptions-item label="税号">{{ customer.tax_id || '—' }}</el-descriptions-item>
      <el-descriptions-item label="行业">{{ customer.industry || '—' }}</el-descriptions-item>
      <el-descriptions-item label="结算方式">{{ customer.payment_terms || '—' }}</el-descriptions-item>
    </el-descriptions>

    <el-tabs v-model="activeTab" class="erp-tabs">
      <!-- 联系人 -->
      <el-tab-pane label="联系人" name="contacts">
        <div class="pane-actions">
          <el-button type="primary" size="small" :icon="Plus" @click="openContact()">新增联系人</el-button>
        </div>
        <el-table :data="contacts" border stripe>
          <el-table-column prop="name" label="姓名" min-width="120" />
          <el-table-column prop="position" label="职位" min-width="120" />
          <el-table-column prop="phone" label="电话" min-width="130" />
          <el-table-column prop="email" label="邮箱" min-width="180" />
          <el-table-column prop="wechat" label="微信" min-width="130" />
          <el-table-column label="主要" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_primary" type="success" size="small">是</el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" align="center">
            <template #default="{ row }">
              <el-button link type="primary" @click="openContact(row)">编辑</el-button>
              <el-button link type="danger" @click="removeContact(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 地址 -->
      <el-tab-pane label="地址" name="addresses">
        <div class="pane-actions">
          <el-button type="primary" size="small" :icon="Plus" @click="openAddress()">新增地址</el-button>
        </div>
        <el-table :data="addresses" border stripe>
          <el-table-column prop="address_type" label="类型" width="100" formatter="v" />
          <el-table-column label="收件人" min-width="110">
            <template #default="{ row }">{{ row.recipient || '—' }}</template>
          </el-table-column>
          <el-table-column label="电话" min-width="130">
            <template #default="{ row }">{{ row.phone || '—' }}</template>
          </el-table-column>
          <el-table-column label="地址" min-width="260">
            <template #default="{ row }">{{ [row.province, row.city, row.district, row.detail].filter(Boolean).join(' ') || '—' }}</template>
          </el-table-column>
          <el-table-column label="默认" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" align="center">
            <template #default="{ row }">
              <el-button link type="primary" @click="openAddress(row)">编辑</el-button>
              <el-button link type="danger" @click="removeAddress(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 跟进记录 -->
      <el-tab-pane label="跟进记录" name="followups">
        <div class="pane-actions">
          <el-button type="primary" size="small" :icon="Plus" @click="openFollowUp()">新增跟进</el-button>
        </div>
        <el-table :data="followUps" border stripe empty-text="暂无跟进记录" :default-sort="{prop:'follow_date',order:'descending'}">
          <el-table-column prop="follow_date" label="跟进日期" width="120" formatter="v" />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">{{ followTypeLabel(row.follow_type) }}</template>
          </el-table-column>
          <el-table-column prop="summary" label="跟进内容" min-width="260" show-overflow-tooltip />
          <el-table-column label="下次行动/日期" min-width="200">
            <template #default="{ row }">{{ row.next_action || '' }}<el-tag v-if="row.next_follow_date" size="small" style="margin-left:6px">{{ row.next_follow_date }}</el-tag></template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 编辑核心资料 -->
    <FormDrawer v-model="editVisible" title="编辑客户资料" width="600px" :saving="saving" @save="saveProfile">
      <el-form ref="profileFormRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="客户编号"><el-input v-model="form.code" /></el-form-item>
        <el-form-item label="客户名称" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="简称"><el-input v-model="form.short_name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="类型"><el-select v-model="form.customer_type" style="width:100%"><el-option label="企业" value="company" /><el-option label="个人" value="person" /></el-select></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="税号"><el-input v-model="form.tax_id" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="币种"><el-select v-model="form.currency" style="width:100%"><el-option label="CNY" value="CNY" /><el-option label="USD" value="USD" /></el-select></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="信用额度"><el-input-number v-model="form.credit_limit" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="行业"><el-input v-model="form.industry" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="结算方式"><el-input v-model="form.payment_terms" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 联系人 -->
    <FormDrawer v-model="contactVisible" :title="contactIndex === null ? '新增联系人' : '编辑联系人'" width="520px" :saving="saving" @save="saveContact">
      <el-form :model="contactForm" label-width="80px">
        <el-form-item label="姓名" required>
          <el-input v-model="contactForm.name" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="职位"><el-input v-model="contactForm.position" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="电话"><el-input v-model="contactForm.phone" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="邮箱"><el-input v-model="contactForm.email" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="微信"><el-input v-model="contactForm.wechat" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="主要联系人">
          <el-switch v-model="contactForm.is_primary" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="contactForm.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 地址 -->
    <FormDrawer v-model="addressVisible" :title="addressIndex === null ? '新增地址' : '编辑地址'" width="520px" :saving="saving" @save="saveAddress">
      <el-form :model="addressForm" label-width="80px">
        <el-form-item label="类型">
          <el-select v-model="addressForm.address_type" style="width:100%">
            <el-option label="发货地址" value="shipping" />
            <el-option label="收货地址" value="delivery" />
            <el-option label="办公地址" value="office" />
          </el-select>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="收件人"><el-input v-model="addressForm.recipient" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="电话"><el-input v-model="addressForm.phone" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="省份"><el-input v-model="addressForm.province" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="城市"><el-input v-model="addressForm.city" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="区县"><el-input v-model="addressForm.district" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="详细地址"><el-input v-model="addressForm.detail" /></el-form-item>
        <el-form-item label="默认地址"><el-switch v-model="addressForm.is_default" /></el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 跟进 -->
    <FormDrawer v-model="followVisible" title="新增跟进" width="520px" :saving="saving" @save="saveFollowUp">
      <el-form :model="followForm" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="跟进类型"><el-select v-model="followForm.follow_type" style="width:100%"><el-option v-for="(l,v) in followTypes" :key="v" :label="l" :value="v" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="跟进日期"><el-date-picker v-model="followForm.follow_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="跟进内容" required><el-input v-model="followForm.summary" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="下次行动"><el-input v-model="followForm.next_action" /></el-form-item>
        <el-form-item label="下次日期"><el-date-picker v-model="followForm.next_follow_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  ElMessage, ElMessageBox, ElButton, ElTable, ElTableColumn, ElDescriptions, ElDescriptionsItem,
  ElTag, ElTabs, ElTabPane, ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElInputNumber,
  ElRow, ElCol, ElSwitch, ElDatePicker
} from 'element-plus'
import { Plus, ArrowLeft } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import FormDrawer from '../components/FormDrawer.vue'
import { api, fmtMoney, statusLabel, statusTagType } from '../api'
import { back, currentId } from '../nav'

const customerId = Number(currentId())

const loading = ref(false)
const customer = ref({})
const contacts = ref([])
const addresses = ref([])
const followUps = ref([])
const activeTab = ref('contacts')

const followTypes = { phone: '电话', visit: '拜访', email: '邮件', meeting: '会议', other: '其他' }
const followTypeLabel = (v) => followTypes[v] || v || '—'

async function load() {
  loading.value = true
  try {
    const data = await api.get(`/customers/${customerId}`)
    customer.value = data
    contacts.value = data.contacts || []
    addresses.value = data.addresses || []
  } catch (e) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadFollowUps() {
  try {
    followUps.value = await api.get(`/customers/${customerId}/follow-ups`)
  } catch (e) { ElMessage.error(e.message) }
}

// ===== 编辑核心资料 =====
const editVisible = ref(false)
const saving = ref(false)
const profileFormRef = ref()
const form = reactive({})
const rules = { name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }] }

function openEdit() {
  Object.assign(form, {
    code: customer.value.code, name: customer.value.name, short_name: customer.value.short_name || '',
    customer_type: customer.value.customer_type || 'company', tax_id: customer.value.tax_id || '',
    currency: customer.value.currency || 'CNY', credit_limit: Number(customer.value.credit_limit) || 0,
    industry: customer.value.industry || '', payment_terms: customer.value.payment_terms || '',
    notes: customer.value.notes || ''
  })
  editVisible.value = true
}

async function saveProfile() {
  await profileFormRef.value.validate()
  saving.value = true
  try {
    await api.put(`/customers/${customerId}`, {
      ...form, credit_limit: Number(form.credit_limit) || 0,
      contacts: contacts.value, addresses: addresses.value
    })
    ElMessage.success('已保存')
    editVisible.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

// ===== 联系人 =====
const contactVisible = ref(false)
const contactIndex = ref(null)
const contactForm = reactive({})

function openContact(row) {
  contactIndex.value = row ? contacts.value.indexOf(row) : null
  Object.assign(contactForm, row
    ? { ...row }
    : { name: '', position: '', phone: '', email: '', wechat: '', is_primary: false, notes: '' })
  contactVisible.value = true
}

async function saveContact() {
  if (!contactForm.name) { ElMessage.warning('请输入姓名'); return }
  const item = { ...contactForm }
  if (item.is_primary) contacts.value.forEach((c) => { c.is_primary = false })
  if (contactIndex.value === null) contacts.value.push(item)
  else contacts.value[contactIndex.value] = item
  saving.value = true
  try {
    await api.put(`/customers/${customerId}`, buildCustomerPayload())
    ElMessage.success('已保存')
    contactVisible.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function removeContact(row) {
  try { await ElMessageBox.confirm(`删除联系人「${row.name}」？`, '提示', { type: 'warning' }) } catch (e) { return }
  contacts.value = contacts.value.filter((c) => c !== row)
  saving.value = true
  try {
    await api.put(`/customers/${customerId}`, buildCustomerPayload())
    ElMessage.success('已删除')
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

// ===== 地址 =====
const addressVisible = ref(false)
const addressIndex = ref(null)
const addressForm = reactive({})

function openAddress(row) {
  addressIndex.value = row ? addresses.value.indexOf(row) : null
  Object.assign(addressForm, row
    ? { ...row }
    : { address_type: 'shipping', recipient: '', phone: '', province: '', city: '', district: '', detail: '', is_default: false })
  addressVisible.value = true
}

async function saveAddress() {
  const item = { ...addressForm }
  if (item.is_default) addresses.value.forEach((a) => { a.is_default = false })
  if (addressIndex.value === null) addresses.value.push(item)
  else addresses.value[addressIndex.value] = item
  saving.value = true
  try {
    await api.put(`/customers/${customerId}`, buildCustomerPayload())
    ElMessage.success('已保存')
    addressVisible.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function removeAddress(row) {
  try { await ElMessageBox.confirm('删除该地址？', '提示', { type: 'warning' }) } catch (e) { return }
  addresses.value = addresses.value.filter((a) => a !== row)
  saving.value = true
  try {
    await api.put(`/customers/${customerId}`, buildCustomerPayload())
    ElMessage.success('已删除')
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

function buildCustomerPayload() {
  return {
    code: customer.value.code, name: customer.value.name,
    short_name: customer.value.short_name || null,
    customer_type: customer.value.customer_type || 'company',
    tax_id: customer.value.tax_id || null, currency: customer.value.currency || 'CNY',
    payment_terms: customer.value.payment_terms || null,
    credit_limit: Number(customer.value.credit_limit) || 0,
    industry: customer.value.industry || null, scale: customer.value.scale || null,
    status: customer.value.status || 'active', owner_user_id: customer.value.owner_user_id || null,
    notes: customer.value.notes || null,
    contacts: contacts.value, addresses: addresses.value
  }
}

// ===== 跟进 =====
const followVisible = ref(false)
const followForm = reactive({})

function openFollowUp() {
  Object.assign(followForm, { contact_id: null, follow_type: 'phone', follow_date: new Date().toISOString().slice(0, 10), summary: '', next_action: '', next_follow_date: null })
  followVisible.value = true
}

async function saveFollowUp() {
  if (!followForm.summary) { ElMessage.warning('请输入跟进内容'); return }
  saving.value = true
  try {
    await api.post(`/customers/${customerId}/follow-ups`, { ...followForm, contact_id: null })
    ElMessage.success('已添加')
    followVisible.value = false
    await loadFollowUps()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

onMounted(async () => {
  await load()
  await loadFollowUps()
})
</script>

<style scoped>
.erp-tabs {
  margin-top: 4px;
}
.pane-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}
</style>
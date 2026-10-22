<script setup lang="ts">
/**
 * Agent 会话列表（P11 前端，design 2.2.2-(5)——左栏独立交互域）。
 *
 * 服务端 updated_at 倒序原样渲染（前端不排序）；当前会话高亮；
 * 空标题「新会话」占位；重命名 el-dialog（1..200 前端拦截）与删除
 * ElMessageBox.confirm **交互内聚于本组件**，操作结果以事件上报
 * （API 调用在 AgentView——子组件零 api 调用，spec §4.4 规则 4）。
 *
 * generating=true 时列表项与新建入口视觉置灰——轻提示由 AgentView
 * 统一弹出（GENERATING_BLOCK_HINT 单一来源，避免双提示，design
 * 2.2.2-(5) 归属裁定）；点击仍会 emit select（由 AgentView 短路拦截）。
 */
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

import type { AgentConversation } from '@/types/agent'

/** 会话标题长度上限（PATCH 校验 1..200）。 */
const TITLE_MAX_LEN = 200

/** 空标题占位文案（O4——服务端首条消息后补 20 字截断标题）。 */
const UNTITLED_TEXT = '新会话'

const props = defineProps<{
  /** 会话列表（服务端 updated_at 倒序原样渲染）。 */
  conversations: AgentConversation[]
  /** 当前会话 id（null = 无选中/空态）。 */
  currentId: number | null
  /** 列表加载中（骨架/spinner 态，不白屏）。 */
  loading: boolean
  /** 流式生成中（列表项与新建视觉置灰）。 */
  generating: boolean
}>()

const emit = defineEmits<{
  (e: 'create'): void
  (e: 'select', conversationId: number): void
  (e: 'rename', conversationId: number, title: string): void
  (e: 'remove', conversationId: number): void
}>()

/** 重命名弹窗状态（预填当前标题）。 */
const renameVisible = ref(false)
const renameId = ref<number | null>(null)
const renameTitle = ref('')

/** 行显示标题（空 → 「新会话」）。 */
function displayTitle(title: string | null): string {
  return title || UNTITLED_TEXT
}

/** 打开重命名弹窗（预填）。 */
function openRename(conversation: AgentConversation): void {
  renameId.value = conversation.id
  renameTitle.value = conversation.title || ''
  renameVisible.value = true
}

/** 重命名确认（空标题禁用由按钮 :disabled 保证；1..200 由 maxlength 硬限）。 */
function confirmRename(): void {
  const title = renameTitle.value.trim()
  if (!title || renameId.value == null) return
  emit('rename', renameId.value, title)
  renameVisible.value = false
}

/** 删除确认（spec §5.2.1 规则 6 原文文案）。 */
function confirmRemove(conversation: AgentConversation): void {
  void ElMessageBox.confirm(
    `删除后不可恢复，将同时删除会话内全部消息。确定删除「${displayTitle(conversation.title)}」吗？`,
    '删除会话',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
    .then(() => emit('remove', conversation.id))
    .catch(() => {
      // 取消：无请求无变更。
    })
}
</script>

<template>
  <div class="conversation-list">
    <div class="list-head">
      <span class="list-title">会话</span>
      <el-button size="small" :icon="Plus" :disabled="props.generating" @click="emit('create')">
        新建会话
      </el-button>
    </div>

    <div v-if="props.loading" class="list-loading" v-loading="true" element-loading-text="加载中" />

    <el-empty
      v-else-if="!props.conversations.length"
      description="暂无会话，点击上方新建开始"
      :image-size="70"
      class="list-empty"
    />

    <div v-else class="list-body">
      <div
        v-for="conversation in props.conversations"
        :key="conversation.id"
        class="conversation-item"
        :class="{ active: conversation.id === props.currentId, disabled: props.generating }"
        @click="emit('select', conversation.id)"
      >
        <span class="item-title">{{ displayTitle(conversation.title) }}</span>
        <span class="item-actions" @click.stop>
          <el-button link size="small" @click="openRename(conversation)">重命名</el-button>
          <el-button link size="small" type="danger" @click="confirmRemove(conversation)">删除</el-button>
        </span>
      </div>
    </div>

    <!-- 重命名弹窗（1..200 前端拦截：maxlength 硬限 + 空标题禁用） -->
    <el-dialog v-model="renameVisible" title="重命名会话" width="420px" append-to-body>
      <el-input
        v-model="renameTitle"
        :maxlength="TITLE_MAX_LEN"
        show-word-limit
        placeholder="输入新标题（1-200 字符）"
      />
      <template #footer>
        <el-button @click="renameVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!renameTitle.trim()" @click="confirmRename">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.conversation-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.list-title {
  font-size: 14px;
  font-weight: 600;
}
.list-loading {
  flex: 1;
}
.list-empty {
  margin-top: 40px;
}
.list-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.conversation-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.conversation-item:hover {
  background: var(--el-fill-color-light);
}
/* 当前会话高亮（选中态背景 + 主色左边条） */
.conversation-item.active {
  background: var(--el-color-primary-light-9);
  box-shadow: inset 3px 0 0 var(--el-color-primary);
}
/* 生成中视觉置灰（轻提示由 AgentView 统一弹出——单一来源） */
.conversation-item.disabled {
  opacity: 0.55;
}
.item-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-actions {
  flex: 0 0 auto;
  display: none;
}
.conversation-item:hover .item-actions {
  display: inline-flex;
}
</style>
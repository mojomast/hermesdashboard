# Refactor Map: Dashboard Templates/index.html → Modular JS

## Target
- **Monolith**: `templates/index.html` (16,820 lines, ~820KB)
- **Module root**: `templates/js/`
- **Test command**: `cd ~/.hermes/dashboard-refactor-work && python -m pytest tests/ -q --tb=short 2>/dev/null || echo "no tests"`

## Summary
- Total lines: 16,820
- Total top-level JS functions/consts in `<script>` block: ~300+
- The file contains: CSS themes, dashboard layout HTML, 6+ panel tabs, command palette,
  settings modals, IRC chat panel, agent chat panel, games panel, session browser,
  diagnostics panel, message board, and ~300 inline JS functions.

## Focus: Agent Chat Concern
For the multimodal image insertion fix, we only need to extract the **agent chat**
concern. Other concerns (IRC chat, games, sessions, diagnostics, message board,
command palette, settings, theme) can remain in the monolith for now.

### Agent Chat Function Registry

| Name | Line Range | Responsibility | Target Module | Shared State Dependencies |
|------|-----------|----------------|---------------|--------------------------|
| `sendMessage` | 13390-13452 | Send user message + images to backend stream | `agent-chat.js` | `userInput`, `sendBtn`, `pendingChatImages`, `conversation`, `activeRun`, `activeChatSessionId` |
| `clearChat` | 13454-13465 | Clear conversation state | `agent-chat.js` | `chat`, `conversation`, `activeRun` |
| `renderPendingChatImages` | 13476-13489 | Render image preview thumbnails | `agent-chat.js` | `chatImagePreviews`, `pendingChatImages` |
| `addChatImage` | 13491-13499 | Read file as base64 data URL | `agent-chat.js` | `pendingChatImages` |
| `addMessage` | 9131-9160 | Render a message bubble into DOM | `agent-chat.js` | `chat` |
| `renderConversation` | 6246-6264 | Replay conversation into DOM | `agent-chat.js` | `chat`, `conversation` |
| `buildChatRequestMessages` | 10519-10538 | Sanitize messages for API payload | `agent-chat.js` | — |
| `streamChatRun` | ~10600-10700 | SSE stream handler for chat runs | `agent-chat.js` | `activeRun`, `chatRunStatus*` |
| `updateContextDisplay` | ~13300-13388 | Render token/context usage | `agent-chat.js` | `contextSummary`, `contextPills`, `contextBreakdown` |
| `updateActiveRunBanner` | 6174-6193 | Show/hide active run banner | `agent-chat.js` | `activeRun`, `chatRunStatus*` |
| `summarizeActiveRunPreview` | 6157-6173 | Summarize active run for banner | `agent-chat.js` | `activeRun` |
| `saveConversation` | 6072-6075 | Persist conversation to server | `agent-chat.js` | `conversation` |
| `loadConversation` | 6076-6092 | Restore conversation from server | `agent-chat.js` | `conversation` |
| `hydrateChatFromSession` | 7500-7577 | Load session into chat | `agent-chat.js` | `conversation`, `activeRun` |
| `attachChatToSession` | 6150-6156 | Attach chat to session ID | `agent-chat.js` | `activeChatSessionId` |
| `escapeHtml` | 13144-13155 | Utility: escape HTML entities | `utils.js` | — |
| `formatMessageContent` | 13310-13340 | Utility: format markdown-like text | `utils.js` | — |

### Shared Mutable State (Agent Chat)
| Variable | Line | Type | Readers | Writers |
|----------|------|------|---------|---------|
| `conversation` | 5980 | Array | renderConversation, addMessage, sendMessage, loadConversation, saveConversation | sendMessage, clearChat, hydrateChatFromSession |
| `pendingChatImages` | 5993 | Array | renderPendingChatImages, sendMessage | addChatImage, sendMessage |
| `activeRun` | 5990 | Object | updateActiveRunBanner, summarizeActiveRunPreview, sendMessage | sendMessage, clearActiveRun, streamChatRun |
| `activeChatSessionId` | 5991 | String | updateActiveChatBanner, attachChatToSession, sendMessage | attachChatToSession, detachChatSession, sendMessage |
| `userInput` | 5956 | DOM | sendMessage, event listeners | — |
| `sendBtn` | 5957 | DOM | sendMessage, event listeners | — |
| `chat` | 5955 | DOM | renderConversation, addMessage | — |

### Module Assignment Plan

#### `templates/js/utils.js` (shared utilities)
- `escapeHtml`
- `formatMessageContent`
- `scrollChatToBottom` (if chat-scoped)

#### `templates/js/agent-chat.js` (agent chat concern)
- All agent-chat functions listed above
- Event listener setup for paste/drop/attach/send
- State: `conversation`, `pendingChatImages`, `activeRun`, `activeChatSessionId`
- Exports: `initAgentChat()`, `sendMessage()`, `clearChat()`, `addMessage()`,
  `renderConversation()`, `hydrateChatFromSession()`, `attachChatToSession()`,
  `updateActiveRunBanner()`, `buildChatRequestMessages()`

## Risk Flags
- `sendMessage` touches 4+ shared variables (high coupling)
- `streamChatRun` is deeply coupled to `activeRun` state and DOM elements
- Several assistant trace rendering functions (buildAssistantTrace*, renderTool*) are
  used by BOTH agent chat rendering and session transcript rendering — they must stay
  in the monolith or be extracted to a shared `trace-render.js` module.
- The agent chat event listeners are wired at parse time in the monolith; extracting
  them requires moving the listener setup into an `initAgentChat()` function called
  after DOM ready.

## Current Bug: Multimodal Image Insertion
The frontend already supports image paste/drop/attach and builds multimodal content
arrays. The backend `_sanitize_chat_messages` preserves arrays. The gateway
`_handle_chat_completions` preserves arrays. However, two crashes remain in the
core agent (`run_agent.py` in `~/.hermes/hermes-agent-push/`):

1. `_looks_like_codex_intermediate_ack` (line ~1627) does `(user_message or "").strip().lower()`
   which crashes when `user_message` is a list.
2. Ephemeral context injection (line ~7340-7343) only handles `isinstance(_base, str)`,
   so memory prefetch and plugin context are silently lost for multimodal messages.

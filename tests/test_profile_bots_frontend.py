from tests.dashboard_sources import dashboard_source, dashboard_template


def test_bots_navigation_panel_and_profile_form_contract():
    html = dashboard_template()

    assert html.count('data-panel="bots"') >= 2
    assert 'onclick="navigateTo(\'bots\')"' in html
    assert 'id="bots-panel"' in html
    assert 'id="bots-roster"' in html
    assert 'id="bot-create-form"' in html
    assert 'name="name"' in html
    assert 'name="display_name"' in html
    assert 'name="description"' in html
    assert 'name="soul"' in html
    assert 'name="color"' in html
    assert 'id="bot-avatar-file"' in html
    assert 'accept="image/png,image/jpeg,image/webp"' in html
    assert 'id="bot-edit-form"' in html
    assert 'id="bot-edit-name"' in html
    assert 'readonly' in html
    assert 'id="bot-edit-hidden"' in html
    assert 'id="bot-edit-status"' in html
    assert html.count('approval-layout-20260819') == 2
    assert html.count('avatar-rail-20260819') == 2


def test_chat_room_rail_preserves_existing_chat_and_debug_contracts():
    html = dashboard_template()
    source = dashboard_source()

    assert 'id="chat-room-list"' in html
    assert 'data-room-id="main"' in html
    assert 'data-room-id="shared"' in html
    assert 'All Bots Room' in html
    assert 'id="chat-room-title"' in html
    assert 'id="chat"' in html
    assert 'id="user-input"' in html
    assert 'id="send-btn"' in html
    assert 'class="chat-input-actions"' in html
    assert 'class="clear-btn"' in html
    assert 'id="debug-panel"' in html
    assert 'class="chat-room-heading-actions"' in html
    assert 'id="chat-room-rail-toggle"' in html
    assert 'aria-expanded="false"' in html
    assert 'aria-controls="chat-room-list"' in html
    assert 'id="chat-room-avatar"' in html
    assert '.message.user {' in source
    assert 'width: fit-content;' in source
    assert '.chat-input-actions {' in source
    assert '.chat-room-heading-actions {' in source


def test_bot_registry_hash_breadcrumb_and_lazy_load_contract():
    source = dashboard_source()

    assert "{ id: 'bots', label: 'Bots' }" in source
    assert "'chat',\n    'bots'," in source
    assert "case 'bots': loadBots(); break;" in source
    assert "'chat','bots','message-board'" in source
    assert "bots:'Bots'" in source
    assert "fetchJsonOrThrow('/api/bots')" in source
    assert "fetchJsonOrThrow('/api/bot-rooms')" in source
    assert "method: 'POST'" in source
    assert "method: 'DELETE'" in source
    assert "method: 'PATCH'" in source


def test_room_switching_profile_stream_and_shared_message_contract():
    source = dashboard_source()

    assert "let activeChatRoomId = 'main';" in source
    assert "async function switchChatRoom(roomId, options = {})" in source
    assert "let activeRuns = {};" in source
    assert "function getActiveRun(roomId = activeChatRoomId)" in source
    assert "{ version: 2, runs: activeRuns }" in source
    assert "else if (stored.runId)" in source
    assert "if (!options.allowActiveRun && sharedRoomRequestInFlight)" in source
    assert "if (getActiveRun() || streamResumeRooms.has(activeChatRoomId) || sharedRoomRequestInFlight || chatResetInFlight) return;" in source
    assert "const previous = botRoomWriteChains.get(roomId) || Promise.resolve();" in source
    assert "await saveCurrentChatRoom();" in source
    assert "`/api/bot-rooms/${encodeURIComponent(roomId)}`" in source
    assert "body: JSON.stringify({ conversation: roomConversation || [], session_id: sessionId || null })" in source
    assert "roomId: activeChatRoomId" in source
    assert "profile: profileForRoom(roomId)" in source
    assert "room_id: roomId" in source
    assert "profile," in source
    assert "fetch('/api/bot-rooms/shared/messages/stream'" in source
    assert "fetchJsonOrThrow('/api/bot-rooms/shared/messages'" in source
    assert "body: JSON.stringify({ message })" in source
    assert "renderSharedConversation()" in source
    assert "shared-working-indicator" in source
    assert "const roomConversation = messagesPayload;" in source
    assert "persistActiveAssistantState(assistantState, roomId, runState)" in source
    assert "finalizeActiveRun(assistantState, roomId, roomConversation, runState)" in source
    assert "button.setAttribute('aria-current', 'page')" in source


def test_collapsed_room_rail_persistence_and_mobile_contract():
    source = dashboard_source()

    assert "hermes_dashboard_chat_room_rail_expanded_v1" in source
    assert "let expanded = false;" in source
    assert "localStorage.getItem(CHAT_ROOM_RAIL_EXPANDED_KEY) === 'true'" in source
    assert "localStorage.setItem(CHAT_ROOM_RAIL_EXPANDED_KEY, 'true')" in source
    assert "localStorage.removeItem(CHAT_ROOM_RAIL_EXPANDED_KEY)" in source
    assert ".chat-room-rail {\n    flex: 0 0 64px;" in source
    assert ".chat-room-rail.expanded { flex-basis: 218px; }" in source
    assert "@media (max-width: 1000px)" in source
    assert ".chat-room-list { flex-direction: row;" in source


def test_safe_reusable_avatar_and_direct_identity_contract():
    source = dashboard_source()

    assert "function avatarHtml(identity = {}, options = {})" in source
    assert "function bindAvatarFallbacks(root = document)" in source
    assert "image.addEventListener('error'" in source
    assert "image.remove();" in source
    assert "javascript:" not in source[source.index("function safeAvatarUrl"):source.index("function avatarHtml")]
    assert "botRegistry.find(bot => bot.is_default || bot.name === 'default')" in source
    assert "name: 'all-bots', display_name: 'All Bots'" in source
    assert "bot: assistantState.bot || runState.profile || 'default'" in source
    assert "assistantState.bot = assistantSeed?.bot || profile || 'default'" in source
    assert "function botTooltip(identity = {})" in source
    assert "Model: ${model}" in source
    assert "${Number(identity.skill_count)} skills" in source
    assert "title=\"${escapeHtml(botTooltip(bot))}\"" in source
    assert "const fallbackBot = roomBot || (activeChatRoomId === 'main' ? defaultBotIdentity() : null);" in source


def test_bot_detail_patch_avatar_upload_and_remove_contract():
    source = dashboard_source()

    assert "async function openBotEditor(name)" in source
    assert "fetchJsonOrThrow(`/api/bots/${encodeURIComponent(name)}`)" in source
    assert "async function saveBotEditor(event)" in source
    assert "method: 'PATCH'" in source
    assert "display_name: form.elements.display_name.value.trim()" in source
    assert "soul: form.elements.soul.value.trim()" in source
    assert "hidden: form.elements.hidden.checked" in source
    assert "2 * 1024 * 1024" in source
    assert "['image/png', 'image/jpeg', 'image/webp']" in source
    assert "body: file" in source
    assert "method: 'PUT'" in source
    assert "URL.createObjectURL(file)" in source
    assert "URL.revokeObjectURL(url)" in source
    assert "localStorage" not in source[source.index("async function uploadBotAvatar"):source.index("async function openBotEditor")]
    assert "async function removeBotAvatar()" in source
    assert "method: 'DELETE'" in source


def test_progressive_shared_room_ndjson_contract():
    source = dashboard_source()

    assert "async function consumeSharedRoomNdjson(response, onEvent)" in source
    assert "const reader = response.body.getReader()" in source
    assert "buffer.split('\\n')" in source
    assert "event?.type === 'message'" in source
    assert "conversation.push(streamedMessage)" in source
    assert "indicator.insertAdjacentHTML('beforebegin', sharedMessageHtml(streamedMessage))" in source
    assert "event?.type === 'complete'" in source
    assert "if (!error.streamUnavailable) throw error;" in source
    assert "sendSharedRoomMessageFallback(message)" in source
    assert "sharedRoomRequestInFlight = false" in source
    assert "@media (prefers-reduced-motion: reduce)" in source
    assert ":focus-visible" in source


def test_room_aware_clear_and_approval_click_contract_remain_intact():
    source = dashboard_source()

    assert "if (roomId === 'main')" in source
    assert "await saveBotRoom(roomId, [], null);" in source
    assert "data-approval-decision=\"once\"" in source
    assert "data-approval-decision=\"deny\"" in source
    assert "button.addEventListener('click'" in source
    assert "dataset.approvalSignature === signature" in source
    assert 'onclick="respondToApproval(' not in source

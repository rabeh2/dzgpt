// Ensure the DOM is fully loaded before running the script
document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const settingsSidebar = document.getElementById('settings-sidebar');
    const toggleSidebarButton = document.getElementById('toggle-sidebar');
    const mobileMenuButton = document.getElementById('mobile-menu');
    const mobileSettingsButton = document.getElementById('mobile-settings');
    const newConversationButton = document.getElementById('new-conversation');
    const conversationsList = document.getElementById('conversations-list');
    const messagesContainer = document.getElementById('messages');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const modelSelect = document.getElementById('model-select');
    const temperatureSlider = document.getElementById('temperature-slider');
    const temperatureValueSpan = document.getElementById('temperature-value');
    const maxTokensInput = document.getElementById('max-tokens-input');
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    const offlineIndicator = document.getElementById('offline-indicator');
    const confirmModal = document.getElementById('confirm-modal');
    const confirmMessage = document.getElementById('confirm-message');
    const confirmOkButton = document.getElementById('confirm-ok');
    const confirmCancelButton = document.getElementById('confirm-cancel');
    const ttsToggle = document.getElementById('tts-toggle');
    const micButton = document.getElementById('mic-button');

    // --- State Variables ---
    let currentConversationId = null;
    let messages = []; // Stores current conversation messages {role: 'user'/'assistant', content: '...'}
    let isTyping = false; // To prevent multiple requests or show typing indicator
    let confirmationCallback = null; // Function to call after modal confirmation
    // *** CHANGED: Welcome Message ***
    const WELCOME_MESSAGE_CONTENT = "السلام عليكم! أنا مساعد dzteck الرقمي بالعربية. كيف يمكنني مساعدتك اليوم؟";

    // --- New: Frontend Offline Message ---
    const FRONTEND_OFFLINE_MESSAGE = "أعتذر، لا يوجد اتصال بالإنترنت حاليًا. لا يمكنني معالجة طلبك الآن.";

    // --- New: Predefined Responses (Canned Responses) ---
    // *** CHANGED: Predefined Responses ***
    const PREDEFINED_RESPONSES = {
        "من صنعك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة dzteck للتطوير والبحث في الذكاء الاصطناعي.",
        "من انت": "أنا مساعد dzteck الرقمي، تم تطويري بواسطة شركة dzteck للتطوير والبحث في الذكاء الاصطناعي.",
        "مين عملك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة dzteck للتطوير والبحث في الذكاء الاصطناعي.",
        "مين انت": "أنا مساعد dzteck الرقمي، تم تطويري بواسطة شركة dzteck للتطوير والبحث في الذكاء الاصطناعي.", // Note: Duplicate key, last one will likely be used
        "من بناك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة dzteck للتطوير والبحث في الذكاء الاصطناعي.",
        // Add other specific phrases if needed
    };
     // Helper function to check for predefined responses (Original Logic Kept)
     function checkPredefinedResponse(userMessage) {
         // Basic cleaning: lowercase, remove common punctuation, trim
         const cleanedMessage = userMessage.toLowerCase().replace(/[?؟!,.\s\u064B-\u065F\u0640]+/g, ' ').trim(); // Handle Arabic diacritics and kashida
         // Normalize common Arabic letter variations
         const normalizedMessage = cleanedMessage
            .replace(/أ|إ|آ/g, 'ا') // Normalize Alif forms
            .replace(/ى/g, 'ي')     // Normalize Alef Maksura
            .replace(/ة/g, 'ه');    // Normalize Teh Marbuta

         for (const key in PREDEFINED_RESPONSES) {
             // Normalize the key for comparison
             const normalizedKey = key.toLowerCase()
                .replace(/[?؟!,.\s\u064B-\u065F\u0640]+/g, ' ')
                .trim()
                .replace(/أ|إ|آ/g, 'ا')
                .replace(/ى/g, 'ي')
                .replace(/ة/g, 'ه');

              // Check for exact match or starting phrase match (with space for word boundary)
              if (normalizedMessage === normalizedKey || (normalizedKey.length > 2 && normalizedMessage.startsWith(normalizedKey + ' '))) {
                  return PREDEFINED_RESPONSES[key];
              }
         }
         return null; // No predefined response found
     }


    // --- Speech Recognition (STT) --- (Original Code Kept)
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let isRecording = false;

    if (SpeechRecognition && micButton) {
        recognition = new SpeechRecognition();
        recognition.lang = 'ar-SA';
        recognition.continuous = false;
        recognition.interimResults = true;

        recognition.onstart = () => {
            console.log('Speech recognition started'); isRecording = true; micButton.classList.add('recording'); micButton.title = 'إيقاف التسجيل الصوتي'; if(messageInput) messageInput.placeholder = 'استمع... تحدث الآن...';
        };
        recognition.onresult = (event) => {
            let interimTranscript = ''; let finalTranscript = '';
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript;
                else interimTranscript += event.results[i][0].transcript;
            }
            if (finalTranscript && messageInput) {
                 if (messageInput.value && !messageInput.value.match(/[\s\n]$/)) messageInput.value += ' ';
                messageInput.value += finalTranscript; adjustInputHeight();
            }
             messageInput?.focus();
        };
        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error); let errorMessage = 'حدث خطأ في التعرف على الصوت.';
             if (event.error === 'not-allowed' || event.error === 'service-not-allowed') errorMessage = 'تم رفض الوصول إلى الميكروفون.';
             else if (event.error === 'no-speech') errorMessage = 'لم يتم الكشف عن صوت.';
             else if (event.error === 'audio-capture') errorMessage = 'فشل التقاط الصوت.';
             else if (event.error === 'network') errorMessage = 'مشكلة في الشبكة أثناء التعرف.';
             alert(`خطأ في التعرف على الصوت: ${errorMessage}`);
             isRecording = false; micButton?.classList.remove('recording'); if(micButton) micButton.title = 'إدخال صوتي'; if(messageInput) messageInput.placeholder = 'اكتب رسالتك هنا...';
        };
        recognition.onend = () => {
            console.log('Speech recognition ended'); isRecording = false; micButton?.classList.remove('recording'); if(micButton) micButton.title = 'إدخال صوتي'; if(messageInput) { messageInput.placeholder = 'اكتب رسالتك هنا...'; messageInput.focus(); }
        };
         micButton.addEventListener('click', () => {
           if (isRecording) recognition.stop();
           else { try { recognition.start(); } catch (e) { console.error("STT Start Error:", e); alert("لم يتمكن من بدء التعرف الصوتي."); } }
         });
    } else { console.warn('SpeechRecognition not supported.'); if (micButton) micButton.style.display = 'none'; }

    // --- Speech Synthesis (TTS) --- (Original Code Kept)
    const SpeechSynthesis = window.speechSynthesis;
    let availableVoices = [];
    let speakingUtterance = null;
    function loadVoices() { if (!SpeechSynthesis) return; availableVoices = SpeechSynthesis.getVoices(); const arabicVoices = availableVoices.filter(v => v.lang.startsWith('ar')); console.log(`${availableVoices.length} voices loaded, ${arabicVoices.length} Arabic.`); }
    function stopSpeaking() { if (SpeechSynthesis && SpeechSynthesis.speaking) { SpeechSynthesis.cancel(); speakingUtterance = null; document.querySelectorAll('.speak-btn i.speaking').forEach(icon => icon.className = 'fas fa-volume-up'); console.log('TTS stopped.'); } }
    function speakText(text, buttonElement = null) { /* ... (same original logic, including voice selection) ... */
         if (!SpeechSynthesis || !text) return false; if (availableVoices.length === 0) loadVoices(); stopSpeaking();
         try {
             const utterance = new SpeechSynthesisUtterance(text); utterance.lang = 'ar'; utterance.rate = 0.9; utterance.pitch = 1.0; utterance.volume = 1.0;
             let selectedVoice = availableVoices.find(v => v.lang === 'ar-SA') || availableVoices.find(v => v.lang.startsWith('ar-')) || availableVoices.find(v => v.default);
             if (selectedVoice) utterance.voice = selectedVoice; else console.warn('No Arabic voice, using default.');
             const icon = buttonElement?.querySelector('i'); const originalClass = icon?.className;
             utterance.onstart = () => { speakingUtterance = utterance; if (icon) icon.className = 'fas fa-volume-high speaking'; };
             utterance.onend = () => { speakingUtterance = null; if (icon && originalClass) icon.className = originalClass; };
             utterance.onerror = (event) => { console.error('TTS error:', event.error); speakingUtterance = null; if (icon && originalClass) icon.className = originalClass; alert(`TTS Error: ${event.error}`); };
             SpeechSynthesis.speak(utterance); return true;
         } catch (err) { console.error('TTS init error:', err); alert('TTS Error'); return false; }
    }
    if (SpeechSynthesis && ttsToggle) {
        if (SpeechSynthesis.onvoiceschanged !== undefined) SpeechSynthesis.onvoiceschanged = loadVoices; loadVoices();
        messagesContainer?.addEventListener('click', (event) => { const speakButton = event.target.closest('.speak-btn'); if (!speakButton) return; const bubble = speakButton.closest('.message-bubble'); const p = bubble?.querySelector('p'); if (!p?.textContent) return; if (speakingUtterance && speakingUtterance.text === p.textContent && SpeechSynthesis.speaking) stopSpeaking(); else speakText(p.textContent, speakButton); });
        const storedTtsPref = localStorage.getItem('ttsEnabled'); if(storedTtsPref === 'true') ttsToggle.checked = true;
        ttsToggle.addEventListener('change', () => { localStorage.setItem('ttsEnabled', ttsToggle.checked); if (!ttsToggle.checked) stopSpeaking(); });
    } else { console.warn('SpeechSynthesis not supported or ttsToggle missing.'); if (ttsToggle) ttsToggle.closest('.setting-item')?.style.display = 'none'; }

    // --- Initialize Models --- (Original Code Kept)
    const availableModels = [ { value: 'mistralai/mistral-7b-instruct', label: 'Mistral 7B' }, { value: 'anthropic/claude-3-haiku', label: 'Claude 3 Haiku' }, { value: 'google/gemini-pro', label: 'Gemini Pro' }, { value: 'meta-llama/llama-3-8b-instruct', label: 'LLaMA 3 8B' }, { value: 'google/gemma-7b-it', label: 'Gemma 7B' }, { value: 'openai/gpt-3.5-turbo', label: 'GPT-3.5 Turbo' }, { value: 'anthropic/claude-3-sonnet', label: 'Claude 3 Sonnet' } ];
    if(modelSelect){ modelSelect.innerHTML = ''; availableModels.forEach(model => { const option = document.createElement('option'); option.value = model.value; option.textContent = model.label; modelSelect.appendChild(option); }); const savedModel = localStorage.getItem('selectedModel'); if (savedModel && availableModels.some(m => m.value === savedModel)) modelSelect.value = savedModel; else if (availableModels.length > 0) modelSelect.value = availableModels[0].value; modelSelect.addEventListener('change', () => localStorage.setItem('selectedModel', modelSelect.value)); }

    // --- Conversation Management --- (Original Code Kept)
    async function loadConversations() { if (!conversationsList) return; conversationsList.innerHTML = '<div class="empty-state">جارٍ التحميل...</div>'; try { const response = await fetch('/api/conversations'); if (!response.ok) throw new Error(`HTTP ${response.status}`); const conversations = await response.json(); displayConversations(conversations); } catch (error) { console.error('Error loading conversations:', error); if(conversationsList) conversationsList.innerHTML = `<div class="empty-state">فشل التحميل</div>`; } }
    function displayConversations(conversations) { if (!conversationsList) return; conversationsList.innerHTML = ''; if (!conversations || conversations.length === 0) { conversationsList.innerHTML = '<div class="empty-state">لا توجد محادثات</div>'; return; } conversations.forEach(conv => addConversationToList(conv, false)); }
    function addConversationToList(conv, prepend = false) { if (!conversationsList) return; const emptyState = conversationsList.querySelector('.empty-state'); if (emptyState) emptyState.remove(); const item = document.createElement('div'); item.className = 'conversation-item'; item.dataset.conversationId = conv.id; if (conv.id === currentConversationId) item.classList.add('active'); const titleSpan = document.createElement('span'); titleSpan.textContent = conv.title || "محادثة جديدة"; titleSpan.title = `${titleSpan.textContent}\n${formatDate(conv.updated_at)}`; const actionsDiv = createConversationActions(conv.id, conv.title); item.appendChild(titleSpan); item.appendChild(actionsDiv); item.addEventListener('click', () => loadConversation(conv.id)); if (prepend) conversationsList.insertBefore(item, conversationsList.firstChild); else conversationsList.appendChild(item); }
    function createConversationActions(id, title) { const actionsDiv = document.createElement('div'); actionsDiv.className = 'conversation-actions'; actionsDiv.appendChild(createActionButton('edit-conv-btn', 'تعديل', 'fa-edit', (e) => { e.stopPropagation(); editConversationTitle(id, title); })); actionsDiv.appendChild(createActionButton('delete-conv-btn', 'حذف', 'fa-trash-alt', (e) => { e.stopPropagation(); confirmDeleteConversation(id); })); return actionsDiv; }
    async function loadConversation(conversationId) { if (!messagesContainer || isTyping) return; stopSpeaking(); messagesContainer.innerHTML = '<div class="empty-state">جارٍ التحميل...</div>'; hideRegenerateButton(); try { const response = await fetch(`/api/conversations/${conversationId}`); if (!response.ok) throw new Error(`HTTP ${response.status}`); const conversation = await response.json(); clearMessages(false); currentConversationId = conversationId; messages = conversation.messages?.map(msg => ({ ...msg })) || []; if (messages.length > 0) messages.forEach(msg => addMessageToUI(msg.role, msg.content, false, msg.created_at, msg.id)); else if(messagesContainer) messagesContainer.innerHTML = '<div class="empty-state">المحادثة فارغة.</div>'; document.querySelectorAll('.conversation-item').forEach(item => item.classList.toggle('active', item.dataset.conversationId === conversationId)); if (window.innerWidth <= 768 && settingsSidebar?.classList.contains('show')) toggleSidebar(); scrollToBottom(true); if (messages.length > 0 && messages[messages.length - 1].role === 'assistant') showRegenerateButton(); else hideRegenerateButton(); } catch (error) { console.error('Error loading conversation:', error); if(messagesContainer) messagesContainer.innerHTML = `<div class="empty-state">فشل تحميل المحادثة.</div>`; alert('فشل تحميل المحادثة.'); currentConversationId = null; document.querySelectorAll('.conversation-item.active').forEach(item => item.classList.remove('active')); } }
    function editConversationTitle(conversationId, currentTitle) { const newTitle = prompt('أدخل العنوان الجديد:', currentTitle); if (newTitle !== null && newTitle.trim() !== '' && newTitle.trim() !== currentTitle) updateConversationTitle(conversationId, newTitle.trim()); }
    async function updateConversationTitle(conversationId, newTitle) { try { const response = await fetch(`/api/conversations/${conversationId}/title`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: newTitle }) }); if (!response.ok) throw new Error('Failed update'); const item = conversationsList?.querySelector(`.conversation-item[data-conversation-id="${conversationId}"] span`); if(item) item.textContent = newTitle; } catch (error) { console.error('Update title error:', error); alert('فشل تحديث العنوان.'); } }
    function confirmDeleteConversation(conversationId) { if(!confirmMessage) return; confirmMessage.textContent = 'هل أنت متأكد من حذف المحادثة؟'; showConfirmModal(() => deleteConversation(conversationId)); }
    async function deleteConversation(conversationId) { try { const response = await fetch(`/api/conversations/${conversationId}`, { method: 'DELETE' }); if (!response.ok) throw new Error('Failed delete'); if (conversationId === currentConversationId) { clearMessages(); currentConversationId = null; messages = []; } loadConversations(false); } catch (error) { console.error('Delete conv error:', error); alert('فشل حذف المحادثة.'); } }

    // --- Clear Messages UI --- (Original Code Kept, uses updated welcome message const)
    function clearMessages(addWelcome = true) { if (!messagesContainer) return; messagesContainer.innerHTML = ''; hideRegenerateButton(); if (addWelcome) addMessageToUI('assistant', WELCOME_MESSAGE_CONTENT, true); }

    // --- Add Message to UI --- (Original Code Kept, uses helper function)
    function addMessageToUI(role, content, isWelcome = false, timestamp = null, messageId = null) { if (!messagesContainer) return; messagesContainer.querySelector('.empty-state')?.remove(); const bubble = document.createElement('div'); bubble.className = `message-bubble ${role === 'user' ? 'user-bubble' : 'ai-bubble'} fade-in`; if (messageId) bubble.dataset.messageId = messageId; const p = document.createElement('p'); p.textContent = content; bubble.appendChild(p); if (role === 'assistant') { const actions = document.createElement('div'); actions.className = 'message-actions'; const copyBtn = createActionButton('copy-btn', 'نسخ', 'fa-copy', () => copyToClipboard(content, copyBtn)); actions.appendChild(copyBtn); if (SpeechSynthesis && ttsToggle) { const speakBtn = createActionButton('speak-btn', 'استماع', 'fa-volume-up'); actions.appendChild(speakBtn); } bubble.appendChild(actions); if (!isWelcome && ttsToggle?.checked && typeof speakText === 'function') setTimeout(() => speakText(content), 500); } messagesContainer.appendChild(bubble); if (!isWelcome) scrollToBottom(); }
    function createActionButton(className, title, iconClass, onClick = null) { const button = document.createElement('button'); button.className = `icon-button ${className}`; button.title = title; button.innerHTML = `<i class="fas ${iconClass}"></i>`; if (onClick) button.addEventListener('click', onClick); return button; }
    function copyToClipboard(text, buttonElement = null) { navigator.clipboard.writeText(text).then(() => { if (buttonElement) { const icon = buttonElement.querySelector('i'); const orig = icon?.className; if(icon) icon.className = 'fas fa-check'; setTimeout(() => { if(icon && orig) icon.className = orig; }, 2000); } }).catch(err => { console.error('Copy failed:', err); alert('فشل النسخ'); }); }

    // --- Regenerate Button --- (Original Code Kept)
    function createRegenerateButton() { let btn = document.getElementById('regenerate-button'); if (!btn && messagesContainer && document.getElementById('input-area')) { btn = document.createElement('button'); btn.id = 'regenerate-button'; btn.innerHTML = '<i class="fas fa-redo"></i> إعادة توليد'; btn.addEventListener('click', handleRegenerate); document.getElementById('input-area').before(btn); } return btn; }
    function showRegenerateButton() { const btn = createRegenerateButton(); if(btn) btn.style.display = 'flex'; adjustInputHeight(); }
    function hideRegenerateButton() { const btn = document.getElementById('regenerate-button'); if(btn) btn.remove(); adjustInputHeight(); }
    async function handleRegenerate() { if (!currentConversationId || isTyping || messages.length === 0) return; const lastMsgIdx = messages.length - 1; if (messages[lastMsgIdx].role !== 'assistant') return; isTyping = true; hideRegenerateButton(); stopSpeaking(); const lastBubble = messagesContainer?.querySelector('.message-bubble:last-of-type.ai-bubble'); const lastContent = messages[lastMsgIdx].content; try { lastBubble?.remove(); messages.pop(); addTypingIndicator(); const history = messages.slice(-20).map(m => ({ role: m.role, content: m.content })); const body = { conversation_id: currentConversationId, model: modelSelect?.value, temperature: parseFloat(temperatureSlider?.value || 0.7), max_tokens: parseInt(maxTokensInput?.value || 512, 10) }; const response = await fetch('/api/regenerate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); removeTypingIndicator(); if (!response.ok) { if (lastContent) { addMessageToUI('assistant', lastContent); messages.push({ role: 'assistant', content: lastContent }); } const errData = await response.json().catch(()=>({})); throw new Error(errData.error || REGENERATE_ERROR); } const data = await response.json(); const ts = new Date().toISOString(); addMessageToUI('assistant', data.content, false, ts); messages.push({ role: 'assistant', content: data.content, created_at: ts }); showRegenerateButton(); } catch (error) { console.error('Regen error:', error); removeTypingIndicator(); alert(error.message || REGENERATE_ERROR); if (messages.length > 0 && messages[messages.length - 1].role === 'assistant') showRegenerateButton(); } finally { isTyping = false; adjustInputHeight(); messageInput?.focus(); } }

    // --- Typing Indicator --- (Original Code Kept)
    function addTypingIndicator() { removeTypingIndicator(); const indicator = document.createElement('div'); indicator.className = 'message-bubble ai-bubble typing-indicator-bubble'; indicator.id = 'typing-indicator'; indicator.innerHTML = `<div class="typing-indicator"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`; if(messagesContainer) { messagesContainer.appendChild(indicator); scrollToBottom(); } }
    function removeTypingIndicator() { document.getElementById('typing-indicator')?.remove(); }

    // --- Send Message --- (Original Code Kept, uses updated welcome message const)
    async function sendMessage() { if (!messageInput || !sendButton) return; const userMessage = messageInput.value.trim(); if (!userMessage || isTyping) return; isTyping = true; sendButton.disabled = true; messageInput.disabled = true; hideRegenerateButton(); stopSpeaking(); const userTimestamp = new Date().toISOString(); addMessageToUI('user', userMessage, false, userTimestamp); messages.push({ role: 'user', content: userMessage, created_at: userTimestamp }); messageInput.value = ''; adjustInputHeight(); scrollToBottom(); addTypingIndicator(); const predefinedResponse = checkPredefinedResponse(userMessage); if (predefinedResponse) { setTimeout(() => { removeTypingIndicator(); const aiTimestamp = new Date().toISOString(); addMessageToUI('assistant', predefinedResponse, false, aiTimestamp); messages.push({ role: 'assistant', content: predefinedResponse, created_at: aiTimestamp }); isTyping = false; sendButton.disabled = false; messageInput.disabled = false; messageInput.focus(); showRegenerateButton(); }, 300); return; } if (!navigator.onLine) { setTimeout(() => { removeTypingIndicator(); addMessageToUI('assistant', FRONTEND_OFFLINE_MESSAGE, false, new Date().toISOString()); isTyping = false; sendButton.disabled = false; messageInput.disabled = false; messageInput.focus(); }, 300); return; } try { const history = messages.slice(-20).map(m => ({ role: m.role, content: m.content })); const body = { history: history, conversation_id: currentConversationId, model: modelSelect?.value, temperature: parseFloat(temperatureSlider?.value || 0.7), max_tokens: parseInt(maxTokensInput?.value || 512, 10) }; const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); removeTypingIndicator(); if (!response.ok) { const errData = await response.json().catch(()=>({})); throw new Error(errData.error || MESSAGE_SEND_ERROR); } const data = await response.json(); const aiTimestamp = new Date().toISOString(); if (!currentConversationId && data.id) { currentConversationId = data.id; addConversationToList({ id: data.id, title: messages[0]?.content.substring(0, 80) || "محادثة جديدة", updated_at: aiTimestamp }, true); document.querySelectorAll('.conversation-item').forEach(item => item.classList.toggle('active', item.dataset.conversationId === currentConversationId)); } addMessageToUI('assistant', data.content, false, aiTimestamp); messages.push({ role: 'assistant', content: data.content, created_at: aiTimestamp }); showRegenerateButton(); } catch (error) { console.error('Send error:', error); removeTypingIndicator(); addMessageToUI('error', `${error.message || MESSAGE_SEND_ERROR}`); if (messages.length > 1 && messages[messages.length-1].role === 'user' && messages[messages.length-2]?.role === 'assistant') showRegenerateButton(); } finally { isTyping = false; if(sendButton) sendButton.disabled = false; if(messageInput) messageInput.disabled = false; messageInput?.focus(); adjustInputHeight(); } }

    // --- Utility Functions --- (Original Code Kept)
    function scrollToBottom(instant = false) { if(messagesContainer) messagesContainer.scrollTo({ top: messagesContainer.scrollHeight, behavior: instant ? 'instant' : 'smooth' }); }
    function adjustInputHeight() { if (!messageInput) return; messageInput.style.height = 'auto'; const newHeight = Math.min(messageInput.scrollHeight, 200); messageInput.style.height = `${newHeight}px`; const inputAreaHeight = document.getElementById('input-area')?.offsetHeight || 70; const regenBtn = document.getElementById('regenerate-button'); const regenHeight = (regenBtn && regenBtn.style.display !== 'none') ? regenBtn.offsetHeight + 16 : 0; if (messagesContainer) messagesContainer.style.paddingBottom = `${inputAreaHeight + regenHeight + 10}px`; }
    function toggleSidebar() { if (!settingsSidebar || !sidebarOverlay) return; const show = !settingsSidebar.classList.contains('show'); settingsSidebar.classList.toggle('show', show); sidebarOverlay?.classList.toggle('show', show); document.body.classList.toggle('sidebar-open', show); document.body.style.overflow = show && window.innerWidth <= 768 ? 'hidden' : ''; }
    function showConfirmModal(callback) { if(!confirmModal) return; confirmationCallback = callback; confirmModal.classList.add('show'); }
    function hideConfirmModal() { if(!confirmModal) return; confirmModal.classList.remove('show'); confirmationCallback = null; }
    function formatDate(iso) { if (!iso) return ''; try { const d = new Date(iso); return new Intl.DateTimeFormat('ar-SA', { year: 'numeric', month: 'short', day: 'numeric'}).format(d); } catch(e){ return ''; } }
    function formatTime(iso) { if (!iso) return ''; try { const d = new Date(iso); return new Intl.DateTimeFormat('ar-SA', { hour: 'numeric', minute: '2-digit', hour12: true}).format(d); } catch(e){ return ''; } }
    function escapeHtml(unsafe="") { if(typeof unsafe !== 'string') return ''; return unsafe.replace(/&/g, "&").replace(/</g, "<").replace(/>/g, ">").replace(/"/g, """).replace(/'/g, "'"); }

    // --- Event Listeners --- (Original Code Kept)
    function setupEventListeners() { if (sendButton) sendButton.addEventListener('click', sendMessage); if (messageInput) { messageInput.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } else if (e.key === 'Enter' && e.shiftKey) { setTimeout(adjustInputHeight, 0); } }); messageInput.addEventListener('input', adjustInputHeight); } if (newConversationButton) { newConversationButton.addEventListener('click', () => { if (isTyping) return; stopSpeaking(); clearMessages(); currentConversationId = null; messages = []; hideRegenerateButton(); document.querySelectorAll('.conversation-item.active').forEach(item => item.classList.remove('active')); if (window.innerWidth <= 768 && settingsSidebar?.classList.contains('show')) toggleSidebar(); messageInput?.focus(); }); } if (temperatureSlider) { temperatureSlider.addEventListener('input', () => { if(temperatureValueSpan) temperatureValueSpan.textContent = temperatureSlider.value; }); temperatureSlider.addEventListener('change', () => localStorage.setItem('temperature', temperatureSlider.value)); } if (maxTokensInput) maxTokensInput.addEventListener('change', () => localStorage.setItem('maxTokens', maxTokensInput.value) ); if (darkModeToggle) { darkModeToggle.addEventListener('change', () => { document.body.classList.toggle('dark-mode', darkModeToggle.checked); localStorage.setItem('darkModeEnabled', darkModeToggle.checked); }); } toggleSidebarButton?.addEventListener('click', toggleSidebar); mobileMenuButton?.addEventListener('click', toggleSidebar); mobileSettingsButton?.addEventListener('click', toggleSidebar); closeSidebarButton?.addEventListener('click', toggleSidebar); sidebarOverlay?.addEventListener('click', toggleSidebar); confirmOkButton?.addEventListener('click', () => { if (confirmationCallback) confirmationCallback(); hideConfirmModal(); }); confirmCancelButton?.addEventListener('click', hideConfirmModal); window.addEventListener('online', () => offlineIndicator?.classList.remove('visible')); window.addEventListener('offline', () => offlineIndicator?.classList.add('visible')); window.addEventListener('resize', adjustInputHeight); }

    // --- Initialization --- (Original Code Kept)
    function initializeApp() { console.log("Initializing App..."); try { const savedTemp = localStorage.getItem('temperature'); if (savedTemp && temperatureSlider && temperatureValueSpan) { temperatureSlider.value = savedTemp; temperatureValueSpan.textContent = savedTemp; } const savedTokens = localStorage.getItem('maxTokens'); if (savedTokens && maxTokensInput) maxTokensInput.value = savedTokens; const savedDarkMode = localStorage.getItem('darkModeEnabled'); if (darkModeToggle) darkModeToggle.checked = savedDarkMode === 'true'; document.body.classList.toggle('dark-mode', darkModeToggle?.checked || false); if (!navigator.onLine && offlineIndicator) offlineIndicator.classList.add('visible'); setupEventListeners(); clearMessages(); loadConversations(); adjustInputHeight(); messageInput?.focus(); console.log("App Initialized."); } catch(error) { console.error("FATAL Init Error:", error); alert("فشل تحميل التطبيق."); document.body.innerHTML = `<div style='padding:20px; color:red;'>Error initializing. Please refresh. Details: ${error.message}</div>`; } }

    initializeApp();

}); // End DOMContentLoaded

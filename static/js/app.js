--- START OF FILE app.js ---

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed. Initializing app...");

    // --- DOM Element Selection (with checks) ---
    function getElement(id, required = true) {
        const element = document.getElementById(id);
        if (!element && required) {
            console.error(`CRITICAL: Element with ID '${id}' not found!`);
            // Potentially stop execution or show a major error
        } else if (!element) {
            console.warn(`Optional element with ID '${id}' not found.`);
        }
        return element;
    }

    const settingsSidebar = getElement('settings-sidebar');
    const toggleSidebarButton = getElement('toggle-sidebar', false); // Might be hidden on mobile
    const closeSidebarButton = getElement('close-sidebar', false); // Might not exist if HTML changes
    const mobileMenuButton = getElement('mobile-menu', false);     // Might be hidden on desktop
    const mobileSettingsButton = getElement('mobile-settings', false); // Might be hidden
    const sidebarOverlay = getElement('sidebar-overlay', false);
    const newConversationButton = getElement('new-conversation');
    const conversationsList = getElement('conversations-list');
    const messagesContainer = getElement('messages');
    const messageInput = getElement('message-input');
    const sendButton = getElement('send-button');
    const modelSelect = getElement('model-select');
    const temperatureSlider = getElement('temperature-slider');
    const temperatureValueSpan = getElement('temperature-value');
    const maxTokensInput = getElement('max-tokens-input');
    const darkModeToggle = getElement('dark-mode-toggle');
    const offlineIndicator = getElement('offline-indicator');
    const appErrorMessage = getElement('app-error-message');
    const confirmModal = getElement('confirm-modal');
    const confirmMessage = getElement('confirm-message');
    const confirmOkButton = getElement('confirm-ok');
    const confirmCancelButton = getElement('confirm-cancel');
    const ttsToggle = getElement('tts-toggle', false); // TTS might be hidden if unsupported
    const micButton = getElement('mic-button', false); // Mic might be hidden if unsupported

    // --- State Variables ---
    let currentConversationId = null;
    let messages = [];
    let isTyping = false;
    let confirmationCallback = null;
    let appErrorTimeout = null;
    let isSidebarOpen = false; // Track sidebar state

    // --- Constants ---
    const WELCOME_MESSAGE_CONTENT = "السلام عليكم! أنا مساعد dzteck الرقمي. كيف يمكنني مساعدتك اليوم؟";
    const FRONTEND_OFFLINE_MESSAGE = "أعتذر، لا يوجد اتصال بالإنترنت حاليًا. لا يمكنني معالجة طلبك الآن.";
    const GENERAL_ERROR_MESSAGE = "حدث خطأ ما. يرجى المحاولة مرة أخرى لاحقاً.";
    const CONVERSATION_LOAD_ERROR = "فشل تحميل المحادثات.";
    const MESSAGE_SEND_ERROR = "فشل إرسال الرسالة.";
    const REGENERATE_ERROR = "فشل إعادة توليد الرد.";

    // --- Predefined Responses ---
     const PREDEFINED_RESPONSES = {
        // Greetings & Basic Interaction
        "السلام عليكم": "وعليكم السلام ورحمة الله وبركاته! كيف يمكنني خدمتك اليوم؟",
        "اهلا": "أهلاً بك! أنا هنا لمساعدتك.",
        "مرحبا": "مرحباً! بماذا يمكنني أن أخدمك؟",
        "صباح الخير": "صباح النور والسرور!",
        "مساء الخير": "مساء النور! كيف يمكنني المساعدة؟",
        "كيف حالك": "أنا بخير حال، شكراً لسؤالك! كيف يمكنني مساعدتك اليوم؟",
        "شكرا": "على الرحب والسعة! يسعدني تقديم المساعدة.",
        "شكرا لك": "لا شكر على واجب. هل هناك أي شيء آخر يمكنني المساعدة به؟",
        "عفوا": "أهلاً بك.",
        "مع السلامة": "إلى اللقاء! أتمنى لك يوماً سعيداً.",
        "وداعا": "في أمان الله.",

        // About the Bot / dzteck
        "من انت": "أنا مساعد رقمي تم تطويره بواسطة فريق dzteck لمساعدتك في الإجابة على استفساراتك وتنفيذ بعض المهام.",
        "ما اسمك": "يمكنك مناداتي بمساعد dzteck.",
        "من صنعك": "تم تطويري وبرمجتي بواسطة فريق المطورين في شركة dzteck للبرمجيات.",
        "مين عملك": "تم تطويري وبرمجتي بواسطة فريق المطورين في شركة dzteck للبرمجيات.",
        "من طورك": "تم تطويري وبرمجتي بواسطة فريق المطورين في شركة dzteck للبرمجيات.",
        "من انشاك": "تم تطويري وبرمجتي بواسطة فريق المطورين في شركة dzteck للبرمجيات.",
        "منو سواك": "تم تطويري وبرمجتي بواسطة فريق المطورين في شركة dzteck للبرمجيات.",
        "ما هي dzteck": "dzteck هي شركة متخصصة في تطوير الحلول البرمجية وتطبيقات الذكاء الاصطناعي، وتقديم استشارات تقنية متقدمة.", // Expanded example
        "ماذا يمكنك ان تفعل": "يمكنني الإجابة على مجموعة واسعة من الأسئلة، المساعدة في كتابة النصوص، تقديم المعلومات العامة، وشرح المفاهيم التقنية. جرب أن تسألني شيئاً!",
        "ما هي قدراتك": "أستطيع فهم اللغة العربية والإنجليزية، البحث عن المعلومات (إذا كان النموذج متصلاً بالإنترنت)، إنشاء محتوى نصي، والإجابة على استفساراتك العامة. قدراتي تعتمد على النموذج اللغوي الذي تم اختياره في الإعدادات.",

        // Common Questions / Requests (Examples)
        "ما هو الوقت": "أنا آسف، ليس لدي وصول مباشر للوقت الحالي. يمكنك التحقق من ساعة جهازك.",
        "ما هو تاريخ اليوم": "أعتذر، لا يمكنني الوصول إلى التاريخ الحالي بشكل مباشر. يرجى التحقق من تقويم جهازك.",
        "احكي لي نكتة": "مرة مهندس برمجيات قابل لمبة، قالها: إنتي منورة النهاردة ليه؟ قالتله: عشان عاملة update!", // Tech joke
        "ما هو الذكاء الاصطناعي": "الذكاء الاصطناعي (AI) هو فرع من علوم الحاسوب يهدف إلى إنشاء أنظمة قادرة على أداء مهام تتطلب عادةً ذكاءً بشرياً، مثل التعلم، حل المشكلات، فهم اللغة، واتخاذ القرارات.",
    };

    function checkPredefinedResponse(userMessage) {
        // Input validation
        if (typeof userMessage !== 'string' || !userMessage) {
            return null;
        }
        try {
            const cleanedMessage = userMessage.toLowerCase().replace(/[?؟!,.\s\u064B-\u065F\u0640]+/g, ' ').trim();
            const normalizedMessage = cleanedMessage
                .replace(/أ|إ|آ/g, 'ا')
                .replace(/ى/g, 'ي')
                .replace(/ة/g, 'ه');

            for (const key in PREDEFINED_RESPONSES) {
                // Normalize the key only once or cache it if performance is critical
                const normalizedKey = key.toLowerCase()
                    .replace(/[?؟!,.\s\u064B-\u065F\u0640]+/g, ' ')
                    .trim()
                    .replace(/أ|إ|آ/g, 'ا')
                    .replace(/ى/g, 'ي')
                    .replace(/ة/g, 'ه');

                if (normalizedMessage === normalizedKey || (normalizedKey.length > 2 && normalizedMessage.startsWith(normalizedKey + ' '))) {
                    return PREDEFINED_RESPONSES[key];
                }
            }
        } catch (error) {
            console.error("Error in checkPredefinedResponse:", error);
        }
        return null;
    }

    // --- Global Error Display ---
    function showAppError(message, duration = 5000) {
        if (!appErrorMessage) return; // Don't proceed if error element doesn't exist
        console.log("Showing App Error:", message);
        if (appErrorTimeout) clearTimeout(appErrorTimeout);

        appErrorMessage.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}`;
        appErrorMessage.classList.add('show');

        // Adjust position (safer calculation)
        try {
            const inputAreaHeight = document.getElementById('input-area')?.offsetHeight || 80;
            const regenerateButton = document.getElementById('regenerate-button');
            const regenerateHeight = (regenerateButton && regenerateButton.style.display !== 'none') ? regenerateButton.offsetHeight + 16 : 0;
            const bottomOffset = inputAreaHeight + regenerateHeight + 10;
            appErrorMessage.style.bottom = `${bottomOffset}px`;
        } catch (e) {
            console.error("Error calculating error message position:", e);
            appErrorMessage.style.bottom = '80px'; // Fallback position
        }

        appErrorTimeout = setTimeout(() => {
            if (appErrorMessage) appErrorMessage.classList.remove('show');
        }, duration);
    }

    // --- Speech Recognition (STT) ---
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let isRecording = false;

    if (SpeechRecognition && micButton) {
        try {
            recognition = new SpeechRecognition();
            recognition.lang = 'ar-SA';
            recognition.continuous = false;
            recognition.interimResults = true;

            recognition.onstart = () => {
                console.log('STT started'); isRecording = true; micButton.classList.add('recording'); micButton.title = 'إيقاف التسجيل'; if(messageInput) messageInput.placeholder = 'استمع...';
            };
            recognition.onresult = (event) => { /* ... (same logic as before) ... */
                 let interimTranscript = '';
                 let finalTranscript = '';
                 for (let i = event.resultIndex; i < event.results.length; ++i) {
                     if (event.results[i].isFinal) { finalTranscript += event.results[i][0].transcript; }
                     else { interimTranscript += event.results[i][0].transcript; }
                 }
                 if (finalTranscript && messageInput) {
                     const currentVal = messageInput.value;
                     messageInput.value = (currentVal && !currentVal.match(/[\s\n]$/) ? currentVal + ' ' : currentVal) + finalTranscript;
                     adjustInputHeight();
                 }
            };
             recognition.onerror = (event) => { /* ... (same logic with showAppError) ... */
                 console.error('STT Error:', event.error, event.message);
                 let userMessage = 'حدث خطأ في التعرف على الصوت.';
                 if (event.error === 'not-allowed' || event.error === 'service-not-allowed') userMessage = 'تم رفض الوصول إلى الميكروفون.';
                 else if (event.error === 'no-speech') userMessage = 'لم يتم الكشف عن صوت.';
                 else if (event.error === 'audio-capture') userMessage = 'فشل التقاط الصوت.';
                 else if (event.error === 'network') userMessage = 'مشكلة في الشبكة أثناء التعرف.';
                 showAppError(userMessage); // Use the central error display
                 // Reset state regardless of error type
                 isRecording = false;
                 if(micButton) { micButton.classList.remove('recording'); micButton.title = 'إدخال صوتي'; }
                 if(messageInput) messageInput.placeholder = 'اكتب رسالتك هنا...';
             };
            recognition.onend = () => {
                console.log('STT ended'); isRecording = false; if(micButton){ micButton.classList.remove('recording'); micButton.title = 'إدخال صوتي'; } if(messageInput) { messageInput.placeholder = 'اكتب رسالتك هنا...'; messageInput.focus(); }
            };

            micButton.addEventListener('click', () => {
                 // Permission checks and start/stop logic (same as before, ensure checks are robust)
                 if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { showAppError('المتصفح لا يدعم الميكروفون.'); return; }
                 navigator.permissions?.query({ name: 'microphone' }).then(permissionStatus => {
                     if (permissionStatus.state === 'denied') { showAppError('تم رفض الوصول للميكروفون.'); return; }
                     if (isRecording) { recognition.stop(); }
                     else { try { if(messageInput) messageInput.value = ''; recognition.start(); } catch (e) { console.error("STT Start Error:", e); showAppError('فشل بدء التعرف الصوتي.'); } }
                 }).catch(err => { // Proceed even if query fails
                     console.warn("Mic permission query failed:", err);
                     if (isRecording) { recognition.stop(); }
                     else { try { if(messageInput) messageInput.value = ''; recognition.start(); } catch (e) { console.error("STT Start Error (fallback):", e); showAppError('فشل بدء التعرف الصوتي.'); } }
                 });
            });

        } catch (error) {
            console.error("Failed to initialize SpeechRecognition:", error);
            if (micButton) micButton.style.display = 'none';
        }
    } else {
        console.warn('SpeechRecognition not supported.');
        if (micButton) micButton.style.display = 'none';
    }

    // --- Speech Synthesis (TTS) ---
    const SpeechSynthesis = window.speechSynthesis;
    let availableVoices = [];
    let speakingUtterance = null;
    let ttsEnabled = false; // Internal state

    function loadVoices() { /* ... (same as before) ... */ }
    function stopSpeaking() { /* ... (same as before, ensures icons are reset) ... */
         if (SpeechSynthesis && SpeechSynthesis.speaking) {
             SpeechSynthesis.cancel();
             speakingUtterance = null;
             document.querySelectorAll('.speak-btn i.speaking').forEach(icon => {
                  if(icon.classList.contains('fa-volume-high')) icon.className = 'fas fa-volume-up';
             });
             console.log('TTS stopped.');
         }
    }
    function speakText(text, buttonElement = null) { /* ... (same as before, uses showAppError) ... */
         if (!SpeechSynthesis || !text) return false;
         if (availableVoices.length === 0) loadVoices();
         stopSpeaking();
         try {
             const utterance = new SpeechSynthesisUtterance(text);
             // ... (set lang, rate, pitch, volume, select voice - same logic) ...
             let selectedVoice = availableVoices.find(v => v.lang === 'ar-SA' && /female/i.test(v.name)) ||
                                availableVoices.find(v => v.lang === 'ar-SA') ||
                                availableVoices.find(v => v.lang.startsWith('ar-') && /female/i.test(v.name)) ||
                                availableVoices.find(v => v.lang.startsWith('ar-')) ||
                                availableVoices.find(v => v.default && v.lang.startsWith('ar')) || // Try default Arabic
                                availableVoices.find(v => v.default);

             if (selectedVoice) utterance.voice = selectedVoice;
             else console.warn('No suitable Arabic voice found, using browser default.');

             const icon = buttonElement?.querySelector('i');
             const originalClass = icon?.className;
             utterance.onstart = () => { speakingUtterance = utterance; if (icon) icon.className = 'fas fa-volume-high speaking'; console.log('TTS started'); };
             utterance.onend = () => { speakingUtterance = null; if (icon && originalClass) icon.className = originalClass; console.log('TTS ended'); };
             utterance.onerror = (event) => { console.error('TTS error:', event.error); speakingUtterance = null; if (icon && originalClass) icon.className = originalClass; showAppError(`خطأ TTS: ${event.error}`); };
             SpeechSynthesis.speak(utterance);
             return true;
         } catch (err) { console.error('TTS init error:', err); showAppError('خطأ في خدمة نطق النص.'); return false; }
    }

    if (SpeechSynthesis && ttsToggle) {
        if (SpeechSynthesis.onvoiceschanged !== undefined) SpeechSynthesis.onvoiceschanged = loadVoices;
        loadVoices();
        // Event delegation for speak buttons
        messagesContainer?.addEventListener('click', (event) => { /* ... (same logic as before) ... */
             const speakButton = event.target.closest('.speak-btn');
             if (!speakButton) return;
             const messageBubble = speakButton.closest('.message-bubble');
             const textElement = messageBubble?.querySelector('p');
             if (!textElement?.textContent) return;
             if (speakingUtterance && speakingUtterance.text === textElement.textContent && SpeechSynthesis.speaking) stopSpeaking();
             else speakText(textElement.textContent, speakButton);
        });
        // TTS Toggle logic
        const storedTtsPreference = localStorage.getItem('ttsEnabled');
        ttsEnabled = storedTtsPreference === 'true';
        ttsToggle.checked = ttsEnabled;
        ttsToggle.addEventListener('change', () => {
            ttsEnabled = ttsToggle.checked;
            localStorage.setItem('ttsEnabled', ttsEnabled);
            if (!ttsEnabled) stopSpeaking();
        });
    } else {
        console.warn('SpeechSynthesis not supported or ttsToggle element missing.');
        if (ttsToggle) ttsToggle.closest('.setting-item')?.style.display = 'none';
    }


    // --- Initialize Models Dropdown ---
    const availableModels = [ /* ... (same model list) ... */ ];
    function populateModels() {
         if (!modelSelect) return;
         modelSelect.innerHTML = '';
         availableModels.forEach(model => {
             const option = document.createElement('option');
             option.value = model.value; option.textContent = model.label; modelSelect.appendChild(option);
         });
         const savedModel = localStorage.getItem('selectedModel');
         if (savedModel && availableModels.some(m => m.value === savedModel)) modelSelect.value = savedModel;
         else if (availableModels.length > 0) modelSelect.value = availableModels[0].value;
         modelSelect.addEventListener('change', () => localStorage.setItem('selectedModel', modelSelect.value));
    }
    populateModels();


    // --- Conversation Management ---
    async function loadConversations(showLoading = true) {
         if (!conversationsList) return;
         if (showLoading) conversationsList.innerHTML = '<div class="empty-state loading-conversations"><i class="fas fa-spinner fa-spin"></i> جارٍ التحميل...</div>';
         try {
             const response = await fetch('/api/conversations');
             if (!response.ok) throw new Error(`HTTP ${response.status}`);
             const conversations = await response.json();
             displayConversations(conversations);
         } catch (error) {
             console.error('Error loading conversations:', error);
             if(conversationsList) conversationsList.innerHTML = `<div class="empty-state error"><i class="fas fa-exclamation-triangle"></i> ${CONVERSATION_LOAD_ERROR}</div>`;
         }
    }

    function displayConversations(conversations) {
        if (!conversationsList) return;
        conversationsList.innerHTML = '';
        if (!conversations || conversations.length === 0) {
            conversationsList.innerHTML = '<div class="empty-state"><i class="fas fa-comments"></i> لا توجد محادثات</div>';
            return;
        }
        conversations.forEach(conv => addConversationToList(conv, false)); // Add without prepending
    }

     // Helper to add *one* conversation item, optionally at the top
     function addConversationToList(conv, prepend = false) {
         if (!conversationsList) return;
         const emptyState = conversationsList.querySelector('.empty-state');
         if (emptyState) emptyState.remove();

         const item = document.createElement('div');
         item.className = 'conversation-item';
         item.dataset.conversationId = conv.id;

         const titleSpan = document.createElement('span');
         titleSpan.textContent = conv.title || "محادثة جديدة";
         titleSpan.title = `${titleSpan.textContent}\n${formatDate(conv.updated_at)}`;

         const actionsDiv = createConversationActions(conv.id, conv.title);

         item.appendChild(titleSpan);
         item.appendChild(actionsDiv);
         item.addEventListener('click', () => handleConversationClick(conv.id, item));

         if (prepend) conversationsList.insertBefore(item, conversationsList.firstChild);
         else conversationsList.appendChild(item);
     }


    function createConversationActions(id, title) { /* ... (same as before) ... */
         const actionsDiv = document.createElement('div'); actionsDiv.className = 'conversation-actions';
         actionsDiv.appendChild(createActionButton('edit-conv-btn', 'تعديل', 'fa-edit', (e) => { e.stopPropagation(); editConversationTitle(id, title); }));
         actionsDiv.appendChild(createActionButton('delete-conv-btn', 'حذف', 'fa-trash-alt', (e) => { e.stopPropagation(); confirmDeleteConversation(id); }));
         return actionsDiv;
    }

    function handleConversationClick(id, itemElement) { /* ... (same as before) ... */
         if (id === currentConversationId || isTyping) return;
         document.querySelectorAll('.conversation-item.loading').forEach(el => el.classList.remove('loading'));
         if(itemElement) itemElement.classList.add('loading');
         loadConversation(id).finally(() => { if(itemElement) itemElement.classList.remove('loading'); });
    }

    async function loadConversation(conversationId) { /* ... (same error handling, uses showAppError) ... */
         if (!messagesContainer) return;
         stopSpeaking();
         messagesContainer.innerHTML = '<div class="empty-state loading-messages"><i class="fas fa-spinner fa-spin"></i> جارٍ تحميل الرسائل...</div>';
         hideRegenerateButton();

         try {
             const response = await fetch(`/api/conversations/${conversationId}`);
             if (!response.ok) throw new Error(`HTTP ${response.status}`);
             const conversation = await response.json();

             clearMessages(false); // Clear UI
             currentConversationId = conversationId;
             messages = conversation.messages?.map(msg => ({ ...msg })) || []; // Handle potential missing messages array

             if (messages.length > 0) messages.forEach(msg => addMessageToUI(msg.role, msg.content, false, msg.created_at, msg.id));
             else if(messagesContainer) messagesContainer.innerHTML = '<div class="empty-state"><i class="fas fa-comment-dots"></i> المحادثة فارغة.</div>';

             document.querySelectorAll('.conversation-item').forEach(item => item.classList.toggle('active', item.dataset.conversationId === conversationId));
             if (window.innerWidth <= 768 && isSidebarOpen) toggleSidebar(); // Close mobile sidebar
             scrollToBottom(true); // Scroll instantly
             if (messages.length > 0 && messages[messages.length - 1].role === 'assistant') showRegenerateButton();
             else hideRegenerateButton();

         } catch (error) {
             console.error('Error loading conversation:', error);
             if(messagesContainer) messagesContainer.innerHTML = `<div class="empty-state error"><i class="fas fa-exclamation-triangle"></i> فشل تحميل المحادثة.</div>`;
             showAppError('فشل تحميل المحادثة.');
             currentConversationId = null;
             document.querySelectorAll('.conversation-item.active').forEach(item => item.classList.remove('active'));
         }
    }

    function editConversationTitle(id, currentTitle) { /* ... (same) ... */
         const newTitle = prompt('أدخل العنوان الجديد:', currentTitle);
         if (newTitle && newTitle.trim() && newTitle.trim() !== currentTitle) updateConversationTitle(id, newTitle.trim());
    }
    async function updateConversationTitle(id, newTitle) { /* ... (same, uses showAppError) ... */
         const item = conversationsList?.querySelector(`.conversation-item[data-conversation-id="${id}"]`);
         item?.classList.add('loading');
         try {
             const response = await fetch(`/api/conversations/${id}/title`, { /* ... */ });
             if (!response.ok) throw new Error('Failed update');
             const titleSpan = item?.querySelector('span');
             if (titleSpan) { titleSpan.textContent = newTitle; /* Update title attr too */ }
         } catch (error) { console.error('Update title error:', error); showAppError('فشل تحديث العنوان.'); }
         finally { item?.classList.remove('loading'); }
    }
    function confirmDeleteConversation(id) { /* ... (same) ... */
         confirmMessage.textContent = 'هل أنت متأكد من حذف المحادثة نهائياً؟';
         showConfirmModal(() => deleteConversation(id));
    }
    async function deleteConversation(id) { /* ... (same, uses showAppError) ... */
         const item = conversationsList?.querySelector(`.conversation-item[data-conversation-id="${id}"]`);
         item?.classList.add('loading');
         try {
             const response = await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
             if (!response.ok) throw new Error('Failed delete');
             if (id === currentConversationId) { clearMessages(); currentConversationId = null; messages = []; }
             item?.remove();
             if (conversationsList && conversationsList.children.length === 0) conversationsList.innerHTML = '<div class="empty-state"><i class="fas fa-comments"></i> لا توجد محادثات</div>';
         } catch (error) { console.error('Delete conv error:', error); showAppError('فشل حذف المحادثة.'); item?.classList.remove('loading'); }
    }

    // --- Message UI ---
    function clearMessages(addWelcome = true) {
        if (!messagesContainer) return;
        messagesContainer.innerHTML = '';
        hideRegenerateButton();
        if (addWelcome) {
            addMessageToUI('assistant', WELCOME_MESSAGE_CONTENT, true, new Date().toISOString());
        }
    }

    function addMessageToUI(role, content, isInitialWelcome = false, timestamp = null, messageId = null) {
        if (!messagesContainer) return;
        // Remove empty state if present
        messagesContainer.querySelector('.empty-state')?.remove();

        const bubble = document.createElement('div');
        // Added 'error-bubble' handling based on role
        bubble.className = `message-bubble ${role === 'error' ? 'error-bubble' : (role + '-bubble')} fade-in`;
        if (messageId) bubble.dataset.messageId = messageId;

        const p = document.createElement('p');
        // Render content safely
        if (role === 'error') {
            p.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${escapeHtml(content || GENERAL_ERROR_MESSAGE)}`;
        } else {
             // Apply basic Markdown and escape HTML
            p.innerHTML = renderMarkdown(content || ""); // Use helper for clarity
        }
        bubble.appendChild(p);

        // Add Timestamp (only for non-error)
        if (timestamp && role !== 'error') {
            const timeDiv = document.createElement('div');
            timeDiv.className = 'message-timestamp';
            timeDiv.textContent = formatTime(timestamp);
            bubble.appendChild(timeDiv);
        }

        // Add Actions (only for user/assistant, not error)
        if (role === 'assistant' || role === 'user') {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'message-actions';
            // Copy Button (for both user & assistant)
            actionsDiv.appendChild(createActionButton('copy-btn', `نسخ ${role === 'user' ? 'الرسالة' : 'الرد'}`, 'fa-copy', () => copyToClipboard(content, actionsDiv.querySelector('.copy-btn'))));
            // Speak Button (only for assistant and if supported)
            if (role === 'assistant' && SpeechSynthesis) {
                 actionsDiv.appendChild(createActionButton('speak-btn', 'استماع', 'fa-volume-up')); // Listener is delegated
            }
             // Add Vote Buttons (only for assistant)
             // if (role === 'assistant') {
             //     actionsDiv.appendChild(createVoteButtons(messageId));
             // }
            bubble.appendChild(actionsDiv);
        }

        messagesContainer.appendChild(bubble);

        // Add listeners for any new copy code buttons
        bubble.querySelectorAll('.copy-code-button').forEach(button => {
             button.addEventListener('click', handleCodeCopyClick);
        });

        if (!isInitialWelcome) scrollToBottom();

         // Auto-TTS for assistant messages
         if (role === 'assistant' && !isInitialWelcome && ttsEnabled && typeof speakText === 'function') {
              setTimeout(() => speakText(content), 300);
         }
    }
     // Helper to render basic markdown and escape HTML
     function renderMarkdown(text) {
         if (!text) return "";
         // 1. Escape basic HTML tags to prevent injection
         let escapedText = escapeHtml(text);
         // 2. Apply Markdown formatting
         return escapedText
             .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Bold
             .replace(/\*(.*?)\*/g, '<em>$1</em>')     // Italics
             .replace(/```([\s\S]*?)```/g, (match, code) => { // Code blocks
                 const langMatch = code.match(/^(\w+)\n/);
                 const lang = langMatch ? langMatch[1] : '';
                 const codeContent = langMatch ? code.substring(langMatch[0].length) : code;
                 const copyId = `copy-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
                 // Content inside <code> is already escaped by initial escapeHtml
                 return `<div class="code-block-wrapper">
                            <button class="copy-code-button" data-copy-target-id="${copyId}" title="نسخ الكود">
                                <i class="fas fa-copy"></i> ${escapeHtml(lang)}
                            </button>
                            <pre><code id="${copyId}" class="language-${lang}">${codeContent.trim()}</code></pre>
                         </div>`;
             })
             .replace(/`(.*?)`/g, (match, code) => `<code>${code}</code>`); // Inline code (already escaped)
     }

    // Helper to create action buttons (reusable)
    function createActionButton(className, title, iconClass, onClick = null) { /* ... (same) ... */
         const button = document.createElement('button'); button.className = `icon-button ${className}`; button.title = title;
         button.innerHTML = `<i class="fas ${iconClass}"></i>`; if (onClick) button.addEventListener('click', onClick); return button;
    }
    function handleCodeCopyClick(event) { /* ... (logic moved to copyToClipboard helper) ... */
         const button = event.currentTarget;
         const targetId = button.dataset.copyTargetId;
         const codeElement = document.getElementById(targetId);
         if (codeElement) copyToClipboard(codeElement.textContent, button);
    }

    // --- Clipboard Helper ---
    function copyToClipboard(text, buttonElement = null) { /* ... (same, uses showAppError) ... */
         if (!text) return;
         navigator.clipboard.writeText(text).then(() => {
             console.log('Copied successfully');
             if (buttonElement) { /* Show success feedback */
                 const icon = buttonElement.querySelector('i'); const originalIcon = icon?.className; const originalTitle = buttonElement.title;
                 if(icon) icon.className = 'fas fa-check'; buttonElement.title = 'تم النسخ!'; buttonElement.classList.add('copied');
                 setTimeout(() => { if (icon && originalIcon) icon.className = originalIcon; buttonElement.title = originalTitle; buttonElement.classList.remove('copied'); }, 2000);
             }
         }).catch(err => {
             console.error('Failed to copy:', err); showAppError('فشل النسخ.');
             if (buttonElement) { /* Show error feedback */
                  const icon = buttonElement.querySelector('i'); const originalIcon = icon?.className; const originalTitle = buttonElement.title;
                  if(icon) icon.className = 'fas fa-times'; buttonElement.title = 'فشل النسخ'; buttonElement.classList.add('error');
                  setTimeout(() => { if (icon && originalIcon) icon.className = originalIcon; buttonElement.title = originalTitle; buttonElement.classList.remove('error'); }, 2000);
             }
         });
    }

    // --- Regenerate ---
    function createRegenerateButton() { /* ... (same) ... */
         let button = document.getElementById('regenerate-button');
         if (!button && document.getElementById('input-area')) {
             button = document.createElement('button'); button.id = 'regenerate-button';
             button.innerHTML = '<i class="fas fa-redo"></i> إعادة توليد'; button.addEventListener('click', handleRegenerate);
             document.getElementById('input-area').before(button);
         } return button;
    }
    function showRegenerateButton() { const btn = createRegenerateButton(); if(btn) btn.style.display = 'flex'; adjustInputHeight(); }
    function hideRegenerateButton() { const btn = document.getElementById('regenerate-button'); if(btn) btn.remove(); adjustInputHeight(); }
    async function handleRegenerate() { /* ... (same error handling, uses showAppError) ... */
         if (!currentConversationId || isTyping || messages.length === 0) return;
         const lastMessageIndex = messages.length - 1;
         if (messages[lastMessageIndex].role !== 'assistant') return;

         isTyping = true; hideRegenerateButton(); stopSpeaking();
         const lastBubble = messagesContainer?.querySelector('.message-bubble:last-of-type.ai-bubble');
         const lastMessageContent = messages[lastMessageIndex].content; // Store before pop

         try {
             lastBubble?.remove(); messages.pop(); addTypingIndicator();
             const historyForApi = messages.slice(-20).map(m => ({ role: m.role, content: m.content }));
             const requestBody = {
                 conversation_id: currentConversationId, model: modelSelect?.value,
                 temperature: parseFloat(temperatureSlider?.value || 0.7), max_tokens: parseInt(maxTokensInput?.value || 1024, 10)
             };
             const response = await fetch('/api/regenerate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody) });
             removeTypingIndicator();
             if (!response.ok) { // Restore previous message on failure
                 if (lastMessageContent) { addMessageToUI('assistant', lastMessageContent, false, new Date().toISOString()); messages.push({ role: 'assistant', content: lastMessageContent }); }
                 const errorData = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
                 throw new Error(errorData.error || REGENERATE_ERROR);
             }
             const data = await response.json(); const aiTimestamp = new Date().toISOString();
             addMessageToUI('assistant', data.content, false, aiTimestamp);
             messages.push({ role: 'assistant', content: data.content, created_at: aiTimestamp });
             showRegenerateButton();
         } catch (error) {
             console.error('Regenerate error:', error); removeTypingIndicator(); showAppError(error.message || REGENERATE_ERROR);
             if (messages.length > 0 && messages[messages.length - 1].role === 'assistant') showRegenerateButton(); // Show if last is (restored) AI
         } finally { isTyping = false; adjustInputHeight(); messageInput?.focus(); }
    }


    // --- Typing Indicator ---
    function addTypingIndicator() { /* ... (same) ... */
         removeTypingIndicator();
         const indicatorBubble = document.createElement('div'); indicatorBubble.className = 'message-bubble ai-bubble typing-indicator-bubble'; indicatorBubble.id = 'typing-indicator';
         indicatorBubble.innerHTML = `<div class="typing-indicator"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`;
         if (messagesContainer) { messagesContainer.appendChild(indicatorBubble); scrollToBottom(); }
    }
    function removeTypingIndicator() { document.getElementById('typing-indicator')?.remove(); }


    // --- Send Message ---
    async function sendMessage() {
        if (!messageInput || !sendButton) return; // Ensure elements exist

        const userMessage = messageInput.value.trim();
        if (!userMessage || isTyping) return;

        isTyping = true; sendButton.disabled = true; messageInput.disabled = true;
        hideRegenerateButton(); stopSpeaking();

        const userTimestamp = new Date().toISOString();
        addMessageToUI('user', userMessage, false, userTimestamp);
        messages.push({ role: 'user', content: userMessage, created_at: userTimestamp });
        messageInput.value = ''; adjustInputHeight();
        scrollToBottom();
        addTypingIndicator();

        // Check predefined
        const predefinedResponse = checkPredefinedResponse(userMessage);
        if (predefinedResponse) {
             console.log("Using predefined response.");
             setTimeout(() => { // Simulate thinking
                 removeTypingIndicator(); const aiTimestamp = new Date().toISOString();
                 addMessageToUI('assistant', predefinedResponse, false, aiTimestamp);
                 messages.push({ role: 'assistant', content: predefinedResponse, created_at: aiTimestamp });
                 isTyping = false; sendButton.disabled = false; messageInput.disabled = false; messageInput.focus();
                 showRegenerateButton();
             }, 500 + Math.random() * 500);
             return;
        }

        // Check offline
        if (!navigator.onLine) {
            console.log("Offline.");
            setTimeout(() => {
                removeTypingIndicator(); const offlineTimestamp = new Date().toISOString();
                addMessageToUI('assistant', FRONTEND_OFFLINE_MESSAGE, false, offlineTimestamp); // Show offline message
                // Do NOT add to persistent message history
                isTyping = false; sendButton.disabled = false; messageInput.disabled = false; messageInput.focus();
            }, 500);
            return;
        }

        // API Call
        try {
            const historyForApi = messages.slice(-20).map(m => ({ role: m.role, content: m.content })); // Limit history
            const requestBody = {
                history: historyForApi, conversation_id: currentConversationId,
                model: modelSelect?.value, temperature: parseFloat(temperatureSlider?.value || 0.7),
                max_tokens: parseInt(maxTokensInput?.value || 1024, 10)
            };

            const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody) });
            removeTypingIndicator();

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `خطأ HTTP ${response.status}` }));
                throw new Error(errorData.error || MESSAGE_SEND_ERROR);
            }

            const data = await response.json(); const aiTimestamp = new Date().toISOString();

            if (!currentConversationId && data.id) { // Handle new conversation creation
                currentConversationId = data.id;
                // Add to list UI without full reload
                addConversationToList({ id: data.id, title: messages[0]?.content.substring(0, 80) || "محادثة جديدة", updated_at: aiTimestamp }, true);
                document.querySelectorAll('.conversation-item').forEach(item => item.classList.toggle('active', item.dataset.conversationId === currentConversationId));
            }

            addMessageToUI('assistant', data.content, false, aiTimestamp);
            messages.push({ role: 'assistant', content: data.content, created_at: aiTimestamp });
            showRegenerateButton();

        } catch (error) {
            console.error('Send message error:', error); removeTypingIndicator();
            addMessageToUI('error', `${error.message || MESSAGE_SEND_ERROR}`); // Add error bubble
            // Show regenerate only if previous message was AI
            if (messages.length > 1 && messages[messages.length-1].role === 'user' && messages[messages.length-2]?.role === 'assistant') showRegenerateButton();
        } finally {
            isTyping = false; if(sendButton) sendButton.disabled = false; if(messageInput) messageInput.disabled = false; messageInput?.focus(); adjustInputHeight();
        }
    }

    // --- Utility Functions ---
    function scrollToBottom(instant = false) { if(messagesContainer) messagesContainer.scrollTo({ top: messagesContainer.scrollHeight, behavior: instant ? 'instant' : 'smooth' }); }
    function adjustInputHeight() { /* ... (same logic, ensure elements exist) ... */
         if (!messageInput || !messagesContainer || !document.getElementById('input-area')) return;
         messageInput.style.height = 'auto'; const scrollHeight = messageInput.scrollHeight; const maxHeight = 150;
         messageInput.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
         const inputAreaHeight = document.getElementById('input-area').offsetHeight;
         const regenerateButton = document.getElementById('regenerate-button');
         const regenerateHeight = (regenerateButton && regenerateButton.style.display !== 'none') ? regenerateButton.offsetHeight + 16 : 0;
         messagesContainer.style.paddingBottom = `${inputAreaHeight + regenerateHeight + 10}px`;
         // Adjust error message position if visible
         if (appErrorMessage && appErrorMessage.classList.contains('show')) {
             const bottomOffset = inputAreaHeight + regenerateHeight + 10; appErrorMessage.style.bottom = `${bottomOffset}px`;
         }
    }
    function toggleSidebar() { /* ... (same logic, checks elements exist) ... */
         if (!settingsSidebar || !sidebarOverlay || !document.body) return;
         isSidebarOpen = !settingsSidebar.classList.contains('show');
         settingsSidebar.classList.toggle('show', isSidebarOpen);
         sidebarOverlay.classList.toggle('show', isSidebarOpen);
         document.body.classList.toggle('sidebar-open', isSidebarOpen);
         document.body.style.overflow = isSidebarOpen && window.innerWidth <= 768 ? 'hidden' : '';
    }
    function showConfirmModal(callback) { if(!confirmModal) return; confirmationCallback = callback; confirmModal.classList.add('show'); }
    function hideConfirmModal() { if(!confirmModal) return; confirmModal.classList.remove('show'); confirmationCallback = null; }
    function formatDate(isoString) { /* ... (same) ... */
        if (!isoString) return ''; try { const date = new Date(isoString); return new Intl.DateTimeFormat('ar-SA', { year: 'numeric', month: 'short', day: 'numeric' }).format(date); } catch (e) { return ''; }
    }
    function formatTime(isoString) { /* ... (same) ... */
         if (!isoString) return ''; try { const date = new Date(isoString); return new Intl.DateTimeFormat('ar-SA', { hour: 'numeric', minute: '2-digit', hour12: true }).format(date); } catch (e) { return ''; }
    }
    function escapeHtml(unsafe = "") { /* ... (same) ... */
        if(typeof unsafe !== 'string') return '';
        return unsafe.replace(/&/g, "&").replace(/</g, "<").replace(/>/g, ">").replace(/"/g, """).replace(/'/g, "'");
    }

    // --- Event Listeners Setup ---
    function setupEventListeners() {
        console.log("Setting up event listeners...");
        // Use optional chaining and check if element exists before adding listener
        sendButton?.addEventListener('click', sendMessage);
        messageInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
            else if (e.key === 'Enter' && e.shiftKey) { setTimeout(adjustInputHeight, 0); }
        });
        messageInput?.addEventListener('input', adjustInputHeight);
        newConversationButton?.addEventListener('click', () => {
            if (isTyping) return; stopSpeaking(); clearMessages(); currentConversationId = null; messages = []; hideRegenerateButton();
            document.querySelectorAll('.conversation-item.active').forEach(item => item.classList.remove('active'));
            if (window.innerWidth <= 768 && isSidebarOpen) toggleSidebar(); messageInput?.focus();
        });
        temperatureSlider?.addEventListener('input', () => { if(temperatureValueSpan) temperatureValueSpan.textContent = temperatureSlider.value; });
        temperatureSlider?.addEventListener('change', () => { localStorage.setItem('temperature', temperatureSlider.value); });
        maxTokensInput?.addEventListener('change', () => localStorage.setItem('maxTokens', maxTokensInput.value));
        darkModeToggle?.addEventListener('change', () => {
            document.body.classList.toggle('dark-mode', darkModeToggle.checked);
            localStorage.setItem('darkModeEnabled', darkModeToggle.checked);
        });
        toggleSidebarButton?.addEventListener('click', toggleSidebar); // Desktop toggle
        mobileMenuButton?.addEventListener('click', toggleSidebar);    // Mobile menu button
        mobileSettingsButton?.addEventListener('click', toggleSidebar); // Mobile settings button in footer
        closeSidebarButton?.addEventListener('click', toggleSidebar);   // Mobile close button in sidebar
        sidebarOverlay?.addEventListener('click', toggleSidebar);     // Mobile overlay click

        confirmOkButton?.addEventListener('click', () => { if (confirmationCallback) confirmationCallback(); hideConfirmModal(); });
        confirmCancelButton?.addEventListener('click', hideConfirmModal);
        window.addEventListener('online', () => offlineIndicator?.classList.remove('visible'));
        window.addEventListener('offline', () => offlineIndicator?.classList.add('visible'));
        window.addEventListener('resize', adjustInputHeight); // Adjust layout on resize
        console.log("Event listeners setup complete.");
    }

    // --- Initialization ---
    function initializeApp() {
        console.log("Initializing dzteck Chat App v2.1...");
        // Load settings
        try {
            const savedTemp = localStorage.getItem('temperature');
            if (savedTemp && temperatureSlider && temperatureValueSpan) { temperatureSlider.value = savedTemp; temperatureValueSpan.textContent = savedTemp; }
            const savedTokens = localStorage.getItem('maxTokens');
            if (savedTokens && maxTokensInput) maxTokensInput.value = savedTokens;
            const savedDarkMode = localStorage.getItem('darkModeEnabled');
            if(darkModeToggle) darkModeToggle.checked = savedDarkMode === 'true';
            document.body.classList.toggle('dark-mode', darkModeToggle?.checked || false);
        } catch (e) {
            console.error("Error loading settings from localStorage:", e);
        }

        // Check network
        if (!navigator.onLine && offlineIndicator) offlineIndicator.classList.add('visible');

        setupEventListeners(); // Attach listeners
        clearMessages();     // Setup initial UI
        loadConversations(); // Fetch conversations
        adjustInputHeight(); // Initial layout calculation
        messageInput?.focus();
        console.log("App Initialized.");
    }

    // --- Run Initialization ---
    try {
        initializeApp();
    } catch (error) {
        console.error("CRITICAL ERROR during app initialization:", error);
        // Display a user-friendly message if possible
        const body = document.body;
        if (body) {
             body.innerHTML = '<div style="padding: 20px; text-align: center; font-family: sans-serif; color: red;">حدث خطأ فادح أثناء تحميل التطبيق. يرجى المحاولة مرة أخرى لاحقاً.</div>';
        }
    }

}); // End DOMContentLoaded
--- END OF FILE app.js ---

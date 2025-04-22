--- START OF FILE app.js ---

// Ensure the DOM is fully loaded before running the script
document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const settingsSidebar = document.getElementById('settings-sidebar');
    const toggleSidebarButton = document.getElementById('toggle-sidebar'); // Desktop toggle
    const closeSidebarButton = document.getElementById('close-sidebar'); // Mobile close
    const mobileMenuButton = document.getElementById('mobile-menu'); // Mobile open
    const mobileSettingsButton = document.getElementById('mobile-settings'); // Mobile open from footer
    const sidebarOverlay = document.getElementById('sidebar-overlay'); // Mobile overlay
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
    const appErrorMessage = document.getElementById('app-error-message'); // Global error display
    const confirmModal = document.getElementById('confirm-modal');
    const confirmMessage = document.getElementById('confirm-message');
    const confirmOkButton = document.getElementById('confirm-ok');
    const confirmCancelButton = document.getElementById('confirm-cancel');
    const ttsToggle = document.getElementById('tts-toggle');
    const micButton = document.getElementById('mic-button');

    // --- State Variables ---
    let currentConversationId = null;
    let messages = []; // Stores current conversation messages {role: 'user'/'assistant', content: '...', id: ..., created_at: ...}
    let isTyping = false; // To prevent multiple requests or show typing indicator
    let confirmationCallback = null; // Function to call after modal confirmation
    let appErrorTimeout = null; // Timeout ID for hiding the global error message

    // --- Constants ---
    // Updated Welcome Message Content
    const WELCOME_MESSAGE_CONTENT = "السلام عليكم! أنا مساعد dzteck الرقمي. كيف يمكنني مساعدتك اليوم؟";
    const FRONTEND_OFFLINE_MESSAGE = "أعتذر، لا يوجد اتصال بالإنترنت حاليًا. لا يمكنني معالجة طلبك الآن.";
    const GENERAL_ERROR_MESSAGE = "حدث خطأ ما. يرجى المحاولة مرة أخرى لاحقاً.";
    const CONVERSATION_LOAD_ERROR = "فشل تحميل المحادثات.";
    const MESSAGE_SEND_ERROR = "فشل إرسال الرسالة.";
    const REGENERATE_ERROR = "فشل إعادة توليد الرد.";

    // --- Updated and Expanded Predefined Responses ---
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

        // Add more specific phrases or questions relevant to dzteck or common user queries
    };

    // --- Helper function to check for predefined responses ---
    function checkPredefinedResponse(userMessage) {
        const cleanedMessage = userMessage.toLowerCase().replace(/[?؟!,.\s\u064B-\u065F\u0640]+/g, ' ').trim(); // Added Kashida removal
        const normalizedMessage = cleanedMessage
            .replace(/أ|إ|آ/g, 'ا') // Normalize Alif
            .replace(/ى/g, 'ي') // Normalize Alef Maksura
            .replace(/ة/g, 'ه'); // Normalize Teh Marbuta

        for (const key in PREDEFINED_RESPONSES) {
            const normalizedKey = key.toLowerCase()
                .replace(/[?؟!,.\s\u064B-\u065F\u0640]+/g, ' ')
                .trim()
                .replace(/أ|إ|آ/g, 'ا')
                .replace(/ى/g, 'ي')
                .replace(/ة/g, 'ه');

            // Check for exact match or starting phrase match
            if (normalizedMessage === normalizedKey || (normalizedKey.length > 2 && normalizedMessage.startsWith(normalizedKey + ' '))) { // Check length > 2 to avoid matching 'ما' alone etc.
                return PREDEFINED_RESPONSES[key];
            }
        }
        return null; // No predefined response found
    }

    // --- Speech Recognition (STT) ---
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let isRecording = false;

    if (SpeechRecognition && micButton) { // Ensure micButton exists
        recognition = new SpeechRecognition();
        recognition.lang = 'ar-SA'; // Or another Arabic dialect like 'ar-EG'
        recognition.continuous = false;
        recognition.interimResults = true; // Get results as they come

        recognition.onstart = () => {
            console.log('STT started');
            isRecording = true;
            micButton.classList.add('recording');
            micButton.title = 'إيقاف التسجيل الصوتي';
            messageInput.placeholder = 'استمع... تحدث الآن...';
        };

        recognition.onresult = (event) => {
            let interimTranscript = '';
            let finalTranscript = '';
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                } else {
                    interimTranscript += event.results[i][0].transcript;
                }
            }
            // Append final transcript, adding space if needed
            if (finalTranscript) {
                const currentVal = messageInput.value;
                messageInput.value = (currentVal && !currentVal.match(/[\s\n]$/) ? currentVal + ' ' : currentVal) + finalTranscript;
                adjustInputHeight();
            }
             // Optionally display interim results in placeholder (can be distracting)
             // else if (interimTranscript) { messageInput.placeholder = `...${interimTranscript}...`; }
        };

        recognition.onerror = (event) => {
            console.error('STT Error:', event.error, event.message);
            isRecording = false;
            micButton.classList.remove('recording');
            micButton.title = 'إدخال صوتي';
            messageInput.placeholder = 'اكتب رسالتك هنا...';
            let userMessage = 'حدث خطأ في التعرف على الصوت.';
            if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                userMessage = 'تم رفض الوصول إلى الميكروفون. يرجى السماح للموقع بالوصول من إعدادات المتصفح.';
            } else if (event.error === 'no-speech') {
                userMessage = 'لم يتم الكشف عن صوت. يرجى التحدث بوضوح.';
            } else if (event.error === 'audio-capture') {
                userMessage = 'فشل التقاط الصوت. تأكد من توصيل وعمل الميكروفون.';
            } else if (event.error === 'network') {
                userMessage = 'مشكلة في الشبكة أثناء التعرف الصوتي.';
            }
            showAppError(userMessage);
        };

        recognition.onend = () => {
            console.log('STT ended');
            isRecording = false;
            micButton.classList.remove('recording');
            micButton.title = 'إدخال صوتي';
            messageInput.placeholder = 'اكتب رسالتك هنا...';
            messageInput.focus(); // Keep focus after recording
        };

        micButton.addEventListener('click', () => {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                showAppError('المتصفح لا يدعم الوصول إلى الميكروفون.');
                return;
            }
            // Check permission status (best effort)
            navigator.permissions?.query({ name: 'microphone' }).then(permissionStatus => {
                if (permissionStatus.state === 'denied') {
                    showAppError('تم رفض الوصول إلى الميكروفون سابقاً. يرجى تمكينه من إعدادات المتصفح.');
                    return;
                }
                // Proceed with starting/stopping
                if (isRecording) {
                    recognition.stop();
                } else {
                    try {
                        messageInput.value = ''; // Clear input before starting voice input
                        recognition.start();
                    } catch (e) {
                        console.error("Error starting STT:", e);
                        showAppError('لم يتمكن من بدء التعرف على الصوت. تأكد من أن الميكروفون متاح.');
                        isRecording = false; // Reset state
                        micButton.classList.remove('recording');
                        micButton.title = 'إدخال صوتي';
                        messageInput.placeholder = 'اكتب رسالتك هنا...';
                    }
                }
            }).catch(err => {
                console.warn("Microphone permission query failed, proceeding cautiously:", err);
                // Fallback if permission query fails
                if (isRecording) {
                    recognition.stop();
                } else {
                     try {
                          messageInput.value = '';
                          recognition.start();
                     } catch (e) {
                          console.error("Error starting STT (fallback):", e);
                          showAppError('لم يتمكن من بدء التعرف على الصوت.');
                     }
                }
            });
        });

    } else {
        console.warn('Web Speech API (SpeechRecognition) not supported.');
        if (micButton) micButton.style.display = 'none'; // Hide button if not supported
    }

    // --- Speech Synthesis (TTS) ---
    const SpeechSynthesis = window.speechSynthesis;
    let availableVoices = [];
    let speakingUtterance = null;

    function loadVoices() {
        if (!SpeechSynthesis) return;
        availableVoices = SpeechSynthesis.getVoices();
        const arabicVoices = availableVoices.filter(v => v.lang.startsWith('ar'));
        console.log(`${availableVoices.length} voices loaded, ${arabicVoices.length} Arabic voices found.`);
        if (arabicVoices.length === 0) {
             console.warn('No native Arabic voices found in browser for TTS.');
        }
    }

    function speakText(text, buttonElement = null) {
        if (!SpeechSynthesis || !text) return false;
        if (availableVoices.length === 0) loadVoices(); // Ensure voices are loaded

        stopSpeaking(); // Stop previous speech

        try {
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'ar'; // Set language hint
            utterance.rate = 0.9;  // Slightly slower can be clearer
            utterance.pitch = 1.0;
            utterance.volume = 1.0;

            // Voice selection logic (prioritize female voices, then Saudi, then any Arabic)
            let selectedVoice = availableVoices.find(v => v.lang === 'ar-SA' && /female/i.test(v.name)) ||
                                availableVoices.find(v => v.lang === 'ar-SA') ||
                                availableVoices.find(v => v.lang.startsWith('ar-') && /female/i.test(v.name)) ||
                                availableVoices.find(v => v.lang.startsWith('ar-')) ||
                                availableVoices.find(v => v.lang.includes('ar')) ||
                                availableVoices.find(v => v.default && v.lang.startsWith('ar')) ||
                                availableVoices.find(v => v.default); // Fallback to any default

            if (selectedVoice) {
                utterance.voice = selectedVoice;
                console.log('TTS using voice:', selectedVoice.name, `(${selectedVoice.lang})`);
            } else {
                console.warn('No suitable Arabic voice found, using browser default.');
            }

            const icon = buttonElement?.querySelector('i');
            const originalClass = icon?.className;

            utterance.onstart = () => {
                speakingUtterance = utterance;
                if (icon) icon.className = 'fas fa-volume-high speaking'; // Indicate speaking
                console.log('TTS started');
            };
            utterance.onend = () => {
                speakingUtterance = null;
                if (icon && originalClass) icon.className = originalClass; // Reset icon
                console.log('TTS ended');
            };
            utterance.onerror = (event) => {
                console.error('TTS error:', event.error);
                speakingUtterance = null;
                if (icon && originalClass) icon.className = originalClass; // Reset icon
                showAppError(`خطأ في نطق النص: ${event.error}`);
            };

            SpeechSynthesis.speak(utterance);
            return true;
        } catch (err) {
            console.error('Error initializing TTS:', err);
            showAppError('حدث خطأ أثناء محاولة نطق النص.');
            return false;
        }
    }

    function stopSpeaking() {
        if (SpeechSynthesis && SpeechSynthesis.speaking) {
            SpeechSynthesis.cancel(); // Stop speech
            speakingUtterance = null;
            // Reset any icons that were in the 'speaking' state
            document.querySelectorAll('.speak-btn i.speaking').forEach(icon => {
                 if (icon.classList.contains('fa-volume-high')) { // Check if it's the speaking icon
                     icon.className = 'fas fa-volume-up'; // Reset to default volume icon
                 }
            });
            console.log('TTS stopped.');
        }
    }

    if (SpeechSynthesis) {
        if (SpeechSynthesis.onvoiceschanged !== undefined) {
            SpeechSynthesis.onvoiceschanged = loadVoices;
        }
        loadVoices(); // Initial load attempt

        // Event delegation for speak buttons click
        messagesContainer.addEventListener('click', (event) => {
            const speakButton = event.target.closest('.speak-btn');
            if (!speakButton) return; // Exit if not a speak button

            const messageBubble = speakButton.closest('.message-bubble');
            const textElement = messageBubble?.querySelector('p');
            if (!textElement?.textContent) return; // Exit if no text found

            // If clicking the button of the currently speaking utterance, stop it. Otherwise, speak the new text.
            if (speakingUtterance && speakingUtterance.text === textElement.textContent && SpeechSynthesis.speaking) {
                stopSpeaking();
            } else {
                speakText(textElement.textContent, speakButton);
            }
        });

        // TTS Toggle initial state and listener
        const storedTtsPreference = localStorage.getItem('ttsEnabled');
        ttsToggle.checked = storedTtsPreference === 'true'; // Set initial state from storage
        ttsToggle.addEventListener('change', () => {
            localStorage.setItem('ttsEnabled', ttsToggle.checked); // Save preference
            if (!ttsToggle.checked) {
                stopSpeaking(); // Stop speaking if toggled off
            }
        });

    } else {
        console.warn('Web Speech API (SpeechSynthesis) not supported.');
        if (ttsToggle) ttsToggle.closest('.setting-item').style.display = 'none'; // Hide TTS setting if not supported
    }

    // --- Initialize Models Dropdown ---
    const availableModels = [
        { value: 'mistralai/mistral-7b-instruct', label: 'Mistral 7B' },
        { value: 'anthropic/claude-3-haiku', label: 'Claude 3 Haiku' },
        { value: 'google/gemini-pro', label: 'Gemini Pro' },
        { value: 'meta-llama/llama-3-8b-instruct', label: 'LLaMA 3 8B' },
        { value: 'google/gemma-7b-it', label: 'Gemma 7B' },
        { value: 'openai/gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
        { value: 'anthropic/claude-3-sonnet', label: 'Claude 3 Sonnet' }
    ];
    modelSelect.innerHTML = ''; // Clear existing options
    availableModels.forEach(model => {
        const option = document.createElement('option');
        option.value = model.value;
        option.textContent = model.label;
        modelSelect.appendChild(option);
    });
    // Load saved model or default to the first one
    const savedModel = localStorage.getItem('selectedModel');
    if (savedModel && availableModels.some(model => model.value === savedModel)) {
        modelSelect.value = savedModel;
    } else if (availableModels.length > 0) {
         modelSelect.value = availableModels[0].value; // Default to first if saved not found
    }
    modelSelect.addEventListener('change', () => { localStorage.setItem('selectedModel', modelSelect.value); });

    // --- Global Error Display ---
    function showAppError(message, duration = 5000) {
        if (appErrorTimeout) clearTimeout(appErrorTimeout); // Clear previous error timeout

        appErrorMessage.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}`; // Set message with icon
        appErrorMessage.classList.add('show'); // Make it visible

        // Dynamically adjust bottom position based on input area and potential regenerate button
        const inputArea = document.getElementById('input-area');
        const regenerateButton = document.getElementById('regenerate-button');
        let bottomOffset = 15; // Default spacing from bottom edge

        if (inputArea) {
             bottomOffset += inputArea.offsetHeight;
        }
        if (regenerateButton && regenerateButton.style.display !== 'none') {
             bottomOffset += regenerateButton.offsetHeight + 16; // Add button height and its margin
        }

        appErrorMessage.style.bottom = `${bottomOffset}px`;

        // Set timeout to hide the error message
        appErrorTimeout = setTimeout(() => {
            appErrorMessage.classList.remove('show');
        }, duration);
    }

    // --- Conversation Management ---
    async function loadConversations(showLoading = true) {
         if (showLoading) {
              conversationsList.innerHTML = '<div class="empty-state loading-conversations"><i class="fas fa-spinner fa-spin"></i> جارٍ تحميل المحادثات...</div>';
         }
        try {
            const response = await fetch('/api/conversations');
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
            const conversations = await response.json();
            displayConversations(conversations);
        } catch (error) {
            console.error('Error loading conversations:', error);
            conversationsList.innerHTML = `<div class="empty-state error"><i class="fas fa-exclamation-triangle"></i> ${CONVERSATION_LOAD_ERROR}</div>`;
            // Don't show global error for initial load failure, only list error
        }
    }

    function displayConversations(conversations) {
        conversationsList.innerHTML = ''; // Clear previous
        if (!conversations || conversations.length === 0) {
            conversationsList.innerHTML = '<div class="empty-state"><i class="fas fa-comments"></i> لا توجد محادثات سابقة</div>';
            return;
        }
        conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            item.dataset.conversationId = conv.id;
            if (conv.id === currentConversationId) item.classList.add('active');

            const titleSpan = document.createElement('span');
            titleSpan.textContent = conv.title || "محادثة بدون عنوان";
            titleSpan.title = `${titleSpan.textContent}\nآخر تحديث: ${formatDate(conv.updated_at)}`;

            const actionsDiv = createConversationActions(conv.id, conv.title);

            item.appendChild(titleSpan); // Title first in DOM for text flow
            item.appendChild(actionsDiv); // Actions last
            item.addEventListener('click', () => handleConversationClick(conv.id, item));
            conversationsList.appendChild(item);
        });
    }

    function createConversationActions(id, title) {
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'conversation-actions';
        // Edit Button
        actionsDiv.appendChild(createActionButton('edit-conv-btn', 'تعديل العنوان', 'fa-edit', (e) => {
            e.stopPropagation(); editConversationTitle(id, title);
        }));
        // Delete Button
        actionsDiv.appendChild(createActionButton('delete-conv-btn', 'حذف المحادثة', 'fa-trash-alt', (e) => {
            e.stopPropagation(); confirmDeleteConversation(id);
        }));
        return actionsDiv;
    }

    function handleConversationClick(id, itemElement) {
        if (id === currentConversationId || isTyping) return; // Prevent action if busy or already active

        // Indicate loading on the clicked item
        document.querySelectorAll('.conversation-item.loading').forEach(el => el.classList.remove('loading'));
        itemElement?.classList.add('loading');

        loadConversation(id).finally(() => {
             itemElement?.classList.remove('loading'); // Always remove loading state
        });
    }

    async function loadConversation(conversationId) {
        stopSpeaking(); // Stop TTS
        messagesContainer.innerHTML = '<div class="empty-state loading-messages"><i class="fas fa-spinner fa-spin"></i> جارٍ تحميل الرسائل...</div>';
        hideRegenerateButton();

        try {
            const response = await fetch(`/api/conversations/${conversationId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
            const conversation = await response.json();

            clearMessages(false); // Clear UI without welcome message
            currentConversationId = conversationId;
            messages = conversation.messages.map(msg => ({ ...msg })); // Shallow copy message objects

            if (messages.length > 0) {
                 messages.forEach(msg => addMessageToUI(msg.role, msg.content, false, msg.created_at, msg.id));
            } else {
                 messagesContainer.innerHTML = '<div class="empty-state"><i class="fas fa-comment-dots"></i> ابدأ هذه المحادثة بإرسال رسالة.</div>';
            }

            // Update active state in list
            document.querySelectorAll('.conversation-item').forEach(item => {
                item.classList.toggle('active', item.dataset.conversationId === conversationId);
            });

            // Close sidebar on mobile if open
            if (window.innerWidth <= 768 && settingsSidebar.classList.contains('show')) {
                toggleSidebar();
            }

            scrollToBottom(true); // Force scroll

            // Show regenerate button if appropriate
            if (messages.length > 0 && messages[messages.length - 1].role === 'assistant') {
                showRegenerateButton();
            } else {
                hideRegenerateButton();
            }
        } catch (error) {
            console.error('Error loading conversation:', error);
            messagesContainer.innerHTML = `<div class="empty-state error"><i class="fas fa-exclamation-triangle"></i> فشل تحميل المحادثة.</div>`;
            showAppError('فشل تحميل المحادثة.');
            currentConversationId = null; // Reset ID
            document.querySelectorAll('.conversation-item.active').forEach(item => item.classList.remove('active'));
        }
    }

    function editConversationTitle(id, currentTitle) {
        const newTitle = prompt('أدخل العنوان الجديد للمحادثة:', currentTitle);
        if (newTitle && newTitle.trim() && newTitle.trim() !== currentTitle) {
            updateConversationTitle(id, newTitle.trim());
        }
    }

    async function updateConversationTitle(id, newTitle) {
        const item = conversationsList.querySelector(`.conversation-item[data-conversation-id="${id}"]`);
        item?.classList.add('loading');
        try {
            const response = await fetch(`/api/conversations/${id}/title`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle }),
            });
            if (!response.ok) throw new Error('Failed to update title');
            const titleSpan = item?.querySelector('span');
            if (titleSpan) {
                 titleSpan.textContent = newTitle;
                 titleSpan.title = `${newTitle}\nآخر تحديث: ${formatDate(new Date().toISOString())}`; // Update title attribute too
            }
        } catch (error) {
            console.error('Error updating title:', error);
            showAppError('فشل تحديث عنوان المحادثة.');
        } finally {
            item?.classList.remove('loading');
        }
    }

    function confirmDeleteConversation(id) {
        confirmMessage.textContent = 'هل أنت متأكد من أنك تريد حذف هذه المحادثة نهائياً؟ لا يمكن التراجع عن هذا الإجراء.';
        showConfirmModal(() => deleteConversation(id));
    }

    async function deleteConversation(id) {
        const item = conversationsList.querySelector(`.conversation-item[data-conversation-id="${id}"]`);
        item?.classList.add('loading');
        try {
            const response = await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
            if (!response.ok) throw new Error('Failed to delete');

            if (id === currentConversationId) {
                clearMessages(); // Reset chat area
                currentConversationId = null;
                messages = [];
            }
            item?.remove(); // Remove from list
            if (conversationsList.children.length === 0) {
                 conversationsList.innerHTML = '<div class="empty-state"><i class="fas fa-comments"></i> لا توجد محادثات سابقة</div>';
            }
        } catch (error) {
            console.error('Error deleting conversation:', error);
            showAppError('فشل حذف المحادثة.');
            item?.classList.remove('loading');
        }
    }

    // --- Message UI Handling ---
    function clearMessages(addWelcome = true) {
        messagesContainer.innerHTML = '';
        hideRegenerateButton();
        if (addWelcome) {
            addMessageToUI('assistant', WELCOME_MESSAGE_CONTENT, true, new Date().toISOString());
        }
    }

    function addMessageToUI(role, content, isInitialWelcome = false, timestamp = null, messageId = null) {
        const emptyState = messagesContainer.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const bubble = document.createElement('div');
        bubble.className = `message-bubble ${role}-bubble fade-in`; // Use role directly in class
        if (role === 'error') bubble.classList.add('error-bubble'); // Specific class for errors
        if (messageId) bubble.dataset.messageId = messageId;

        const p = document.createElement('p');
        if (role === 'error') {
             // Add icon to error message content
             p.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${escapeHtml(content)}`;
        } else {
             // Render Markdown for non-error messages
             p.innerHTML = content
                 .replace(/&/g, "&").replace(/</g, "<").replace(/>/g, ">") // Basic HTML escape first
                 .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                 .replace(/\*(.*?)\*/g, '<em>$1</em>')
                 .replace(/```([\s\S]*?)```/g, (match, code) => {
                     const langMatch = code.match(/^(\w+)\n/);
                     const lang = langMatch ? langMatch[1] : '';
                     const codeContent = langMatch ? code.substring(langMatch[0].length) : code;
                     const copyId = `copy-${messageId || Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
                     // Note: Using escapeHtml on codeContent *before* putting it in <code>
                     return `<div class="code-block-wrapper">
                                <button class="copy-code-button" data-copy-target-id="${copyId}" title="نسخ الكود">
                                    <i class="fas fa-copy"></i> ${escapeHtml(lang)}
                                </button>
                                <pre><code id="${copyId}" class="language-${lang}">${escapeHtml(codeContent.trim())}</code></pre>
                             </div>`;
                  })
                 .replace(/`(.*?)`/g, (match, code) => `<code>${escapeHtml(code)}</code>`); // Escape inline code too
        }
        bubble.appendChild(p);

        // Add Timestamp
        if (timestamp && role !== 'error') {
            const timeDiv = document.createElement('div');
            timeDiv.className = 'message-timestamp';
            timeDiv.textContent = formatTime(timestamp);
            bubble.appendChild(timeDiv);
        }

        // Add Actions (only for non-error messages)
        if (role === 'assistant') {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'message-actions';
            actionsDiv.appendChild(createActionButton('copy-btn', 'نسخ الرد', 'fa-copy', () => copyToClipboard(content, actionsDiv.querySelector('.copy-btn'))));
            if (SpeechSynthesis) {
                 actionsDiv.appendChild(createActionButton('speak-btn', 'استماع إلى الرد', 'fa-volume-up'));
            }
            // Placeholder for vote buttons if implemented later
            // actionsDiv.appendChild(createVoteButtons(messageId));
            bubble.appendChild(actionsDiv);

             // Auto-TTS (if enabled and not the initial welcome)
             if (!isInitialWelcome && ttsToggle?.checked && typeof speakText === 'function') {
                  setTimeout(() => speakText(content), 300);
             }

        } else if (role === 'user') {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'message-actions';
            actionsDiv.appendChild(createActionButton('copy-btn', 'نسخ الرسالة', 'fa-copy', () => copyToClipboard(content, actionsDiv.querySelector('.copy-btn'))));
            bubble.appendChild(actionsDiv);
        }

        messagesContainer.appendChild(bubble);

        // Add code copy listeners for any new code blocks
        bubble.querySelectorAll('.copy-code-button').forEach(button => {
             button.addEventListener('click', () => {
                 const targetId = button.dataset.copyTargetId;
                 const codeElement = document.getElementById(targetId);
                 if (codeElement) {
                     copyToClipboard(codeElement.textContent, button);
                 }
             });
        });

        if (!isInitialWelcome) {
            scrollToBottom();
        }
    }

    // Helper to create action buttons
    function createActionButton(className, title, iconClass, onClick = null) {
        const button = document.createElement('button');
        button.className = `icon-button ${className}`; // Use icon-button base class
        button.title = title;
        button.innerHTML = `<i class="fas ${iconClass}"></i>`;
        if (onClick) {
            button.addEventListener('click', onClick);
        }
        return button;
    }

    // --- Copy to Clipboard Helper ---
    function copyToClipboard(text, buttonElement = null) {
        navigator.clipboard.writeText(text).then(() => {
            if (buttonElement) {
                const icon = buttonElement.querySelector('i');
                const originalIcon = icon?.className;
                const originalTitle = buttonElement.title;
                if (icon) icon.className = 'fas fa-check';
                buttonElement.title = 'تم النسخ!';
                buttonElement.classList.add('copied'); // Add class for potential styling
                setTimeout(() => {
                    if (icon && originalIcon) icon.className = originalIcon;
                    buttonElement.title = originalTitle;
                    buttonElement.classList.remove('copied');
                }, 2000);
            }
            console.log('Text copied');
        }).catch(err => {
            console.error('Failed to copy text:', err);
            if (buttonElement) {
                 const icon = buttonElement.querySelector('i');
                 const originalIcon = icon?.className;
                 const originalTitle = buttonElement.title;
                 if (icon) icon.className = 'fas fa-times';
                 buttonElement.title = 'فشل النسخ';
                 buttonElement.classList.add('error');
                 setTimeout(() => {
                     if (icon && originalIcon) icon.className = originalIcon;
                     buttonElement.title = originalTitle;
                     buttonElement.classList.remove('error');
                 }, 2000);
            }
            showAppError('فشل نسخ النص.');
        });
    }

    // --- Regenerate Button ---
    function createRegenerateButton() {
        let button = document.getElementById('regenerate-button');
        if (!button) {
            button = document.createElement('button');
            button.id = 'regenerate-button';
            button.innerHTML = '<i class="fas fa-redo"></i> إعادة توليد الرد';
            button.addEventListener('click', handleRegenerate);
            document.getElementById('input-area').before(button); // Insert before input area
        }
        return button;
    }
    function showRegenerateButton() { createRegenerateButton().style.display = 'flex'; adjustInputHeight(); } // Adjust layout after showing
    function hideRegenerateButton() { document.getElementById('regenerate-button')?.remove(); adjustInputHeight(); } // Adjust layout after hiding


    // --- Handle Regenerate ---
    async function handleRegenerate() {
        if (!currentConversationId || isTyping || messages.length === 0) return;

        const lastMessageIndex = messages.length - 1;
        if (messages[lastMessageIndex].role !== 'assistant') return;

        isTyping = true;
        hideRegenerateButton();
        stopSpeaking();

        // Find the DOM element of the last AI message to potentially restore it on error
        const lastBubble = messagesContainer.querySelector('.message-bubble:last-of-type.ai-bubble');
        const lastMessageContent = messages[lastMessageIndex].content; // Store content before popping

        try {
            lastBubble?.remove(); // Remove from UI
            messages.pop(); // Remove from state
            addTypingIndicator();

            const requestBody = { /* ... same as before ... */ };

            const response = await fetch('/api/regenerate', { /* ... same as before ... */ });

            removeTypingIndicator();

            if (!response.ok) {
                // Restore previous message on failure
                if (lastMessageContent) {
                    addMessageToUI('assistant', lastMessageContent, false, new Date().toISOString()); // Re-add the old message visually
                    messages.push({ role: 'assistant', content: lastMessageContent }); // Add back to state
                }
                const errorData = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
                throw new Error(errorData.error || REGENERATE_ERROR);
            }

            const data = await response.json();
            addMessageToUI('assistant', data.content, false, new Date().toISOString()); // Add new message
            messages.push({ role: 'assistant', content: data.content });
            showRegenerateButton();

        } catch (error) {
            console.error('Error regenerating:', error);
            removeTypingIndicator();
            showAppError(error.message || REGENERATE_ERROR);
            // Show regenerate button again only if the (restored) last message is AI
            if (messages.length > 0 && messages[messages.length - 1].role === 'assistant') {
                 showRegenerateButton();
            }
        } finally {
            isTyping = false;
            adjustInputHeight(); // Adjust layout
        }
    }


    // --- Typing Indicator ---
    function addTypingIndicator() {
        removeTypingIndicator(); // Ensure only one exists
        const indicatorBubble = document.createElement('div');
        indicatorBubble.className = 'message-bubble ai-bubble typing-indicator-bubble';
        indicatorBubble.id = 'typing-indicator';
        indicatorBubble.innerHTML = `<div class="typing-indicator"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`;
        messagesContainer.appendChild(indicatorBubble);
        scrollToBottom();
    }
    function removeTypingIndicator() { document.getElementById('typing-indicator')?.remove(); }

    // --- Send Message Logic ---
    async function sendMessage() {
        const userMessage = messageInput.value.trim();
        if (!userMessage || isTyping) return;

        isTyping = true;
        sendButton.disabled = true;
        messageInput.disabled = true;
        hideRegenerateButton();
        stopSpeaking();

        // Add user message optimistically
        const userTimestamp = new Date().toISOString();
        addMessageToUI('user', userMessage, false, userTimestamp);
        messages.push({ role: 'user', content: userMessage, created_at: userTimestamp }); // Add to state
        messageInput.value = '';
        adjustInputHeight();
        scrollToBottom(); // Scroll after adding user message
        addTypingIndicator();

        // Check predefined AFTER showing user message
        const predefinedResponse = checkPredefinedResponse(userMessage);
        if (predefinedResponse) {
            console.log("Using predefined response:", predefinedResponse);
            setTimeout(() => { // Delay slightly for realism
                removeTypingIndicator();
                const aiTimestamp = new Date().toISOString();
                addMessageToUI('assistant', predefinedResponse, false, aiTimestamp);
                messages.push({ role: 'assistant', content: predefinedResponse, created_at: aiTimestamp });
                isTyping = false;
                sendButton.disabled = false;
                messageInput.disabled = false;
                messageInput.focus();
                showRegenerateButton();
                 // Optionally sync with backend here
                 // syncPredefinedMessages(currentConversationId, userMessage, predefinedResponse);
            }, 500 + Math.random() * 500); // Random delay 0.5s-1s
            return;
        }

        // Check offline AFTER showing user message
        if (!navigator.onLine) {
            console.log("Offline detected.");
            setTimeout(() => { // Delay offline message too
                removeTypingIndicator();
                const offlineTimestamp = new Date().toISOString();
                addMessageToUI('assistant', FRONTEND_OFFLINE_MESSAGE, false, offlineTimestamp);
                // Do NOT add frontend offline message to persistent 'messages' state
                isTyping = false;
                sendButton.disabled = false;
                messageInput.disabled = false;
                messageInput.focus();
                // No regenerate for offline message
            }, 500);
            return;
        }

        // Proceed with API call
        try {
            // Limit history sent to API (e.g., last 10 messages) to manage token usage
            const historyForApi = messages.slice(-10).map(m => ({ role: m.role, content: m.content }));

            const requestBody = {
                history: historyForApi,
                conversation_id: currentConversationId,
                model: modelSelect.value,
                temperature: parseFloat(temperatureSlider.value),
                max_tokens: parseInt(maxTokensInput.value, 10)
            };

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
            });

            removeTypingIndicator();

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
                throw new Error(errorData.error || MESSAGE_SEND_ERROR);
            }

            const data = await response.json();
            const aiTimestamp = new Date().toISOString();

            if (!currentConversationId && data.id) {
                currentConversationId = data.id;
                // Add conversation to list without full reload if possible
                addConversationToList({ id: data.id, title: messages[0]?.content.substring(0, 80) || "محادثة جديدة", updated_at: aiTimestamp });
                // Mark new conversation as active
                 document.querySelectorAll('.conversation-item').forEach(item => {
                     item.classList.toggle('active', item.dataset.conversationId === currentConversationId);
                 });
            }

            addMessageToUI('assistant', data.content, false, aiTimestamp);
            messages.push({ role: 'assistant', content: data.content, created_at: aiTimestamp });
            showRegenerateButton();

        } catch (error) {
            console.error('Error sending message:', error);
            removeTypingIndicator();
            addMessageToUI('error', `${error.message || MESSAGE_SEND_ERROR}`); // Show error bubble
            // Don't show global error for send errors, bubble is enough
            // Decide if regenerate should be shown - only if previous AI msg exists
            if (messages.length > 1 && messages[messages.length-1].role === 'user' && messages[messages.length-2].role === 'assistant') {
                 showRegenerateButton();
            }
        } finally {
            isTyping = false;
            sendButton.disabled = false;
            messageInput.disabled = false;
            messageInput.focus();
            adjustInputHeight(); // Adjust layout after response/error
        }
    }

    // Helper to add a single conversation item to the list UI
    function addConversationToList(conv) {
        const emptyState = conversationsList.querySelector('.empty-state');
        if (emptyState) emptyState.remove(); // Remove empty state if adding first item

        const item = document.createElement('div');
        item.className = 'conversation-item';
        item.dataset.conversationId = conv.id;

        const titleSpan = document.createElement('span');
        titleSpan.textContent = conv.title || "محادثة بدون عنوان";
        titleSpan.title = `${titleSpan.textContent}\nآخر تحديث: ${formatDate(conv.updated_at)}`;

        const actionsDiv = createConversationActions(conv.id, conv.title);

        item.appendChild(titleSpan);
        item.appendChild(actionsDiv);
        item.addEventListener('click', () => handleConversationClick(conv.id, item));

        // Insert at the top of the list
        conversationsList.insertBefore(item, conversationsList.firstChild);
    }


    // --- Utility Functions ---
    function scrollToBottom(instant = false) {
         messagesContainer.scrollTo({ top: messagesContainer.scrollHeight, behavior: instant ? 'instant' : 'smooth' });
    }

    function adjustInputHeight() {
        messageInput.style.height = 'auto';
        const scrollHeight = messageInput.scrollHeight;
        const maxHeight = 150; // Max height in pixels from CSS
        messageInput.style.height = `${Math.min(scrollHeight, maxHeight)}px`;

        // Adjust message container padding dynamically
        const inputAreaHeight = document.getElementById('input-area')?.offsetHeight || 70; // Estimate height
        const regenerateButton = document.getElementById('regenerate-button');
        const regenerateHeight = (regenerateButton && regenerateButton.style.display !== 'none') ? regenerateButton.offsetHeight + 16 : 0;
        messagesContainer.style.paddingBottom = `${inputAreaHeight + regenerateHeight + 10}px`; // Total height + buffer

        // Adjust global error message position if visible
         if (appErrorMessage.classList.contains('show')) {
              const bottomOffset = inputAreaHeight + regenerateHeight + 10;
              appErrorMessage.style.bottom = `${bottomOffset}px`;
         }
    }

    function toggleSidebar() {
        const show = !settingsSidebar.classList.contains('show');
        settingsSidebar.classList.toggle('show', show);
        sidebarOverlay.classList.toggle('show', show);
        document.body.classList.toggle('sidebar-open', show);
        document.body.style.overflow = show && window.innerWidth <= 768 ? 'hidden' : '';
    }

    function showConfirmModal(callback) { confirmationCallback = callback; confirmModal.classList.add('show'); }
    function hideConfirmModal() { confirmModal.classList.remove('show'); confirmationCallback = null; }

    function formatDate(isoString) { /* ... same as before ... */ }
    function formatTime(isoString) { /* ... same as before ... */ }
    function escapeHtml(unsafe) { /* ... same as before ... */ }


    // --- Event Listeners Setup ---
    function setupEventListeners() {
        sendButton.addEventListener('click', sendMessage);
        messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
            // Trigger input event manually on Enter to resize after sending potentially
            else if (e.key === 'Enter' && e.shiftKey) {
                 setTimeout(adjustInputHeight, 0); // Adjust after newline inserted
            }
        });
        messageInput.addEventListener('input', adjustInputHeight);
        newConversationButton.addEventListener('click', () => {
            if (isTyping) return;
            stopSpeaking();
            clearMessages();
            currentConversationId = null;
            messages = [];
            hideRegenerateButton();
            document.querySelectorAll('.conversation-item.active').forEach(item => item.classList.remove('active'));
            if (window.innerWidth <= 768 && settingsSidebar.classList.contains('show')) toggleSidebar();
            messageInput.focus();
        });
        temperatureSlider.addEventListener('input', () => { temperatureValueSpan.textContent = temperatureSlider.value; });
        temperatureSlider.addEventListener('change', () => { localStorage.setItem('temperature', temperatureSlider.value); });
        maxTokensInput.addEventListener('change', () => localStorage.setItem('maxTokens', maxTokensInput.value) );
        darkModeToggle.addEventListener('change', () => {
            document.body.classList.toggle('dark-mode', darkModeToggle.checked);
            localStorage.setItem('darkModeEnabled', darkModeToggle.checked);
        });
        toggleSidebarButton.addEventListener('click', toggleSidebar);
        mobileMenuButton.addEventListener('click', toggleSidebar);
        mobileSettingsButton.addEventListener('click', toggleSidebar);
        closeSidebarButton.addEventListener('click', toggleSidebar);
        sidebarOverlay.addEventListener('click', toggleSidebar);
        confirmOkButton.addEventListener('click', () => { if (confirmationCallback) confirmationCallback(); hideConfirmModal(); });
        confirmCancelButton.addEventListener('click', hideConfirmModal);
        window.addEventListener('online', () => offlineIndicator.classList.remove('visible'));
        window.addEventListener('offline', () => offlineIndicator.classList.add('visible'));
        window.addEventListener('resize', adjustInputHeight); // Adjust padding on resize
    }

    // --- Initialization ---
    function initializeApp() {
        console.log("Initializing dzteck Chat App v2.1...");
        // Load settings from localStorage
        const savedTemp = localStorage.getItem('temperature');
        if (savedTemp) { temperatureSlider.value = savedTemp; temperatureValueSpan.textContent = savedTemp; }
        const savedTokens = localStorage.getItem('maxTokens');
        if (savedTokens) { maxTokensInput.value = savedTokens; }
        const savedDarkMode = localStorage.getItem('darkModeEnabled');
        darkModeToggle.checked = savedDarkMode === 'true'; // Set checkbox state
        document.body.classList.toggle('dark-mode', darkModeToggle.checked); // Apply theme

        // Check network status
        if (!navigator.onLine) offlineIndicator.classList.add('visible');

        setupEventListeners(); // Attach all event listeners
        clearMessages();     // Setup initial UI (adds welcome message)
        loadConversations(); // Fetch conversations
        adjustInputHeight(); // Calculate initial layout adjustments
        messageInput.focus(); // Focus input field
        console.log("App Initialized.");
    }

    initializeApp(); // Run the initialization

}); // End DOMContentLoaded
--- END OF FILE app.js ---

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
    let messages = [];
    let isTyping = false;
    let confirmationCallback = null;

    const WELCOME_MESSAGE_CONTENT = "السلام عليكم! أنا dzteck، مساعدك الرقمي بالعربية. كيف يمكنني مساعدتك اليوم؟";

    const FRONTEND_OFFLINE_MESSAGE = "أعتذر، لا يوجد اتصال بالإنترنت حاليًا. لا يمكنني معالجة طلبك الآن.";

    const PREDEFINED_RESPONSES = {
        "من صنعك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة dzteck للبحث والتطوير في الذكاء الاصطناعي.",
        "من انت": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة dzteck للبحث والتطوير في الذكاء الاصطناعي.",
        "مين عملك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة dzteck للبحث والتطوير في الذكاء الاصطناعي.",
        "مين انت": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة dzteck للبحث والتطوير في الذكاء الاصطناعي.",
        "من بناك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة dzteck للبحث والتطوير في الذكاء الاصطناعي."
    };

    function checkPredefinedResponse(userMessage) {
        const cleanedMessage = userMessage.toLowerCase().replace(/[?؟!,.\s]+/g, ' ').trim();
        for (const key in PREDEFINED_RESPONSES) {
            if (cleanedMessage.startsWith(key.toLowerCase() + ' ')) {
                return PREDEFINED_RESPONSES[key];
            }
            if (cleanedMessage === key.toLowerCase()) {
                return PREDEFINED_RESPONSES[key];
            }
        }
        return null;
    }// --- Speech Recognition (STT) ---
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let isRecording = false;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.lang = 'ar-SA';
        recognition.continuous = false;
        recognition.interimResults = true;

        recognition.onstart = () => {
            console.log('Speech recognition started');
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

            if (finalTranscript) {
                if (messageInput.value && !messageInput.value.match(/[\s\n]$/)) {
                    messageInput.value += ' ';
                }
                messageInput.value += finalTranscript;
            }

            messageInput.focus();
            adjustInputHeight();
        };

        recognition.onerror = (event) => {
            isRecording = false;
            micButton.classList.remove('recording');
            micButton.title = 'إدخال صوتي';
            messageInput.placeholder = 'اكتب رسالتك هنا...';

            let errorMessage = 'حدث خطأ في التعرف على الصوت.';
            if (event.error === 'not-allowed') {
                errorMessage = 'تم رفض الوصول إلى الميكروفون.';
            } else if (event.error === 'no-speech') {
                errorMessage = 'لم يتم الكشف عن صوت.';
            } else if (event.error === 'audio-capture') {
                errorMessage = 'فشل التقاط الصوت.';
            } else if (event.error === 'language-not-supported') {
                errorMessage = 'اللغة العربية غير مدعومة.';
            } else if (event.error === 'network') {
                errorMessage = 'مشكلة في الشبكة.';
            }

            alert(`خطأ في التعرف على الصوت: ${errorMessage}`);
        };

        recognition.onend = () => {
            isRecording = false;
            micButton.classList.remove('recording');
            micButton.title = 'إدخال صوتي';
            messageInput.placeholder = 'اكتب رسالتك هنا...';
        };

        if (micButton) {
            micButton.addEventListener('click', () => {
                if (isRecording) {
                    recognition.stop();
                } else {
                    recognition.start();
                }
            });
        }
    } else {
        if (micButton) micButton.style.display = 'none';
    }// --- Speech Synthesis (TTS) ---
    const SpeechSynthesis = window.speechSynthesis;
    let availableVoices = [];
    let speakingUtterance = null;

    if (SpeechSynthesis) {
        SpeechSynthesis.cancel();

        const loadVoices = () => {
            availableVoices = SpeechSynthesis.getVoices();
        };

        if (SpeechSynthesis.onvoiceschanged !== undefined) {
            SpeechSynthesis.onvoiceschanged = loadVoices;
        }

        loadVoices();

        const speakText = (text) => {
            if (!SpeechSynthesis || !text) {
                alert('خدمة التحدث غير متوفرة');
                return;
            }

            if (SpeechSynthesis.speaking) {
                SpeechSynthesis.cancel();
            }

            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'ar';
            utterance.rate = 0.9;

            let selectedVoice = availableVoices.find(v => v.lang === 'ar-SA') ||
                                availableVoices.find(v => v.lang.startsWith('ar')) ||
                                availableVoices.find(v => v.name.toLowerCase().includes('arab')) ||
                                availableVoices.find(v => v.default) || availableVoices[0];

            if (selectedVoice) {
                utterance.voice = selectedVoice;
            }

            utterance.onend = () => {
                speakingUtterance = null;
            };

            SpeechSynthesis.speak(utterance);
            speakingUtterance = utterance;
        };

        const stopSpeaking = () => {
            if (SpeechSynthesis && SpeechSynthesis.speaking) {
                SpeechSynthesis.cancel();
            }
        };

        messagesContainer.addEventListener('click', (event) => {
            const speakButtonTarget = event.target.closest('.speak-btn');
            if (!speakButtonTarget) return;

            const icon = speakButtonTarget.querySelector('i');
            const originalClass = icon.className;

            const messageBubble = speakButtonTarget.closest('.message-bubble');
            const textElement = messageBubble.querySelector('p');
            if (!textElement || !textElement.textContent) return;

            if (speakingUtterance && SpeechSynthesis.speaking) {
                stopSpeaking();
                icon.className = originalClass;
            } else {
                icon.className = 'fas fa-volume-high';
                const success = speakText(textElement.textContent);
                if (success) {
                    const check = setInterval(() => {
                        if (!SpeechSynthesis.speaking) {
                            icon.className = originalClass;
                            clearInterval(check);
                        }
                    }, 500);
                } else {
                    icon.className = originalClass;
                }
            }
        });

        const storedTtsPreference = localStorage.getItem('ttsEnabled');
        if (storedTtsPreference === 'true') {
            ttsToggle.checked = true;
        }

        ttsToggle.addEventListener('change', () => {
            localStorage.setItem('ttsEnabled', ttsToggle.checked);
            if (!ttsToggle.checked && SpeechSynthesis.speaking) {
                stopSpeaking();
            }
        });

    } else {
        if (ttsToggle) {
            ttsToggle.parentElement.style.display = 'none';
        }
    }const availableModels = [
        { value: 'mistralai/mistral-7b-instruct', label: 'Mistral 7B' },
        { value: 'anthropic/claude-3-haiku', label: 'Claude 3 Haiku' },
        { value: 'google/gemini-pro', label: 'Gemini Pro' },
        { value: 'meta-llama/llama-3-8b-instruct', label: 'LLaMA 3 8B' },
        { value: 'google/gemma-7b-it', label: 'Gemma 7B' },
        { value: 'openai/gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
        { value: 'anthropic/claude-3-sonnet', label: 'Claude 3 Sonnet' }
    ];

    modelSelect.innerHTML = '';
    availableModels.forEach(model => {
        const option = document.createElement('option');
        option.value = model.value;
        option.textContent = model.label;
        modelSelect.appendChild(option);
    });

    const savedModel = localStorage.getItem('selectedModel');
    if (savedModel && availableModels.some(model => model.value === savedModel)) {
        modelSelect.value = savedModel;
    }

    modelSelect.addEventListener('change', () => {
        localStorage.setItem('selectedModel', modelSelect.value);
    });

    // إعدادات واجهة الاستخدام
    const savedTemperature = localStorage.getItem('temperature');
    if (savedTemperature) {
        temperatureSlider.value = savedTemperature;
        temperatureValueSpan.textContent = savedTemperature;
    }

    const savedMaxTokens = localStorage.getItem('maxTokens');
    if (savedMaxTokens) {
        maxTokensInput.value = savedMaxTokens;
    }

    const savedDarkMode = localStorage.getItem('darkModeEnabled');
    if (savedDarkMode === 'true') {
        darkModeToggle.checked = true;
        document.body.classList.add('dark-mode');
    }

    if (!navigator.onLine) {
        offlineIndicator.classList.add('visible');
    }// التهيئة النهائية
    clearMessages(); // عرض رسالة الترحيب: "أنا dzteck..."
    loadConversations();
    messageInput.focus();

    // استماع لتغيرات الشبكة
    window.addEventListener('online', function() {
        offlineIndicator.classList.remove('visible');
    });

    window.addEventListener('offline', function() {
        offlineIndicator.classList.add('visible');
    });

});

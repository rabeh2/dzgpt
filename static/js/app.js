// Ensure the DOM is fully loaded before running the script
document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const settingsSidebar = document.getElementById('settings-sidebar');
    const toggleSidebarButton = document.getElementById('toggle-sidebar'); // Desktop toggle
    const mobileMenuButton = document.getElementById('mobile-menu'); // Mobile open
    const mobileSettingsButton = document.getElementById('mobile-settings'); // Mobile open (from footer)
    const closeSidebarButton = document.getElementById('close-sidebar'); // Mobile close
    const sidebarOverlay = document.getElementById('sidebar-overlay'); // New overlay element

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
    const appErrorMessage = document.getElementById('app-error-message'); // Global error message element

    const confirmModal = document.getElementById('confirm-modal');
    const confirmMessage = document.getElementById('confirm-message');
    const confirmOkButton = document.getElementById('confirm-ok');
    const confirmCancelButton = document.getElementById('confirm-cancel');

    const ttsToggle = document.getElementById('tts-toggle');
    const micButton = document.getElementById('mic-button');

    // --- State Variables ---
    let currentConversationId = null;
    // Stores current conversation messages {role: 'user'/'assistant', content: '...', id: '[DB_ID or null]'}
    let messages = [];
    let isTyping = false; // To prevent multiple requests or show typing indicator
    let confirmationCallback = null; // Function to call after modal confirmation
    const WELCOME_MESSAGE_CONTENT = "السلام عليكم! أنا ياسمين، مساعدتك الرقمية بالعربية. كيف يمكنني مساعدتك اليوم؟";

    // --- Frontend Offline Message ---
    const FRONTEND_OFFLINE_MESSAGE = "أعتذر، لا يوجد اتصال بالإنترنت حاليًا. لا يمكنني معالجة طلبك الآن.";

    // --- Predefined Responses (Canned Responses) ---
    const PREDEFINED_RESPONSES = {
        "من صنعك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "من انت": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "مين عملك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "مين انت": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "من بناك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "ما هو اسمك": "اسمي ياسمين، مساعدتك الرقمية.",
        "اسمك ايه": "اسمي ياسمين، مساعدتك الرقمية.",
        "كيف حالك": "أنا بخير شكراً لك، كيف يمكنني مساعدتك؟",
        "شكرا": "على الرحب والسعة!",
        "مع السلامة": "إلى اللقاء! أتمنى لك يوماً سعيداً.",
        "ما هي قدراتك": "أنا نموذج لغوي مدرب على فهم اللغة العربية وتوليد النصوص، يمكنني المساعدة في الإجابة على الأسئلة، كتابة النصوص، الترجمة، والعديد من المهام الأخرى. ما الذي تود تجربته؟",
        "ما هي حدودك": "لا يمكنني تصفح الإنترنت في الوقت الفعلي، وقد لا أكون على دراية بأحدث المعلومات بعد نقطة توقفي التدريبي. كما أنني لا أمتلك مشاعر أو وعياً.",
        "من قام بتطويرك": "تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "هل تتذكر محادثاتنا": "نعم، يمكنني تذكر سياق محادثتنا الحالية لمساعدتك بشكل أفضل. المحادثات السابقة يتم حفظها ويمكنك استعراضها.",
        "ما هي هذه المنصة": "هذه المنصة هي واجهة دردشة لياسمين GPT، تم تطويرها بواسطة شركة dzteck.",
        "اريد مساعده": "بالتأكيد، أنا هنا للمساعدة. ما هو سؤالك أو طلبك؟",
        "ما هو الذكاء الاصطناعي": "الذكاء الاصطناعي هو مجال في علوم الحاسوب يهدف إلى إنشاء أنظمة أو آلات يمكنها أداء مهام تتطلب عادةً ذكاءً بشريًا، مثل التعلم، حل المشكلات، الإدراك، واتخاذ القرارات.",
        "هل انت انسان": "أنا برنامج حاسوبي، لست إنسانًا ولا أمتلك مشاعر أو وعيًا.",
        "ما هي لغتك الأساسية": "تم تدريبي على كمية هائلة من البيانات النصية بلغات متعددة، ولكنني مصمم بشكل خاص لفهم وتوليد اللغة العربية بطلاقة.",
        "هل يمكنك التحدث بلهجة معينة": "تم تدريبي على العربية الفصحى وبعض اللهجات. قد أستخدم أحيانًا تعابير من لهجات مختلفة، لكن جودة الرد قد تختلف حسب اللهجة.",
        "كم عمرك": "ليس لدي عمر بالمعنى البشري، ولكن تطويري مستمر ويتم تحديثي بانتظام.",
        "من هو مؤسس شركة ياسمين": "أنا نموذج لغوي ولا أمتلك معلومات شخصية عن مؤسسي الشركة. أركز على تقديم المساعدة اللغوية."
    };
    // Helper function to check for predefined responses
    function checkPredefinedResponse(userMessage) {
        const cleanedMessage = userMessage.toLowerCase().replace(/[?؟!,.;:]+/g, '').trim();

        for (const key in PREDEFINED_RESPONSES) {
            const cleanedKey = key.toLowerCase().replace(/[?؟!,.;:]+/g, '').trim();
            if (cleanedMessage === cleanedKey) {
                console.log(`Matched exact predefined key: "${key}"`);
                return PREDEFINED_RESPONSES[key];
            }
            const startsWithWordRegex = new RegExp(`^${cleanedKey}\\b`);
             if (startsWithWordRegex.test(cleanedMessage)) {
                  console.log(`Matched startsWith word boundary predefined key: "${key}"`);
                  return PREDEFINED_RESPONSES[key];
             }
            const wordRegex = new RegExp(`\\b${cleanedKey}\\b`);
            if (wordRegex.test(cleanedMessage)) {
                 console.log(`Matched word boundary predefined key: "${key}"`);
                 return PREDEFINED_RESPONSES[key];
            }
             if (cleanedMessage.includes(cleanedKey) && cleanedKey.length > 3) {
                  console.log(`Matched includes predefined key: "${key}"`);
                  return PREDEFINED_RESPONSES[key];
             }
        }
        console.log("No predefined response found.");
        return null;
    }


    // --- Speech Recognition (STT) ---
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
            messageInput.placeholder = '... استمع... تحدث الآن...';
            messageInput.value = '';
            adjustInputHeight();
            sendButton.disabled = true;
            if(micButton) micButton.disabled = false;
        };

        recognition.onresult = (event) => {
            let finalTranscript = '';
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                }
            }

            if (finalTranscript) {
                 if (messageInput.value && !messageInput.value.match(/[\s\n]$/)) {
                    messageInput.value += ' ';
                 }
                messageInput.value += finalTranscript.trim();
            }

             messageInput.focus();
             adjustInputHeight();
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            isRecording = false;
            micButton.classList.remove('recording');
            micButton.title = 'إدخال صوتي';
            messageInput.placeholder = 'اكتب رسالتك هنا...';
            sendButton.disabled = messageInput.value.trim() === '' || isTyping;
             if(micButton) micButton.disabled = false;
             displayError(`خطأ في الإدخال الصوتي: ${getSpeechErrorDescription(event.error)}`);
        };

        recognition.onend = () => {
            console.log('Speech recognition ended');
            isRecording = false;
            micButton.classList.remove('recording');
            micButton.title = 'إدخال صوتي';
            messageInput.placeholder = 'اكتب رسالتك هنا...';
            sendButton.disabled = messageInput.value.trim() === '' || isTyping;
             if(micButton) micButton.disabled = false;
        };

        function getSpeechErrorDescription(error) {
             switch (error) {
                 case 'not-allowed': return 'تم رفض الوصول إلى الميكروفون. يرجى السماح للموقع بالوصول من إعدادات المتصفح.';
                 case 'no-speech': return 'لم يتم الكشف عن صوت. يرجى التحدث بوضوح.';
                 case 'audio-capture': return 'فشل التقاط الصوت. تأكد من اتصال الميكروفون بشكل صحيح.';
                 case 'language-not-supported': return 'اللغة العربية غير مدعومة في متصفحك لهذا الإدخال الصوتي.';
                 case 'network': return 'مشكلة في الشبكة أثناء التعرف على الصوت.';
                 case 'service-not-allowed': return 'خدمة الإدخال الصوتي غير مسموح بها.';
                 case 'bad-grammar': return 'خطأ في تحليل قواعد اللغة.';
                 default: return `حدث خطأ غير معروف (${error}).`;
             }
        }

        if (micButton) {
             micButton.addEventListener('click', () => {
               if (isRecording) {
                   recognition.stop();
               } else {
                   recognition.start();
               }
             });
        } else {
             console.warn('Mic button element not found.');
        }

    } else {
        console.warn('Web Speech API (SpeechRecognition) not supported in this browser.');
        if (micButton) micButton.style.display = 'none';
    }

    // --- Speech Synthesis (TTS) ---
    const SpeechSynthesis = window.speechSynthesis;
    let availableVoices = [];
    let speakingUtterance = null;
    let voiceLoadAttempts = 0;
    const MAX_VOICE_LOAD_ATTEMPTS = 5;

    const loadVoices = () => {
        availableVoices = SpeechSynthesis.getVoices();
        if (availableVoices.length > 0) {
             console.log(`${availableVoices.length} voices loaded.`);
             const arabicVoices = availableVoices.filter(voice => voice.lang.startsWith('ar') || voice.name.toLowerCase().includes('arab'));
             if (arabicVoices.length > 0) {
                  console.log(`Found ${arabicVoices.length} Arabic voices.`);
             } else {
                  console.warn('No specific Arabic voices found. Using default.');
             }
        } else if (voiceLoadAttempts < MAX_VOICE_LOAD_ATTEMPTS) {
            voiceLoadAttempts++;
            console.log(`Voices not immediately available. Attempt ${voiceLoadAttempts}/${MAX_VOICE_LOAD_ATTEMPTS}. Retrying in 500ms.`);
            setTimeout(loadVoices, 500);
        } else {
            console.warn('Failed to load voices after multiple attempts. TTS may not work.');
        }
    };

    if (SpeechSynthesis) {
        SpeechSynthesis.cancel();

        if (SpeechSynthesis.onvoiceschanged !== undefined) {
            SpeechSynthesis.onvoiceschanged = loadVoices;
        }
        loadVoices();

        const speakText = (text) => {
            if (!SpeechSynthesis || !text) {
                console.warn('Speech synthesis not available or text is empty.');
                displayError('خدمة التحدث غير متوفرة في هذا المتصفح');
                return false;
            }

            if (availableVoices.length === 0) {
                loadVoices();
                if (availableVoices.length === 0) {
                     console.warn('No voices available after attempt. Cannot speak.');
                     displayError('لا توجد أصوات تحدث متاحة في متصفحك.');
                     return false;
                }
            }

            stopSpeaking();

            try {
                const utterance = new SpeechSynthesisUtterance(text);

                let selectedVoice = availableVoices.find(v => v.lang === 'ar-SA');
                if (!selectedVoice) {
                    selectedVoice = availableVoices.find(v => v.lang.startsWith('ar'));
                }
                if (!selectedVoice) {
                    selectedVoice = availableVoices.find(v => v.name.toLowerCase().includes('arab'));
                }
                if (!selectedVoice) {
                     selectedVoice = availableVoices.find(v => v.default) || availableVoices[0];
                     console.warn('No specific Arabic voice found, using default or first available.');
                }

                if (selectedVoice) {
                    utterance.voice = selectedVoice;
                } else {
                     console.warn('No voice selected, using browser default.');
                }

                utterance.lang = 'ar';
                utterance.rate = 0.95;
                utterance.pitch = 1.0;
                utterance.volume = 1.0;

                utterance.onstart = () => { speakingUtterance = utterance; };
                utterance.onend = () => { speakingUtterance = null; document.querySelectorAll('.speak-btn i').forEach(icon => { if (icon.classList.contains('fa-volume-high')) icon.className = 'fas fa-volume-up'; }); };
                utterance.onerror = (event) => { console.error('Speech synthesis error:', event.error); speakingUtterance = null; document.querySelectorAll('.speak-btn i').forEach(icon => { if (icon.classList.contains('fa-volume-high')) icon.className = 'fas fa-volume-up'; }); displayError('حدث خطأ أثناء التحدث الصوتي.'); };

                SpeechSynthesis.speak(utterance);
                return true;
            } catch (err) {
                console.error('Error in speech synthesis:', err);
                displayError('حدث خطأ في خدمة التحدث الصوتي.');
                return false;
            }
        };

         const stopSpeaking = () => {
             if (SpeechSynthesis && SpeechSynthesis.speaking) {
                 SpeechSynthesis.cancel();
                 speakingUtterance = null;
                 console.log('Speaking stopped.');
                 document.querySelectorAll('.speak-btn i').forEach(icon => {
                     if (icon.classList.contains('fa-volume-high')) {
                          icon.className = 'fas fa-volume-up';
                     }
                 });
             }
         };


        messagesContainer.addEventListener('click', async (event) => {
            const speakButtonTarget = event.target.closest('.speak-btn');
            const copyButtonTarget = event.target.closest('.copy-btn');
            const voteButtonTarget = event.target.closest('.vote-buttons button');

            // --- Handle Speak Button ---
            if (speakButtonTarget) {
                event.preventDefault();
                event.stopPropagation();
                const icon = speakButtonTarget.querySelector('i');
                const messageBubble = speakButtonTarget.closest('.message-bubble');
                const textElement = messageBubble ? messageBubble.querySelector('p') : null;
                if (!textElement || !textElement.textContent) { console.warn('Speak button clicked, but message text not found.'); return; }
                const textToSpeak = textElement.textContent;

                if (speakingUtterance && SpeechSynthesis.speaking && speakingUtterance.text === textToSpeak) {
                    stopSpeaking();
                } else {
                    stopSpeaking();
                    const success = speakText(textToSpeak);
                    if (success) { icon.className = 'fas fa-volume-high'; } else { icon.className = 'fas fa-volume-up'; }
                }
            }

            // --- Handle Copy Button ---
            if (copyButtonTarget) {
                 event.preventDefault();
                 event.stopPropagation();
                 const icon = copyButtonTarget.querySelector('i');
                 const messageBubble = copyButtonTarget.closest('.message-bubble');
                 const textElement = messageBubble ? messageBubble.querySelector('p') : null;
                 if (!textElement || !textElement.textContent) { console.warn('Copy button clicked, but message text not found.'); return; }
                 const textToCopy = textElement.textContent;

                 navigator.clipboard.writeText(textToCopy)
                     .then(() => {
                         const originalClass = icon.className; icon.className = 'fas fa-check';
                         setTimeout(() => { icon.className = originalClass; }, 2000);
                     })
                     .catch(err => {
                         console.error('Failed to copy text:', err);
                         const originalClass = icon.className; icon.className = 'fas fa-times';
                         setTimeout(() => { icon.className = originalClass; }, 2000);
                         displayError('فشل نسخ النص.');
                     });
            }

             // --- Handle Vote Buttons ---
             if (voteButtonTarget) {
                 event.preventDefault();
                 event.stopPropagation();
                 const voteType = voteButtonTarget.dataset.voteType;
                 const messageBubble = voteButtonTarget.closest('.message-bubble');
                 const messageId = messageBubble ? messageBubble.dataset.messageId : null;
                 if (!messageId) { console.warn('Vote button clicked, but message ID not found on bubble.'); displayError('لا يمكن تسجيل التصويت لهذه الرسالة.'); return; }
                 console.log(`Vote submitted: ${voteType} for message ID ${messageId}`);

                 const success = await sendVote(messageId, voteType);

                 if (success) {
                      const voteButtonsContainer = voteButtonTarget.closest('.vote-buttons');
                      if (voteButtonsContainer) {
                          voteButtonsContainer.querySelectorAll('button').forEach(btn => {
                              btn.disabled = true;
                              if (btn === voteButtonTarget) {
                                   btn.classList.add(voteType === 'like' ? 'liked' : 'disliked');
                              } else {
                                   btn.style.opacity = 0.5;
                                   btn.style.pointerEvents = 'none';
                                   btn.style.cursor = 'default';
                              }
                          });
                      }
                     displayError(`تم تسجيل تصويتك (${voteType === 'like' ? 'إعجاب' : 'عدم إعجاب'}).`, 3000, false);
                 }
             }
        });

         async function sendVote(messageId, voteType) {
             try {
                 const response = await fetch('/api/vote', {
                     method: 'POST',
                     headers: { 'Content-Type': 'application/json', },
                     body: JSON.stringify({ message_id: parseInt(messageId, 10), vote_type: voteType, }),
                 });
                 if (!response.ok) {
                     const errorData = await response.json();
                     console.error('Failed to send vote:', response.status, errorData);
                     throw new Error(errorData.error || 'فشل تسجيل التصويت.');
                 }
                 const result = await response.json();
                 if (result.success) { console.log(`Vote (${voteType}) for message ${messageId} recorded.`); return true; }
                 else { console.error('Vote API returned success: false', result); throw new Error(result.error || 'فشل تسجيل التصويت.'); }
             } catch (error) {
                 console.error('Error sending vote:', error);
                 displayError(`حدث خطأ أثناء تسجيل التصويت: ${error.message}`);
                 return false;
             }
         }

        const storedTtsPreference = localStorage.getItem('ttsEnabled');
        if (storedTtsPreference === 'true') { ttsToggle.checked = true; } else { ttsToggle.checked = false; }
        ttsToggle.addEventListener('change', () => {
            localStorage.setItem('ttsEnabled', ttsToggle.checked);
            if (!ttsToggle.checked && SpeechSynthesis && SpeechSynthesis.speaking) { stopSpeaking(); }
        });

    } else {
        console.warn('Web Speech API (SpeechSynthesis) not supported in this browser.');
        if (ttsToggle) { ttsToggle.closest('.setting-item').style.display = 'none'; }
        const observer = new MutationObserver(mutations => {
            mutations.forEach(mutation => {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === 1) {
                         const speakButton = node.querySelector('.speak-btn');
                         if (speakButton) { speakButton.style.display = 'none'; }
                    }
                });
            });
        });
        observer.observe(messagesContainer, { childList: true, subtree: true });
    }

    // --- تهيئة النماذج ---
    const availableModels = [
        { value: 'mistralai/mistral-7b-instruct-v0.2', label: 'Mistral 7B Instruct' },
        { value: 'anthropic/claude-3-haiku', label: 'Claude 3 Haiku' },
        { value: 'google/gemini-pro', label: 'Gemini Pro' },
        { value: 'meta-llama/llama-3-8b-instruct', label: 'LLaMA 3 8B Instruct' },
        { value: 'google/gemma-7b-it', label: 'Gemma 7B Instruct' },
        { value: 'openai/gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
        { value: 'anthropic/claude-3-sonnet', label: 'Claude 3 Sonnet' },
        { value: 'perplexity/llama-3-70b-instruct', label: 'LLaMA 3 70B Instruct (Perplexity)'},
        { value: 'mistralai/mixtral-8x7b-instruct-v0.1', label: 'Mixtral 8x7b Instruct'},
    ];

    modelSelect.innerHTML = '';
    availableModels.forEach(model => {
        const option = document.createElement('option');
        option.value = model.value; option.textContent = model.label;
        modelSelect.appendChild(option);
    });

    const savedModel = localStorage.getItem('selectedModel');
    if (savedModel && availableModels.some(model => model.value === savedModel)) {
        modelSelect.value = savedModel;
    } else if (availableModels.length > 0) {
         modelSelect.value = availableModels[0].value; localStorage.setItem('selectedModel', availableModels[0].value);
    } else {
         console.error("No models available to select!"); modelSelect.disabled = true;
    }
    modelSelect.addEventListener('change', () => { localStorage.setItem('selectedModel', modelSelect.value); });

    // --- تحميل وعرض المحادثات ---
    async function loadConversations() {
        console.log("Loading conversations...");
        const activeItemId = conversationsList.querySelector('.conversation-item.active')?.dataset.conversationId;
        conversationsList.innerHTML = '';
        conversationsList.appendChild(createLoadingState('تحميل...'));

        try {
            const response = await fetch('/api/conversations');
            if (!response.ok) {
                 const errorText = await response.text(); console.error('Failed to load conversations response:', response.status, errorText);
                throw new Error(`فشل تحميل المحادثات: ${response.status}`);
            }
            const conversations = await response.json();
            conversationsList.innerHTML = '';

            if (conversations.length === 0) {
                const emptyState = document.createElement('div');
                emptyState.className = 'empty-state'; emptyState.textContent = 'لا توجد محادثات سابقة';
                conversationsList.appendChild(emptyState);
            } else {
                conversations.forEach(conversation => {
                    const conversationItem = document.createElement('div');
                    conversationItem.className = 'conversation-item';
                    if (conversation.id === currentConversationId || conversation.id === activeItemId) { conversationItem.classList.add('active'); }
                    conversationItem.dataset.conversationId = conversation.id;
                    const date = new Date(conversation.updated_at);
                    const formattedDate = new Intl.DateTimeFormat('ar-SA', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true }).format(date);
                    const titleSpan = document.createElement('span');
                    titleSpan.textContent = conversation.title; titleSpan.title = `${conversation.title} - آخر تحديث: ${formattedDate}`;
                    const actionsDiv = document.createElement('div'); actionsDiv.className = 'conversation-actions';
                    const editButton = document.createElement('button'); editButton.className = 'icon-button edit-conv-btn'; editButton.title = 'تعديل العنوان'; editButton.innerHTML = '<i class="fas fa-edit"></i>';
                    editButton.onclick = (e) => { e.stopPropagation(); editConversationTitle(conversation.id, conversation.title); };
                    const deleteButton = document.createElement('button'); deleteButton.className = 'icon-button delete-conv-btn'; deleteButton.title = 'حذف المحادثة'; deleteButton.innerHTML = '<i class="fas fa-trash-alt"></i>';
                    deleteButton.onclick = (e) => { e.stopPropagation(); confirmDeleteConversation(conversation.id); };
                    actionsDiv.appendChild(editButton); actionsDiv.appendChild(deleteButton);
                    conversationItem.appendChild(titleSpan); conversationItem.appendChild(actionsDiv);
                    conversationItem.addEventListener('click', () => {
                        if (conversation.id !== currentConversationId) { loadConversation(conversation.id); }
                        else { console.log(`Conversation ${conversation.id} is already active.`); if (window.innerWidth <= 768) toggleSidebar(); }
                    });
                    conversationsList.appendChild(conversationItem);
                });
            }
        } catch (error) {
            console.error('Error loading conversations:', error);
            conversationsList.innerHTML = '';
            conversationsList.appendChild(createErrorState('فشل تحميل المحادثات', error.message));
            displayError(`فشل تحميل قائمة المحادثات: ${error.message}`);
        }
    }

     function createLoadingState(message) {
         const loadingState = document.createElement('div'); loadingState.className = 'empty-state loading-state';
         loadingState.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${message}`; return loadingState;
     }

     function createErrorState(message, details) {
         const errorState = document.createElement('div'); errorState.className = 'empty-state error-state';
         errorState.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}<br><small>${details || ''}</small>`; return errorState;
     }

    async function loadConversation(conversationId) {
        console.log(`Loading conversation ID: ${conversationId}`);
        clearMessages(false); messagesContainer.appendChild(createLoadingState('تحميل المحادثة...'));
        currentConversationId = conversationId;
        document.querySelectorAll('.conversation-item').forEach(item => {
             item.classList.remove('active'); if (item.dataset.conversationId === conversationId) { item.classList.add('active'); item.classList.add('loading'); }
         });

        try {
            const response = await fetch(`/api/conversations/${conversationId}`);
            if (!response.ok) { const errorText = await response.text(); console.error('Failed to load conversation response:', response.status, errorText); throw new Error(`فشل تحميل المحادثة: ${response.status}`); }
            const conversation = await response.json();
            messagesContainer.innerHTML = '';
            messages = conversation.messages.map(msg => ({ id: msg.id, role: msg.role, content: msg.content, created_at: msg.created_at }));
            messages.forEach(msg => { addMessageToUI(msg.role, msg.content, msg.created_at, msg.id); });

            if (window.innerWidth <= 768) { toggleSidebar(); }
            scrollToBottom();
            if (messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length-1].id !== null) { showRegenerateButton(); } else { hideRegenerateButton(); }
            console.log(`Conversation ${conversationId} loaded successfully.`);
        } catch (error) {
            console.error('Error loading conversation:', error); messagesContainer.innerHTML = '';
            messagesContainer.appendChild(createErrorState('فشل تحميل المحادثة.', error.message));
            displayError(`فشل تحميل المحادثة: ${error.message}`); messages = []; hideRegenerateButton();
        } finally {
             document.querySelectorAll('.conversation-item').forEach(item => item.classList.remove('loading'));
             loadConversations();
        }
    }

    function editConversationTitle(conversationId, currentTitle) {
        const newTitle = prompt('أدخل العنوان الجديد للمحادثة:', currentTitle);
        if (newTitle !== null && newTitle.trim() !== '') {
             if (newTitle.trim().length > 100) { displayError('عنوان المحادثة يجب ألا يتجاوز 100 حرف.'); return; }
            updateConversationTitle(conversationId, newTitle.trim());
        } else if (newTitle !== null) { displayError('عنوان المحادثة لا يمكن أن يكون فارغاً.'); }
    }

    async function updateConversationTitle(conversationId, newTitle) {
        console.log(`Updating title for conversation ${conversationId} to '${newTitle}'`);
        const convItem = document.querySelector(`.conversation-item[data-conversation-id="${conversationId}"]`);
        let originalTitle = ''; if (convItem) { originalTitle = convItem.querySelector('span').textContent; convItem.classList.add('loading'); }
        try {
            const response = await fetch(`/api/conversations/${conversationId}/title`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json', }, body: JSON.stringify({ title: newTitle }),
            });
            if (!response.ok) { const errorData = await response.json(); const errorText = errorData.error || await response.text(); console.error('Failed to update title response:', response.status, errorText); throw new Error(errorData.error || `فشل تحديث العنوان: ${response.status}`); }
            const result = await response.json();
            if (result.success) { console.log(`Title updated successfully for ${conversationId}.`); loadConversations(); displayError('تم تحديث عنوان المحادثة بنجاح.', 3000, false); }
            else { throw new Error(result.error || 'فشل تحديث العنوان من الخادم.'); }
        } catch (error) {
            console.error('Error updating conversation title:', error); displayError(`فشل تحديث عنوان المحادثة: ${error.message}`);
             if (convItem && originalTitle) { convItem.querySelector('span').textContent = originalTitle; }
        } finally { if (convItem) { convItem.classList.remove('loading'); } }
    }

    function confirmDeleteConversation(conversationId) {
        confirmMessage.textContent = 'هل أنت متأكد من أنك تريد حذف هذه المحادثة؟ لا يمكن التراجع عن هذا الإجراء.';
        showConfirmModal(() => { deleteConversation(conversationId); });
    }

    async function deleteConversation(conversationId) {
         console.log(`Attempting to delete conversation ID: ${conversationId}`);
         const convItem = document.querySelector(`.conversation-item[data-conversation-id="${conversationId}"]`);
         if (convItem) { convItem.classList.add('loading'); convItem.style.opacity = 0.5; }
        try {
            const response = await fetch(`/api/conversations/${conversationId}`, { method: 'DELETE', });
            if (!response.ok) { const errorData = await response.json(); const errorText = errorData.error || await response.text(); console.error('Failed to delete conversation response:', response.status, errorText); throw new Error(errorData.error || `فشل حذف المحادثة: ${response.status}`); }
            const result = await response.json();
            if (result.success) {
                console.log(`Conversation ${conversationId} deleted successfully.`);
                if (conversationId === currentConversationId) { clearMessages(true); currentConversationId = null; messages = []; hideRegenerateButton(); console.log("Current conversation was deleted. UI cleared."); }
                displayError('تم حذف المحادثة بنجاح.', 3000, false);
                loadConversations();
            } else { throw new Error(result.error || 'فشل حذف المحادثة من الخادم.'); }
        } catch (error) {
            console.error('Error deleting conversation:', error); displayError(`فشل حذف المحادثة: ${error.message}`);
        } finally {
             const convItem = document.querySelector(`.conversation-item[data-conversation-id="${conversationId}"]`);
             if (convItem) { convItem.classList.remove('loading');

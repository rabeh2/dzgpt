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
    const WELCOME_MESSAGE_CONTENT = "السلام عليكم! أنا ياسمين، مساعدتك الرقمية بالعربية. كيف يمكنني مساعدتك اليوم؟";

    // --- New: Frontend Offline Message ---
    const FRONTEND_OFFLINE_MESSAGE = "أعتذر، لا يوجد اتصال بالإنترنت حاليًا. لا يمكنني معالجة طلبك الآن.";

    // --- New: Predefined Responses (Canned Responses) ---
    const PREDEFINED_RESPONSES = {
        "من صنعك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "من انت": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "مين عملك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "مين انت": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        "من بناك": "أنا نموذج لغوي كبير، تم تطويري بواسطة شركة ياسمين للتطوير والبحث في الذكاء الاصطناعي.",
        // Add other specific phrases if needed
    };
     // Helper function to check for predefined responses
     function checkPredefinedResponse(userMessage) {
         // Basic cleaning: lowercase, remove common punctuation, trim
         const cleanedMessage = userMessage.toLowerCase().replace(/[?؟!,.\s]+/g, ' ').trim();
         // Check if the cleaned message *starts with* any of the keys
         // Using startsWith allows matching "من صنعك يا ياسمين؟"
         for (const key in PREDEFINED_RESPONSES) {
              if (cleanedMessage.startsWith(key.toLowerCase() + ' ')) { // Check for word boundary
                  return PREDEFINED_RESPONSES[key];
              }
               if (cleanedMessage === key.toLowerCase()) { // Exact match
                  return PREDEFINED_RESPONSES[key];
               }
         }
         return null; // No predefined response found
     }


    // --- Speech Recognition (STT) ---
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let isRecording = false;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.lang = 'ar-SA'; // Set language to Arabic (Saudi Arabia). Adjust as needed (e.g., 'ar-EG' for Egypt)
        recognition.continuous = false; // Capture a single utterance
        recognition.interimResults = true; // Get results while speaking

        recognition.onstart = () => {
            console.log('Speech recognition started');
            isRecording = true;
            micButton.classList.add('recording');
            micButton.title = 'إيقاف التسجيل الصوتي';
            // Optionally clear input or show indicator
            // messageInput.value = ''; // Clear input on start? Or append? Let's append for now.
            messageInput.placeholder = 'استمع... تحدث الآن...';
        };

        recognition.onresult = (event) => {
            console.log('Speech recognition result:', event);
            let interimTranscript = '';
            let finalTranscript = '';

            // Process all results
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                } else {
                    interimTranscript += event.results[i][0].transcript;
                }
            }

            // Append final transcript to the input
            if (finalTranscript) {
                 // Append a space if input already has text and doesn't end with space/newline
                 if (messageInput.value && !messageInput.value.match(/[\s\n]$/)) {
                    messageInput.value += ' ';
                 }
                messageInput.value += finalTranscript;
            } else {
                 // Optionally show interim results
                 // messageInput.placeholder = `...${interimTranscript}...`; // Indicate listening - might be distracting
            }

             // Keep input field focused and adjust height
             messageInput.focus();
             adjustInputHeight();
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            isRecording = false;
            micButton.classList.remove('recording');
            micButton.title = 'إدخال صوتي';
             messageInput.placeholder = 'اكتب رسالتك هنا...'; // Reset placeholder
             // Provide more specific feedback based on error type
             let errorMessage = 'حدث خطأ في التعرف على الصوت.';
             if (event.error === 'not-allowed') {
                  errorMessage = 'تم رفض الوصول إلى الميكروفون. يرجى السماح للموقع بالوصول.';
             } else if (event.error === 'no-speech') {
                  errorMessage = 'لم يتم الكشف عن صوت. يرجى التحدث بوضوح.';
             } else if (event.error === 'audio-capture') {
                  errorMessage = 'فشل التقاط الصوت. تأكد من اتصال الميكروفون.';
             } else if (event.error === 'language-not-supported') {
                  errorMessage = 'اللغة العربية غير مدعومة في متصفحك لهذا الإدخال الصوتي.';
             } else if (event.error === 'network') {
                 errorMessage = 'مشكلة في الشبكة أثناء التعرف على الصوت.';
             }


             alert(`خطأ في التعرف على الصوت: ${errorMessage}`);

        };

        recognition.onend = () => {
            console.log('Speech recognition ended');
            isRecording = false;
            micButton.classList.remove('recording');
            micButton.title = 'إدخال صوتي';
             messageInput.placeholder = 'اكتب رسالتك هنا...'; // Reset placeholder
             // If input is not empty after recording, maybe send automatically? Or let user send?
             // For now, let the user click send.
        };

         // Mic button click handler
        if (micButton) { // Check if micButton exists
             micButton.addEventListener('click', () => {
               if (isRecording) {
                   recognition.stop(); // Stop recording
               } else {
                   // Clear input before starting new voice input
                   // Decide whether to clear or append. Clearing is simpler for single utterances.
                   // messageInput.value = '';
                   recognition.start(); // Start recording
               }
             });
        }


         // Hide mic button if STT is not supported
    } else {
        console.warn('Web Speech API (SpeechRecognition) not supported in this browser.');
        if (micButton) micButton.style.display = 'none'; // Hide the microphone button
    }

    // --- Speech Synthesis (TTS) ---
    const SpeechSynthesis = window.speechSynthesis;
    let availableVoices = [];
    let speakingUtterance = null; // Keep track of the current utterance
    
    // Force initial loading of voices
    if (SpeechSynthesis) {
        SpeechSynthesis.cancel(); // Reset any previous state
        
        // Function to load available voices and prioritize Arabic voices
        const loadVoices = () => {
            availableVoices = SpeechSynthesis.getVoices();
            
            // تسجيل الأصوات المتوفرة في سجل الكونسول
            console.log(`${availableVoices.length} voices loaded`);
            
            // تصفية الأصوات العربية المتوفرة
            const arabicVoices = availableVoices.filter(voice => 
                voice.lang === 'ar' || 
                voice.lang.startsWith('ar-') ||
                voice.lang.includes('ar') ||
                voice.name.toLowerCase().includes('arab')
            );
            
            if (arabicVoices.length > 0) {
                console.log(`تم العثور على ${arabicVoices.length} صوت عربي:`, 
                    arabicVoices.map(v => `${v.name} (${v.lang})`).join(', '));
            } else {
                console.warn('لم يتم العثور على أي صوت عربي في المتصفح');
            }
        };
        
        // Handle voice loading - browsers handle this differently
        if (SpeechSynthesis.onvoiceschanged !== undefined) {
            // Chrome and most browsers need this event
            SpeechSynthesis.onvoiceschanged = loadVoices;
        }
        
        // Initial loading attempt
        loadVoices();
        
        // Double-check if voices are already available
        if (availableVoices.length === 0) {
            console.log('No voices immediately available. Waiting for voices to load...');
            // Force a second attempt after a short delay
            setTimeout(() => {
                loadVoices();
                if (availableVoices.length === 0) {
                    console.warn('Still no voices available after delay. TTS may not work properly.');
                }
            }, 500);
        }


        // Function to speak a given text
        const speakText = (text) => {
            if (!SpeechSynthesis || !text) {
                console.warn('Speech synthesis not available or text is empty.');
                alert('خدمة التحدث غير متوفرة في هذا المتصفح');
                return;
            }

            // Make sure we have the latest voices
            if (availableVoices.length === 0) {
                availableVoices = SpeechSynthesis.getVoices();
            }

            // Stop previous speech if any
            if (SpeechSynthesis.speaking) {
                SpeechSynthesis.cancel();
            }

            try {
                // Create utterance and set its properties
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'ar'; // Force Arabic language
                utterance.rate = 0.9;  // Slightly slower for Arabic
                utterance.pitch = 1.0; // Normal pitch
                utterance.volume = 1.0; // Full volume
                
                // استخدام صوت عربي فقط
                let selectedVoice = null;
                
                if (availableVoices.length > 0) {
                    // البحث عن صوت باللهجة السعودية أولاً
                    selectedVoice = availableVoices.find(v => v.lang === 'ar-SA');
                    
                    // البحث عن أي لهجة عربية
                    if (!selectedVoice) {
                        selectedVoice = availableVoices.find(v => 
                            v.lang === 'ar' || v.lang.startsWith('ar-'));
                    }
                    
                    // البحث عن أي صوت يدعم العربية
                    if (!selectedVoice) {
                        selectedVoice = availableVoices.find(v => 
                            v.lang.includes('ar') || v.name.toLowerCase().includes('arab'));
                    }
                    
                        // في حالة عدم وجود أي صوت عربي، استخدم أي صوت متوفر
                    if (!selectedVoice) {
                        // محاولة استخدام أي صوت مناسب آخر (حتى غير عربي)
                        console.warn('لم يتم العثور على صوت عربي، سيتم استخدام الصوت الافتراضي');
                        
                        // اختيار أول صوت متوفر أفضل من عدم وجود صوت
                        if (availableVoices.length > 0) {
                            // استخدم الصوت الافتراضي للمتصفح
                            selectedVoice = availableVoices.find(v => v.default) || availableVoices[0];
                            console.log('استخدام الصوت الافتراضي:', selectedVoice.name);
                        } else {
                            console.warn('لا توجد أي أصوات متوفرة في المتصفح');
                        }
                    }
                    
                    // Apply the selected voice
                    if (selectedVoice) {
                        utterance.voice = selectedVoice;
                        console.log('Using voice:', selectedVoice.name, `(${selectedVoice.lang})`);
                    } else {
                        console.warn('No voice found, using browser default');
                    }
                } else {
                    console.warn('No voices available. Using browser default voice.');
                }
                
                // Setup event handlers
                utterance.onstart = () => {
                    speakingUtterance = utterance;
                    console.log('Speaking started');
                };
                
                utterance.onend = () => {
                    speakingUtterance = null;
                    console.log('Speaking ended');
                };
                
                utterance.onerror = (event) => {
                    console.error('Speech synthesis error:', event.error);
                    speakingUtterance = null;
                };
                
                // إضافة رسالة للمستخدم لمعرفة حالة التحدث
                const textToSpeak = text.substring(0, 500) + (text.length > 500 ? '...' : '');
                console.log('Starting speech with text:', textToSpeak.substring(0, 50) + (textToSpeak.length > 50 ? '...' : ''));
                
                // بدء التحدث مع معالجة أخطاء محتملة
                try {
                    SpeechSynthesis.speak(utterance);
                    
                    // للتأكد من أن التحدث بدأ فعلاً
                    setTimeout(() => {
                        if (!SpeechSynthesis.speaking) {
                            console.warn('التحدث لم يبدأ بشكل صحيح، قد لا يدعم المتصفح هذه الميزة');
                        }
                    }, 500);
                } catch (err) {
                    console.error('خطأ أثناء التحدث:', err);
                }
                
                return true; // Successfully started speaking
            } catch (err) {
                console.error('Error in speech synthesis:', err);
                alert('حدث خطأ في خدمة التحدث');
                return false;
            }
        };

         // Function to stop speaking
         const stopSpeaking = () => {
             if (SpeechSynthesis && SpeechSynthesis.speaking) {
                 SpeechSynthesis.cancel();
                 speakingUtterance = null;
                 console.log('Speaking stopped.');
             }
         };


        // Add click listener to messagesContainer to handle clicks on speak buttons
        messagesContainer.addEventListener('click', (event) => {
            // Check if the clicked element is a speak button or its icon
            const speakButtonTarget = event.target.closest('.speak-btn');
            
            if (!speakButtonTarget) return; // Not a speak button
            
            // Visual feedback - change icon briefly
            const icon = speakButtonTarget.querySelector('i');
            const originalClass = icon.className;
            
            // Find the message bubble containing this button
            const messageBubble = speakButtonTarget.closest('.message-bubble');
            if (!messageBubble) return;
            
            // Find the text content within the bubble (p tag)
            const textElement = messageBubble.querySelector('p');
            if (!textElement || !textElement.textContent) return;
            
            // If already speaking, stop it
            if (speakingUtterance && SpeechSynthesis.speaking) {
                // Stop speech and reset icon
                stopSpeaking();
                icon.className = originalClass;
            } else {
                // Start speaking and set active icon
                try {
                    // Change icon to show activity
                    icon.className = 'fas fa-volume-high';
                    
                    // Speak the content
                    const success = speakText(textElement.textContent);
                    
                    if (success) {
                        // Set an interval to check when speech ends and reset icon
                        let iconCheckInterval = setInterval(() => {
                            if (!SpeechSynthesis.speaking) {
                                // Speech ended, reset icon and clear interval
                                icon.className = originalClass;
                                clearInterval(iconCheckInterval);
                            }
                        }, 500); // Check every half second
                        
                        // Also set a maximum timeout (30 seconds) to avoid leaking intervals
                        setTimeout(() => {
                            if (iconCheckInterval) {
                                clearInterval(iconCheckInterval);
                                icon.className = originalClass;
                            }
                        }, 30000);
                    } else {
                        // Speech didn't start, reset icon
                        icon.className = originalClass;
                    }
                } catch (err) {
                    console.error('Error handling speech button:', err);
                    icon.className = originalClass; // Reset icon on error
                }
            }
        });

        // Load TTS preference from localStorage
        const storedTtsPreference = localStorage.getItem('ttsEnabled');
        if (storedTtsPreference === 'true') {
            ttsToggle.checked = true;
        }

        // Handle TTS toggle changes
        ttsToggle.addEventListener('change', () => {
            localStorage.setItem('ttsEnabled', ttsToggle.checked);
            // If turning off, stop any current speech
            if (!ttsToggle.checked && SpeechSynthesis.speaking) {
                stopSpeaking();
            }
        });

    } else {
        console.warn('Web Speech API (SpeechSynthesis) not supported in this browser.');
        // Hide TTS toggle if not supported
        if (ttsToggle) {
            ttsToggle.parentElement.style.display = 'none';
        }
    }

    // --- Initialize Models ---
    // Common models available on OpenRouter
    const availableModels = [
        { value: 'mistralai/mistral-7b-instruct', label: 'Mistral 7B' },
        { value: 'anthropic/claude-3-haiku', label: 'Claude 3 Haiku' },
        { value: 'google/gemini-pro', label: 'Gemini Pro' },
        { value: 'meta-llama/llama-3-8b-instruct', label: 'LLaMA 3 8B' },
        { value: 'google/gemma-7b-it', label: 'Gemma 7B' },
        { value: 'openai/gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
        { value: 'anthropic/claude-3-sonnet', label: 'Claude 3 Sonnet' }
    ];

    // Populate model dropdown
    modelSelect.innerHTML = ''; // Clear any existing options
    availableModels.forEach(model => {
        const option = document.createElement('option');
        option.value = model.value;
        option.textContent = model.label;
        modelSelect.appendChild(option);
    });

    // Load saved model preference from localStorage
    const savedModel = localStorage.getItem('selectedModel');
    if (savedModel && availableModels.some(model => model.value === savedModel)) {
        modelSelect.value = savedModel;
    }

    // Save model selection to localStorage when changed
    modelSelect.addEventListener('change', () => {
        localStorage.setItem('selectedModel', modelSelect.value);
    });

    // --- Load and Display Conversations ---
    async function loadConversations() {
        try {
            const response = await fetch('/api/conversations');
            if (!response.ok) {
                throw new Error('Failed to load conversations');
            }
            const conversations = await response.json();

            // Clear the conversations list
            while (conversationsList.firstChild) {
                conversationsList.removeChild(conversationsList.firstChild);
            }

            if (conversations.length === 0) {
                // No conversations to display
                const emptyState = document.createElement('div');
                emptyState.className = 'empty-state';
                emptyState.textContent = 'لا توجد محادثات سابقة';
                conversationsList.appendChild(emptyState);
            } else {
                // Display each conversation
                conversations.forEach(conversation => {
                    const conversationItem = document.createElement('div');
                    conversationItem.className = 'conversation-item';
                    if (conversation.id === currentConversationId) {
                        conversationItem.classList.add('active');
                    }

                    // Format date
                    const date = new Date(conversation.updated_at);
                    const formattedDate = new Intl.DateTimeFormat('ar-SA', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric'
                    }).format(date);

                    // Create a span for the title
                    const titleSpan = document.createElement('span');
                    titleSpan.textContent = conversation.title;
                    titleSpan.title = `${conversation.title} - ${formattedDate}`;

                    // Create action buttons container
                    const actionsDiv = document.createElement('div');
                    actionsDiv.className = 'conversation-actions';

                    // Edit title button
                    const editButton = document.createElement('button');
                    editButton.className = 'icon-button';
                    editButton.title = 'تعديل العنوان';
                    editButton.innerHTML = '<i class="fas fa-edit"></i>';
                    editButton.onclick = (e) => {
                        e.stopPropagation(); // Prevent loading the conversation
                        editConversationTitle(conversation.id, conversation.title);
                    };

                    // Delete button
                    const deleteButton = document.createElement('button');
                    deleteButton.className = 'icon-button';
                    deleteButton.title = 'حذف المحادثة';
                    deleteButton.innerHTML = '<i class="fas fa-trash-alt"></i>';
                    deleteButton.onclick = (e) => {
                        e.stopPropagation(); // Prevent loading the conversation
                        confirmDeleteConversation(conversation.id);
                    };

                    // Add buttons to actions div
                    actionsDiv.appendChild(editButton);
                    actionsDiv.appendChild(deleteButton);

                    // Add title and actions to conversation item
                    conversationItem.appendChild(titleSpan);
                    conversationItem.appendChild(actionsDiv);

                    // Set click handler for loading the conversation
                    conversationItem.addEventListener('click', () => {
                        loadConversation(conversation.id);
                    });

                    conversationsList.appendChild(conversationItem);
                });
            }
        } catch (error) {
            console.error('Error loading conversations:', error);
            // Show error state
            const errorState = document.createElement('div');
            errorState.className = 'empty-state';
            errorState.textContent = 'فشل تحميل المحادثات';
            conversationsList.appendChild(errorState);
        }
    }

    // --- Load a Single Conversation ---
    async function loadConversation(conversationId) {
        try {
            const response = await fetch(`/api/conversations/${conversationId}`);
            if (!response.ok) {
                throw new Error('Failed to load conversation');
            }
            const conversation = await response.json();

            // Update UI
            clearMessages();
            currentConversationId = conversationId;
            messages = conversation.messages.map(msg => ({
                role: msg.role,
                content: msg.content
            }));

            // Add messages to UI
            messages.forEach(msg => {
                addMessageToUI(msg.role, msg.content);
            });

            // Update active state in conversation list
            document.querySelectorAll('.conversation-item').forEach(item => {
                item.classList.remove('active');
                const itemTitleSpan = item.querySelector('span');
                if (itemTitleSpan && itemTitleSpan.textContent === conversation.title) {
                    item.classList.add('active');
                }
            });

            // Close sidebar on mobile after selecting a conversation
            if (window.innerWidth <= 768) {
                toggleSidebar();
            }

            // Scroll to bottom
            scrollToBottom();

            // Show regenerate button if there are messages
            if (messages.length > 0 && messages[messages.length - 1].role === 'assistant') {
                showRegenerateButton();
            } else {
                hideRegenerateButton();
            }
        } catch (error) {
            console.error('Error loading conversation:', error);
            alert('فشل تحميل المحادثة');
        }
    }

    // --- Edit Conversation Title ---
    function editConversationTitle(conversationId, currentTitle) {
        const newTitle = prompt('أدخل العنوان الجديد للمحادثة:', currentTitle);
        if (newTitle !== null && newTitle.trim() !== '') {
            updateConversationTitle(conversationId, newTitle.trim());
        }
    }

    // --- Update Conversation Title (API Call) ---
    async function updateConversationTitle(conversationId, newTitle) {
        try {
            const response = await fetch(`/api/conversations/${conversationId}/title`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ title: newTitle }),
            });

            if (!response.ok) {
                throw new Error('Failed to update conversation title');
            }

            // Reload the conversations list
            loadConversations();
        } catch (error) {
            console.error('Error updating conversation title:', error);
            alert('فشل تحديث عنوان المحادثة');
        }
    }

    // --- Confirm Delete Conversation ---
    function confirmDeleteConversation(conversationId) {
        confirmMessage.textContent = 'هل أنت متأكد من أنك تريد حذف هذه المحادثة؟';
        showConfirmModal(() => {
            deleteConversation(conversationId);
        });
    }

    // --- Delete Conversation (API Call) ---
    async function deleteConversation(conversationId) {
        try {
            const response = await fetch(`/api/conversations/${conversationId}`, {
                method: 'DELETE',
            });

            if (!response.ok) {
                throw new Error('Failed to delete conversation');
            }

            // If we deleted the current conversation, clear the UI
            if (conversationId === currentConversationId) {
                clearMessages();
                currentConversationId = null;
                messages = [];
                hideRegenerateButton();
            }

            // Reload the conversations list
            loadConversations();
        } catch (error) {
            console.error('Error deleting conversation:', error);
            alert('فشل حذف المحادثة');
        }
    }

    // --- Clear Messages UI ---
    function clearMessages() {
        messagesContainer.innerHTML = '';
        hideRegenerateButton();

        // Add welcome message
        addMessageToUI('assistant', WELCOME_MESSAGE_CONTENT);
    }

    // --- Add Message to UI ---
    function addMessageToUI(role, content) {
        const messageBubble = document.createElement('div');
        messageBubble.className = `message-bubble ${role === 'user' ? 'user-bubble' : 'ai-bubble'} fade-in`;

        const messageContent = document.createElement('p');
        messageContent.textContent = content;
        messageBubble.appendChild(messageContent);

        // For AI messages, add copy and TTS buttons
        if (role === 'assistant') {
            const messageActions = document.createElement('div');
            messageActions.className = 'message-actions';

            // Copy button
            const copyButton = document.createElement('button');
            copyButton.className = 'copy-btn';
            copyButton.title = 'نسخ';
            copyButton.innerHTML = '<i class="fas fa-copy"></i>';
            copyButton.addEventListener('click', () => {
                navigator.clipboard.writeText(content)
                    .then(() => {
                        // Show success feedback
                        copyButton.innerHTML = '<i class="fas fa-check"></i>';
                        setTimeout(() => {
                            copyButton.innerHTML = '<i class="fas fa-copy"></i>';
                        }, 2000);
                    })
                    .catch(err => {
                        console.error('Failed to copy text:', err);
                        copyButton.innerHTML = '<i class="fas fa-times"></i>';
                        setTimeout(() => {
                            copyButton.innerHTML = '<i class="fas fa-copy"></i>';
                        }, 2000);
                    });
            });

            // Speak button
            const speakButton = document.createElement('button');
            speakButton.className = 'speak-btn';
            speakButton.title = 'استماع';
            speakButton.innerHTML = '<i class="fas fa-volume-up"></i>';

            messageActions.appendChild(copyButton);
            messageActions.appendChild(speakButton);
            messageBubble.appendChild(messageActions);

            // If auto-TTS is enabled, speak this message automatically
            if (ttsToggle && ttsToggle.checked && window.speechSynthesis && typeof speakText === 'function') {
                setTimeout(() => {
                    speakText(content);
                }, 500); // Small delay to ensure UI is updated first
            }
        }

        messagesContainer.appendChild(messageBubble);
        scrollToBottom();
    }

    // --- Create Regenerate Button ---
    function createRegenerateButton() {
        // Check if the button already exists
        let regenerateButton = document.getElementById('regenerate-button');
        
        if (!regenerateButton) {
            regenerateButton = document.createElement('button');
            regenerateButton.id = 'regenerate-button';
            regenerateButton.innerHTML = '<i class="fas fa-redo"></i> إعادة توليد الرد';
            regenerateButton.addEventListener('click', handleRegenerate);
            
            // Insert after messages container
            messagesContainer.after(regenerateButton);
        }
        
        return regenerateButton;
    }

    // --- Show Regenerate Button ---
    function showRegenerateButton() {
        const regenerateButton = createRegenerateButton();
        regenerateButton.style.display = 'flex';
    }

    // --- Hide Regenerate Button ---
    function hideRegenerateButton() {
        const regenerateButton = document.getElementById('regenerate-button');
        if (regenerateButton) {
            regenerateButton.style.display = 'none';
        }
    }

    // --- Handle Regenerate Button Click ---
    async function handleRegenerate() {
        if (!currentConversationId || isTyping) {
            return;
        }

        isTyping = true;
        
        try {
            // Remove the last AI message from UI
            if (messages.length > 0 && messages[messages.length - 1].role === 'assistant') {
                const lastMessage = messagesContainer.lastChild;
                if (lastMessage) {
                    messagesContainer.removeChild(lastMessage);
                }
                
                // Also remove from our messages array
                messages.pop();
            }

            // Add typing indicator
            addTypingIndicator();

            // Prepare API call parameters
            const requestBody = {
                conversation_id: currentConversationId,
                model: modelSelect.value,
                temperature: parseFloat(temperatureSlider.value),
                max_tokens: parseInt(maxTokensInput.value, 10)
            };

            // Make the API call
            const response = await fetch('/api/regenerate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody),
            });

            // Remove typing indicator
            removeTypingIndicator();

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'فشل إعادة توليد الرد');
            }

            const data = await response.json();
            
            // Add the new AI message to UI and messages array
            addMessageToUI('assistant', data.content);
            messages.push({ role: 'assistant', content: data.content });
            
            // Show regenerate button
            showRegenerateButton();
            
        } catch (error) {
            console.error('Error regenerating response:', error);
            
            // Show error in UI
            addMessageToUI('assistant', `خطأ: ${error.message || 'فشل إعادة توليد الرد'}`);
            
        } finally {
            isTyping = false;
        }
    }

    // --- Add Typing Indicator ---
    function addTypingIndicator() {
        const typingIndicator = document.createElement('div');
        typingIndicator.className = 'message-bubble ai-bubble typing-indicator-bubble';
        typingIndicator.id = 'typing-indicator';
        
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement('span');
            dot.className = 'typing-dot';
            indicator.appendChild(dot);
        }
        
        typingIndicator.appendChild(indicator);
        messagesContainer.appendChild(typingIndicator);
        scrollToBottom();
    }

    // --- Remove Typing Indicator ---
    function removeTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    // --- Send Message ---
    async function sendMessage() {
        const userMessage = messageInput.value.trim();
        if (!userMessage || isTyping) {
            return;
        }

        // Check network status first
        if (!navigator.onLine) {
            console.log("Offline mode detected. Using frontend offline message");
            // Handle the offline case in the UI directly
            addMessageToUI('user', userMessage);
            messages.push({ role: 'user', content: userMessage });
            
            // Add offline response
            addMessageToUI('assistant', FRONTEND_OFFLINE_MESSAGE);
            messages.push({ role: 'assistant', content: FRONTEND_OFFLINE_MESSAGE });
            
            // Clear input field
            messageInput.value = '';
            adjustInputHeight();
            return;
        }

        // Preliminary check for predefined responses
        const predefinedResponse = checkPredefinedResponse(userMessage);
        if (predefinedResponse) {
            console.log("Using predefined response");
            
            // Show user message
            addMessageToUI('user', userMessage);
            messages.push({ role: 'user', content: userMessage });
            
            // Show predefined response
            addMessageToUI('assistant', predefinedResponse);
            messages.push({ role: 'assistant', content: predefinedResponse });
            
            // If this is a new conversation, we need to create it
            if (!currentConversationId) {
                // We'll create the conversation with the backend on next non-predefined message
                // This saves API calls for quick predefined responses
            } else {
                // For existing conversations, we should add these messages to the server
                // This is a nice-to-have but not vital, as the conversation exists already
                // Could implement: sendMessagesToServer(currentConversationId, userMessage, predefinedResponse);
            }
            
            // Clear input field and adjust
            messageInput.value = '';
            adjustInputHeight();
            
            // Show regenerate button
            showRegenerateButton();
            
            return;
        }

        // Proceed with normal API call
        isTyping = true;
        
        // Add user message to UI and clear input
        addMessageToUI('user', userMessage);
        messageInput.value = '';
        adjustInputHeight();
        
        // Add typing indicator
        addTypingIndicator();
        
        // Update messages array
        messages.push({ role: 'user', content: userMessage });
        
        try {
            // Prepare API call
            const requestBody = {
                history: messages,
                conversation_id: currentConversationId,
                model: modelSelect.value,
                temperature: parseFloat(temperatureSlider.value),
                max_tokens: parseInt(maxTokensInput.value, 10)
            };
            
            // Make API call
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody),
            });
            
            // Remove typing indicator
            removeTypingIndicator();
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'فشل إرسال الرسالة');
            }
            
            const data = await response.json();
            
            // Update conversation ID for new conversations
            if (!currentConversationId && data.id) {
                currentConversationId = data.id;
                // Refresh conversation list
                loadConversations();
            }
            
            // Add AI response to UI and messages array
            addMessageToUI('assistant', data.content);
            messages.push({ role: 'assistant', content: data.content });
            
            // Show regenerate button
            showRegenerateButton();
            
        } catch (error) {
            console.error('Error sending message:', error);
            
            // Remove typing indicator
            removeTypingIndicator();
            
            // Show error in UI
            addMessageToUI('assistant', `خطأ: ${error.message || 'فشل إرسال الرسالة'}`);
            
        } finally {
            isTyping = false;
        }
    }

    // --- Utility Functions ---
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function adjustInputHeight() {
        messageInput.style.height = 'auto';
        const newHeight = Math.min(messageInput.scrollHeight, 200); // Max height 200px
        messageInput.style.height = `${newHeight}px`;
    }

    function toggleSidebar() {
        settingsSidebar.classList.toggle('show');
    }

    function showConfirmModal(callback) {
        confirmationCallback = callback;
        confirmModal.classList.add('show');
    }

    function hideConfirmModal() {
        confirmModal.classList.remove('show');
        confirmationCallback = null;
    }

    // --- Event Listeners ---
    // Send button click
    sendButton.addEventListener('click', sendMessage);

    // Message input key press (Enter to send, Shift+Enter for new line)
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
        // Allow Shift+Enter to add a new line
    });

    // Auto-adjust input height as user types
    messageInput.addEventListener('input', adjustInputHeight);

    // New conversation button
    newConversationButton.addEventListener('click', () => {
        clearMessages();
        currentConversationId = null;
        messages = [{ role: 'assistant', content: WELCOME_MESSAGE_CONTENT }]; // Keep welcome message
        hideRegenerateButton();
        // Close sidebar on mobile
        if (window.innerWidth <= 768) {
            toggleSidebar();
        }
    });

    // Temperature slider change
    temperatureSlider.addEventListener('input', () => {
        temperatureValueSpan.textContent = temperatureSlider.value;
        localStorage.setItem('temperature', temperatureSlider.value);
    });

    // Max tokens input change
    maxTokensInput.addEventListener('change', () => {
        localStorage.setItem('maxTokens', maxTokensInput.value);
    });

    // Dark mode toggle
    darkModeToggle.addEventListener('change', () => {
        document.body.classList.toggle('dark-mode', darkModeToggle.checked);
        localStorage.setItem('darkModeEnabled', darkModeToggle.checked);
    });

    // Toggle sidebar button
    toggleSidebarButton.addEventListener('click', toggleSidebar);
    mobileMenuButton.addEventListener('click', toggleSidebar);
    mobileSettingsButton.addEventListener('click', toggleSidebar);

    // Confirm modal buttons
    confirmOkButton.addEventListener('click', () => {
        if (confirmationCallback) {
            confirmationCallback();
        }
        hideConfirmModal();
    });

    confirmCancelButton.addEventListener('click', hideConfirmModal);

    // Network status listeners
    window.addEventListener('online', function() {
        offlineIndicator.classList.remove('visible');
    });

    window.addEventListener('offline', function() {
        offlineIndicator.classList.add('visible');
    });

    // --- Initialization ---
    // Load saved settings from localStorage
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

    // Check initial network status
    if (!navigator.onLine) {
        offlineIndicator.classList.add('visible');
    }

    // Initial UI setup
    clearMessages(); // This adds the welcome message
    loadConversations();
    messageInput.focus();
});

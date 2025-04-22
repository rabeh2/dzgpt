const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const chatArea = document.getElementById('chat-area');
const conversationsList = document.getElementById('conversations-list');
const modelSelect = document.getElementById('model-select');
const settingsButton = document.getElementById('settings-button');
const settingsSidebar = document.getElementById('settings-sidebar');
const darkModeToggle = document.getElementById('dark-mode-toggle');
const recordButton = document.getElementById('record-button');
const inputArea = document.getElementById('input-area');
const offlineIndicator = document.createElement('div');
let currentConversationId = null;
let isRecording = false;
let recognition = null;

document.addEventListener('DOMContentLoaded', () => {
    initializeSpeechRecognition();
    loadConversations();
    applyDarkMode();
    setupEventListeners();
    loadAnalytics();
});

function initializeSpeechRecognition() {
    if ('webkitSpeechRecognition' in window) {
        recognition = new webkitSpeechRecognition();
        recognition.lang = 'ar-SA';
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            messageInput.value = transcript;
            stopRecording();
        };
        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            stopRecording();
            alert('فشل التعرف على الصوت، حاول مرة أخرى.');
        };
    } else {
        recordButton.style.display = 'none';
    }
}

function setupEventListeners() {
    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    messageInput.addEventListener('input', adjustInputHeight);
    settingsButton.addEventListener('click', toggleSettings);
    darkModeToggle.addEventListener('change', toggleDarkMode);
    recordButton.addEventListener('click', () => isRecording ? stopRecording() : startRecording());
    window.addEventListener('online', () => offlineIndicator.style.display = 'none');
    window.addEventListener('offline', () => {
        offlineIndicator.style.display = 'block';
        offlineIndicator.textContent = 'غير متصل';
        offlineIndicator.className = 'offline-indicator';
        inputArea.appendChild(offlineIndicator);
    });
}

async function loadConversations() {
    try {
        const response = await fetch('/api/conversations');
        const conversations = await response.json();
        conversationsList.innerHTML = '';
        conversations.forEach(conv => {
            const convElement = document.createElement('div');
            convElement.className = 'conversation-item';
            convElement.dataset.id = conv.id;
            convElement.innerHTML = `
                <span>${conv.title}</span>
                <div class="conversation-actions">
                    <button class="icon-button edit-button" title="تعديل"><i class="fas fa-edit"></i></button>
                    <button class="icon-button delete-button" title="حذف"><i class="fas fa-trash"></i></button>
                </div>
            `;
            convElement.addEventListener('click', () => loadConversation(conv.id));
            convElement.querySelector('.edit-button').addEventListener('click', (e) => {
                e.stopPropagation();
                editConversation(conv.id, conv.title);
            });
            convElement.querySelector('.delete-button').addEventListener('click', (e) => {
                e.stopPropagation();
                deleteConversation(conv.id);
            });
            conversationsList.appendChild(convElement);
        });
    } catch (error) {
        console.error('Error loading conversations:', error);
        alert('فشل تحميل المحادثات');
    }
}

async function loadConversation(id) {
    try {
        currentConversationId = id;
        const response = await fetch(`/api/conversations`);
        const conversations = await response.json();
        const conversation = conversations.find(conv => conv.id === id);
        if (!conversation) throw new Error('Conversation not found');
        chatArea.innerHTML = '';
        conversation.messages.forEach(msg => displayMessage(msg));
        document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.toggle('active', item.dataset.id === id);
        });
        chatArea.scrollTop = chatArea.scrollHeight;
    } catch (error) {
        console.error('Error loading conversation:', error);
        alert('فشل تحميل المحادثة');
    }
}

async function sendMessage() {
    const content = messageInput.value.trim();
    if (!content) return;

    const history = Array.from(chatArea.children)
        .filter(child => child.classList.contains('message'))
        .map(child => ({
            role: child.classList.contains('user-message') ? 'user' : 'assistant',
            content: child.querySelector('.message-content').textContent
        }));

    history.push({ role: 'user', content });
    displayMessage({ role: 'user', content, created_at: new Date().toISOString() });
    messageInput.value = '';
    adjustInputHeight();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: currentConversationId,
                history,
                model: modelSelect.value
            })
        });
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        displayMessage({ role: 'assistant', content: data.content, created_at: new Date().toISOString() });
        if (data.new_conversation_id) {
            currentConversationId = data.new_conversation_id;
            await loadConversations();
            await loadConversation(currentConversationId);
        }
        if (data.suggestions && data.suggestions.length > 0) {
            displaySuggestions(data.suggestions);
        }
        chatArea.scrollTop = chatArea.scrollHeight;
    } catch (error) {
        console.error('Error sending message:', error);
        displayMessage({ role: 'assistant', content: 'فشل إرسال الرسالة، حاول مرة أخرى.' });
    }
}

function displayMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${message.role === 'user' ? 'user-message' : 'assistant-message'}`;
    messageElement.innerHTML = `
        <div class="message-content">${message.content}</div>
        <div class="message-actions">
            <button class="icon-button copy-button" title="نسخ"><i class="fas fa-copy"></i></button>
            <button class="icon-button speak-button" title="تحدث"><i class="fas fa-volume-up"></i></button>
        </div>
    `;
    messageElement.querySelector('.copy-button').addEventListener('click', () => {
        navigator.clipboard.writeText(message.content);
        alert('تم نسخ النص!');
    });
    messageElement.querySelector('.speak-button').addEventListener('click', () => speakText(message.content));
    chatArea.appendChild(messageElement);
}

function displaySuggestions(suggestions) {
    let suggestionsContainer = document.getElementById('suggestions-container');
    if (!suggestionsContainer) {
        suggestionsContainer = document.createElement('div');
        suggestionsContainer.id = 'suggestions-container';
        inputArea.appendChild(suggestionsContainer);
    }
    suggestionsContainer.innerHTML = '';
    suggestions.forEach(suggestion => {
        const button = document.createElement('button');
        button.className = 'suggestion-button';
        button.textContent = suggestion;
        button.addEventListener('click', () => {
            messageInput.value = suggestion;
            sendMessage();
        });
        suggestionsContainer.appendChild(button);
    });
}

async function editConversation(id, currentTitle) {
    const newTitle = prompt('أدخل عنوان المحادثة الجديد:', currentTitle);
    if (newTitle && newTitle.trim()) {
        try {
            const response = await fetch(`/api/conversations/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle.trim() })
            });
            const data = await response.json();
            if (data.error) throw new Error(data.error);
            await loadConversations();
        } catch (error) {
            console.error('Error updating conversation:', error);
            alert('فشل تحديث المحادثة');
        }
    }
}

async function deleteConversation(id) {
    if (confirm('هل أنت متأكد من حذف المحادثة؟')) {
        try {
            const response = await fetch(`/api/conversations/${id}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();
            if (data.error) throw new Error(data.error);
            await loadConversations();
            if (currentConversationId === id) {
                currentConversationId = null;
                chatArea.innerHTML = '';
            }
        } catch (error) {
            console.error('Error deleting conversation:', error);
            alert('فشل حذف المحادثة');
        }
    }
}

async function loadAnalytics() {
    try {
        const response = await fetch('/api/conversations/analytics');
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        const content = `
            <p>إجمالي المحادثات: ${data.total_conversations}</p>
            <p>إجمالي الرسائل: ${data.total_messages}</p>
            <p>متوسط الرسائل لكل محادثة: ${data.avg_messages_per_conversation}</p>
            <p>المواضيع الشائعة: ${data.common_topics.join(', ')}</p>
        `;
        document.getElementById('analytics-content').innerHTML = content;
    } catch (error) {
        console.error('Error loading analytics:', error);
        document.getElementById('analytics-content').innerHTML = '<p>فشل تحميل الإحصائيات</p>';
    }
}

function adjustInputHeight() {
    messageInput.style.height = 'auto';
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 150)}px`;
}

function toggleSettings() {
    settingsSidebar.classList.toggle('open');
}

function toggleDarkMode() {
    document.body.classList.toggle('dark-mode');
    localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
}

function applyDarkMode() {
    if (localStorage.getItem('darkMode') === 'true') {
        document.body.classList.add('dark-mode');
        darkModeToggle.checked = true;
    }
}

function startRecording() {
    if (recognition && !isRecording) {
        recognition.start();
        isRecording = true;
        sendButton.innerHTML = '<i class="fas fa-stop"></i>';
        recordButton.innerHTML = '<i class="fas fa-microphone-slash"></i>';
    }
}

function stopRecording() {
    if (recognition && isRecording) {
        recognition.stop();
        isRecording = false;
        sendButton.innerHTML = '<i class="fas fa-paper-plane"></i>';
        recordButton.innerHTML = '<i class="fas fa-microphone"></i>';
    }
}

function speakText(text) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'ar-SA';
        speechSynthesis.speak(utterance);
    } else {
        alert('التحدث غير مدعوم في هذا المتصفح.');
    }
}

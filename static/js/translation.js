// وظائف الترجمة
document.addEventListener('DOMContentLoaded', function() {
    // عناصر واجهة المستخدم
    const sourceTextarea = document.getElementById('source-text');
    const targetTextarea = document.getElementById('target-text');
    const sourceLangSelect = document.getElementById('source-lang');
    const targetLangSelect = document.getElementById('target-lang');
    // const providerSelect = document.getElementById('translation-provider'); // لم نعد نستخدم اختيار المزود
    const translateBtn = document.getElementById('translate-btn');
    const swapLangsBtn = document.getElementById('swap-languages');
    const clearSourceBtn = document.getElementById('clear-source');
    const copySourceBtn = document.getElementById('copy-source');
    const copyTargetBtn = document.getElementById('copy-target');
    const listenSourceBtn = document.getElementById('listen-source');
    const listenTargetBtn = document.getElementById('listen-target');
    const infoBox = document.getElementById('translation-info');
    
    // تهيئة اللغات المدعومة
    fetchSupportedLanguages();

    // المؤشر للترجمة قيد التقدم
    let isTranslating = false;
    
    // أحداث النقر
    translateBtn.addEventListener('click', translateText);
    swapLangsBtn.addEventListener('click', swapLanguages);
    clearSourceBtn.addEventListener('click', clearSourceText);
    copySourceBtn.addEventListener('click', () => copyText(sourceTextarea));
    copyTargetBtn.addEventListener('click', () => copyText(targetTextarea));
    listenSourceBtn.addEventListener('click', () => speakText(sourceTextarea.value, sourceLangSelect.value));
    listenTargetBtn.addEventListener('click', () => speakText(targetTextarea.value, targetLangSelect.value));
    
    // توفير القدرة على الترجمة بالضغط على Ctrl+Enter
    sourceTextarea.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === 'Enter') {
            translateText();
        }
    });
    
    // جلب اللغات المدعومة من الخادم
    function fetchSupportedLanguages() {
        showInfo('جاري تحميل اللغات المدعومة...', 'info');
        
        fetch('/api/translation/languages')
            .then(response => {
                if (!response.ok) throw new Error('فشل في تحميل اللغات المدعومة');
                return response.json();
            })
            .then(languages => {
                populateLanguageSelects(languages);
                showInfo('تم تحميل اللغات المدعومة', 'success', true);
            })
            .catch(error => {
                console.error('Error fetching languages:', error);
                showInfo('حدث خطأ أثناء تحميل اللغات المدعومة', 'error');
            });
    }
    
    // تعبئة قوائم اللغات
    function populateLanguageSelects(languages) {
        // إفراغ القوائم الحالية مع الاحتفاظ بخيار اكتشاف تلقائي في قائمة اللغة المصدر
        while (sourceLangSelect.options.length > 1) {
            sourceLangSelect.remove(1);
        }
        
        while (targetLangSelect.options.length > 0) {
            targetLangSelect.remove(0);
        }
        
        // إضافة اللغات المدعومة
        languages.forEach(lang => {
            const sourceOption = document.createElement('option');
            sourceOption.value = lang.code;
            sourceOption.textContent = lang.name;
            
            const targetOption = document.createElement('option');
            targetOption.value = lang.code;
            targetOption.textContent = lang.name;
            
            sourceLangSelect.appendChild(sourceOption);
            targetLangSelect.appendChild(targetOption);
        });
        
        // تعيين العربية كلغة افتراضية للهدف
        targetLangSelect.value = 'ar';
    }
    
    // وظيفة الترجمة
    function translateText() {
        const sourceText = sourceTextarea.value.trim();
        const sourceLang = sourceLangSelect.value;
        const targetLang = targetLangSelect.value;
        
        if (!sourceText) {
            showInfo('يرجى إدخال نص للترجمة', 'error');
            return;
        }
        
        if (isTranslating) {
            showInfo('الترجمة قيد التنفيذ، يرجى الانتظار...', 'info');
            return;
        }
        
        isTranslating = true;
        translateBtn.disabled = true;
        translateBtn.classList.add('translating');
        showInfo('جاري الترجمة...', 'info');
        
        fetch('/api/translation/translate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                text: sourceText,
                source_lang: sourceLang,
                target_lang: targetLang
            })
        })
        .then(response => {
            if (!response.ok) throw new Error('فشل في طلب الترجمة');
            return response.json();
        })
        .then(data => {
            if (data.success) {
                targetTextarea.value = data.translated_text;
                showInfo(`تمت الترجمة بنجاح - من: ${getLanguageName(data.source_language)} إلى: ${getLanguageName(data.target_language)} - المزود: ${data.provider}`, 'success');
            } else {
                showInfo(`فشل في الترجمة: ${data.error}`, 'error');
            }
        })
        .catch(error => {
            console.error('Translation error:', error);
            showInfo(`حدث خطأ أثناء الترجمة: ${error.message}`, 'error');
        })
        .finally(() => {
            isTranslating = false;
            translateBtn.disabled = false;
            translateBtn.classList.remove('translating');
        });
    }
    
    // تبديل اللغات المصدر والهدف
    function swapLanguages() {
        // لا يمكن التبديل إذا كانت اللغة المصدر هي "auto"
        if (sourceLangSelect.value === 'auto') {
            showInfo('لا يمكن تبديل اللغات عندما يكون المصدر "اكتشاف تلقائي"', 'error', true);
            return;
        }
        
        // تبديل اللغات
        const tempLang = sourceLangSelect.value;
        sourceLangSelect.value = targetLangSelect.value;
        targetLangSelect.value = tempLang;
        
        // تبديل النصوص
        const tempText = sourceTextarea.value;
        sourceTextarea.value = targetTextarea.value;
        targetTextarea.value = tempText;
        
        showInfo('تم تبديل اللغات والنصوص', 'success', true);
    }
    
    // مسح النص المصدر
    function clearSourceText() {
        sourceTextarea.value = '';
        sourceTextarea.focus();
        showInfo('تم مسح النص المصدر', 'info', true);
    }
    
    // نسخ النص
    function copyText(textarea) {
        if (!textarea.value) {
            showInfo('لا يوجد نص للنسخ', 'error', true);
            return;
        }
        
        textarea.select();
        document.execCommand('copy');
        
        // إلغاء تحديد النص
        window.getSelection().removeAllRanges();
        
        showInfo('تم نسخ النص إلى الحافظة', 'success', true);
    }
    
    // قراءة النص باستخدام SpeechSynthesis API
    function speakText(text, languageCode) {
        if (!text) {
            showInfo('لا يوجد نص للقراءة', 'error', true);
            return;
        }
        
        if ('speechSynthesis' in window) {
            // إيقاف أي قراءة سابقة
            window.speechSynthesis.cancel();
            
            const utterance = new SpeechSynthesisUtterance(text);
            
            // تعيين اللغة
            if (languageCode && languageCode !== 'auto') {
                utterance.lang = languageCode;
            }
            
            // محاولة اختيار صوت مناسب للغة
            const voices = window.speechSynthesis.getVoices();
            const languageVoices = voices.filter(voice => {
                // تغيير العربية لتطابق نسق ويندوز مثلًا
                const langCode = languageCode === 'ar' ? 'ar-SA' : languageCode;
                return voice.lang.includes(langCode) || 
                      (languageCode === 'ar' && voice.lang.includes('ar'));
            });
            
            if (languageVoices.length > 0) {
                utterance.voice = languageVoices[0];
            }
            
            window.speechSynthesis.speak(utterance);
            showInfo('جاري قراءة النص...', 'info', true);
        } else {
            showInfo('ميزة تحويل النص إلى كلام غير مدعومة في هذا المتصفح', 'error', true);
        }
    }
    
    // عرض معلومات في صندوق المعلومات
    function showInfo(message, type = 'info', autoHide = false) {
        infoBox.textContent = message;
        infoBox.className = 'info-box';
        
        switch(type) {
            case 'success':
                infoBox.classList.add('success-info');
                break;
            case 'error':
                infoBox.classList.add('error-info');
                break;
            default:
                // النمط الافتراضي (info)
                break;
        }
        
        infoBox.style.display = 'block';
        
        // إخفاء تلقائي بعد 5 ثوانٍ للمعلومات غير المهمة
        if (autoHide) {
            setTimeout(() => {
                infoBox.style.display = 'none';
            }, 5000);
        }
    }
    
    // الحصول على اسم اللغة من رمزها
    function getLanguageName(code) {
        const languageOption = [...sourceLangSelect.options, ...targetLangSelect.options]
            .find(option => option.value === code);
        
        return languageOption ? languageOption.textContent : code;
    }
    
    // عرض حالة افتراضية
    showInfo('مرحبًا بك في خدمة الترجمة! اكتب النص الذي ترغب في ترجمته.', 'info');
});

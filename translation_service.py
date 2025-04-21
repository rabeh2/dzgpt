import requests
import logging
import os
import json

# إعداد السجل للخطأ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# خدمة الترجمة
class TranslationService:
    def __init__(self):
        # القائمة الثابتة من اللغات المدعومة
        self.supported_languages = {
            'ar': 'العربية',
            'en': 'الإنجليزية',
            'fr': 'الفرنسية',
            'es': 'الإسبانية',
            'de': 'الألمانية',
            'it': 'الإيطالية',
            'ru': 'الروسية',
            'zh': 'الصينية',
            'ja': 'اليابانية',
            'ko': 'الكورية',
            'tr': 'التركية',
            'fa': 'الفارسية',
            'ur': 'الأردية',
            'hi': 'الهندية',
            'pt': 'البرتغالية',
            'nl': 'الهولندية',
            'sw': 'السواحيلية',
            'he': 'العبرية'
        }
        
        # عنوان API لخدمة OpenAI - سنستخدمها كمحرك ترجمة
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        
    def get_supported_languages(self):
        """الحصول على اللغات المدعومة بتنسيق مناسب للعرض"""
        return [{"code": code, "name": name} for code, name in self.supported_languages.items()]
    
    def translate_text(self, text, source_lang='auto', target_lang='ar', provider=None):
        """
        ترجمة النص إلى اللغة المستهدفة باستخدام نموذج ذكاء اصطناعي
        
        المعلمات:
            text (str): النص المراد ترجمته
            source_lang (str): رمز لغة المصدر (افتراضيًا: auto للكشف التلقائي)
            target_lang (str): رمز اللغة المستهدفة (افتراضيًا: ar للعربية)
            provider (str): محرك الترجمة (غير مستخدم حاليًا)
            
        الإرجاع:
            dict: قاموس يحتوي على النص المترجم وتفاصيل الترجمة
        """
        try:
            if not text.strip():
                return {"success": False, "error": "النص فارغ", "translated_text": ""}

            if target_lang not in self.supported_languages and target_lang != 'auto':
                return {"success": False, "error": f"اللغة {target_lang} غير مدعومة", "translated_text": ""}
            
            # تحديد اللغة المصدر واللغة الهدف للاستخدام في الدليل
            source_lang_name = "اللغة المناسبة" if source_lang == 'auto' else self.supported_languages.get(source_lang, source_lang)
            target_lang_name = self.supported_languages.get(target_lang, target_lang)
            
            # إنشاء رسالة للنموذج اللغوي
            prompt = f"""ترجم النص التالي من {source_lang_name} إلى {target_lang_name}. 
            أرجو تقديم الترجمة فقط بدون أي تفسيرات أو مقدمات أو توضيحات.
            
            النص: {text}
            
            الترجمة:"""
            
            # باستخدام OpenRouter
            translated_text = ""
            provider_used = ""
            
            if self.openrouter_api_key:
                try:
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.openrouter_api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "mistralai/mistral-7b-instruct",  # نموذج أصغر وأسرع
                            "messages": [
                                {"role": "system", "content": "أنت مترجم محترف ودقيق."},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.3, 
                            "max_tokens": 1000
                        },
                        timeout=10  # تحديد وقت للتنفيذ
                    )
                    
                    response.raise_for_status()
                    result = response.json()
                    
                    if 'choices' in result and len(result['choices']) > 0 and 'message' in result['choices'][0]:
                        translated_text = result['choices'][0]['message']['content'].strip()
                        provider_used = "OpenRouter (Mistral)"
                    else:
                        logger.error("OpenRouter response format unexpected")
                        # سننتقل إلى استخدام Gemini
                except Exception as e:
                    logger.error(f"OpenRouter translation error: {str(e)}")
                    # سننتقل إلى استخدام Gemini
            
            # استخدام Gemini كبديل
            if not translated_text and self.gemini_api_key:
                try:
                    response = requests.post(
                        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}",
                        headers={"Content-Type": "application/json"},
                        json={
                            "contents": [{
                                "role": "user",
                                "parts": [{"text": prompt}]
                            }],
                            "generationConfig": {
                                "temperature": 0.2,
                                "maxOutputTokens": 1000
                            }
                        },
                        timeout=10
                    )
                    
                    response.raise_for_status()
                    result = response.json()
                    
                    if 'candidates' in result and len(result['candidates']) > 0:
                        candidate = result['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            parts = candidate['content']['parts']
                            if parts and 'text' in parts[0]:
                                translated_text = parts[0]['text'].strip()
                                provider_used = "Gemini"
                    
                    if not translated_text:
                        logger.error(f"Unexpected Gemini response format: {json.dumps(result)}")
                except Exception as e:
                    logger.error(f"Gemini translation error: {str(e)}")
                
            # استخدام ترجمة احتياطية بسيطة إذا فشلت كل المحاولات
            if not translated_text:
                if source_lang == target_lang:
                    translated_text = text  # إرجاع النص الأصلي إذا كانت اللغتان متطابقتان
                    provider_used = "Direct"
                else:
                    # محاولة أخيرة
                    try:
                        # استخدام ترجمة بسيطة يدوية لبعض العبارات الشائعة
                        common_phrases = {
                            "Hello": "مرحبا", 
                            "Thank you": "شكرا لك",
                            "Yes": "نعم",
                            "No": "لا",
                            "Good morning": "صباح الخير",
                            "Good evening": "مساء الخير"
                        }
                        
                        if text in common_phrases and target_lang == 'ar':
                            translated_text = common_phrases[text]
                            provider_used = "Fallback"
                        else:
                            return {
                                "success": False, 
                                "error": "فشلت جميع محاولات الترجمة", 
                                "translated_text": "",
                                "source_language": source_lang,
                                "target_language": target_lang,
                                "original_text": text
                            }
                    except Exception as e:
                        logger.error(f"Fallback translation error: {str(e)}")
                        return {
                            "success": False, 
                            "error": str(e),
                            "translated_text": "", 
                            "source_language": source_lang,
                            "target_language": target_lang,
                            "original_text": text
                        }
            
            return {
                "success": True,
                "translated_text": translated_text,
                "source_language": source_lang,
                "target_language": target_lang,
                "original_text": text,
                "provider": provider_used
            }
            
        except Exception as e:
            logger.error(f"خطأ في الترجمة: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "translated_text": "",
                "original_text": text,
                "source_language": source_lang,
                "target_language": target_lang
            }
    
    def detect_language(self, text):
        """
        الكشف عن لغة النص باستخدام نموذج الذكاء الاصطناعي
        
        المعلمات:
            text (str): النص المراد الكشف عن لغته
            
        الإرجاع:
            str: رمز اللغة المكتشفة أو 'unknown' في حالة الفشل
        """
        try:
            if not text.strip():
                return "unknown"
            
            prompt = "اكتشف لغة النص التالي وأعط الرمز فقط (مثل 'ar' للعربية، 'en' للإنجليزية، إلخ.) دون أي تفسير:\n\n" + text
            
            lang_code = "unknown"  # القيمة الافتراضية
            
            # محاولة استخدام OpenRouter أولاً
            if self.openrouter_api_key:
                try:
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.openrouter_api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "mistralai/mistral-7b-instruct",
                            "messages": [
                                {"role": "system", "content": "أنت خبير في اكتشاف اللغات. أجب برمز اللغة فقط مثل 'ar' أو 'en'."},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.1,
                            "max_tokens": 10
                        },
                        timeout=5
                    )
                    
                    response.raise_for_status()
                    result = response.json()
                    
                    if 'choices' in result and len(result['choices']) > 0 and 'message' in result['choices'][0]:
                        detected = result['choices'][0]['message']['content'].strip().lower()
                        
                        # استخراج رمز اللغة من الإجابة
                        for code in self.supported_languages.keys():
                            if code in detected:
                                lang_code = code
                                break
                        
                        # إذا كانت الإجابة قصيرة (2-3 أحرف)، فمن المحتمل أنها رمز لغة
                        if len(detected) <= 3 and len(detected) >= 2:
                            lang_code = detected
                except Exception as e:
                    logger.error(f"OpenRouter language detection error: {str(e)}")
            
            # استخدام Gemini كبديل
            if lang_code == "unknown" and self.gemini_api_key:
                try:
                    response = requests.post(
                        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}",
                        headers={"Content-Type": "application/json"},
                        json={
                            "contents": [{
                                "role": "user",
                                "parts": [{"text": prompt}]
                            }],
                            "generationConfig": {
                                "temperature": 0.1,
                                "maxOutputTokens": 10
                            }
                        },
                        timeout=5
                    )
                    
                    response.raise_for_status()
                    result = response.json()
                    
                    if 'candidates' in result and len(result['candidates']) > 0:
                        candidate = result['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            parts = candidate['content']['parts']
                            if parts and 'text' in parts[0]:
                                detected = parts[0]['text'].strip().lower()
                                
                                # استخراج رمز اللغة من الإجابة
                                for code in self.supported_languages.keys():
                                    if code in detected:
                                        lang_code = code
                                        break
                                
                                # إذا كانت الإجابة قصيرة، فمن المحتمل أنها رمز لغة
                                if len(detected) <= 3 and len(detected) >= 2:
                                    lang_code = detected
                except Exception as e:
                    logger.error(f"Gemini language detection error: {str(e)}")
            
            # محاولة تحليل النص يدويًا في حالة الفشل
            if lang_code == "unknown":
                # اكتشاف بسيط للغة بناءً على الأحرف
                arabic_chars = len([c for c in text if '\u0600' <= c <= '\u06FF'])
                english_chars = len([c for c in text if 'a' <= c.lower() <= 'z'])
                
                if arabic_chars > len(text) * 0.3:
                    lang_code = 'ar'
                elif english_chars > len(text) * 0.3:
                    lang_code = 'en'
            
            return lang_code
            
        except Exception as e:
            logger.error(f"خطأ في الكشف عن اللغة: {str(e)}")
            return "unknown"

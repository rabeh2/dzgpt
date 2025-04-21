# ملف: app.py

import os
import logging
import requests
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
# استيراد models هنا أو داخل الدوال التي تستخدمها
# من المستحسن استيرادها داخل الدوال لتجنب مشاكل الاستيراد الدائري
# from models import Conversation, Message

# إعداد التسجيل (Logging)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- فئة Base لـ SQLAlchemy models ---
class Base(DeclarativeBase):
    pass

# --- تهيئة Flask و SQLAlchemy ---
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "yasmin-gpt-secret-key")

# تهيئة قاعدة بيانات SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300, # إعادة تدوير الاتصالات بعد 300 ثانية
    "pool_pre_ping": True, # التحقق من أن الاتصال لا يزال نشطًا قبل استخدامه
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# تهيئة SQLAlchemy مع التطبيق
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# --- الحصول على مفاتيح API من متغيرات البيئة ---
# API الأساسية: OpenRouter
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
# API الاحتياطية: Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# إعدادات التطبيق الأخرى
APP_URL = os.environ.get("APP_URL", "http://localhost:5000")
APP_TITLE = "Yasmin GPT Chat"  # اسم التطبيق لـ OpenRouter

# --- ردود ياسمين في وضع عدم الاتصال (Fallback في الواجهة الخلفية) ---
# ملاحظة: الواجهة الأمامية تتعامل الآن مع رسائل عدم الاتصال الفورية إذا كان navigator.onLine خطأ.
# هذا الرد الاحتياطي في الواجهة الخلفية مخصص للحالات التي يتم فيها محاولة استدعاء API ويفشل أثناء الطلب.
offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا ياسمين. للأسف، لا يوجد اتصال بالإنترنت حاليًا.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا ياسمين. أعتذر، خدمة الإنترنت غير متوفرة حاليًا.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت."
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت."


# الدالة لاستدعاء Gemini API كنموذج احتياطي
def call_gemini_api(messages_list, temperature, max_tokens=512):
    """Call the Gemini API as a backup when OpenRouter is not available"""
    if not GEMINI_API_KEY:
        logger.warning("Gemini API key not available.")
        return None, "مفتاح Gemini API غير متوفر"

    try:
        # Gemini's API expects prompt in a specific format (contents array)
        # Convert the messages list from OpenRouter format (user/assistant) to Gemini format (user/model)
        gemini_contents = []
        for msg in messages_list:
             # Gemini uses 'user'/'model', need to handle potential 'system' role if used
             role = "user" if msg["role"] == "user" else "model"
             if role == "model" and not gemini_contents: # Gemini expects user first
                  logger.warning("Attempting to start Gemini conversation with model role. Skipping initial model messages.")
                  continue # Skip initial model messages if history doesn't start with user

             # Add 'system' role content to the first 'user' message or handle differently if Gemini supports it in this model
             # For simplicity here, we just use user/model and map other roles to user or ignore
             if msg["role"] not in ["user", "assistant"]:
                  logger.warning(f"Unsupported role '{msg['role']}' for Gemini, mapping to user.")
                  role = "user" # Map other roles like system to user

             # Prevent consecutive 'model' messages as Gemini requires alternation
             if gemini_contents and gemini_contents[-1]['role'] == role == 'model':
                  logger.warning("Consecutive 'model' roles, skipping the current model message for Gemini compatibility.")
                  continue


             gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        # Ensure history starts with user for Gemini
        if gemini_contents and gemini_contents[0]['role'] != 'user':
             logger.warning("Gemini history does not start with 'user'. Adjusting history.")
             # Find the first user message and start from there, or prepend a dummy user message if needed
             first_user_index = -1
             for i, msg in enumerate(gemini_contents):
                  if msg['role'] == 'user':
                       first_user_index = i
                       break

             if first_user_index != -1:
                  gemini_contents = gemini_contents[first_user_index:]
             else:
                  logger.error("No user message found in history for Gemini API call.")
                  return None, "تاريخ المحادثة غير متوافق مع Gemini"


        logger.debug(f"Calling Gemini API with {len(gemini_contents)} parts...")
        response = requests.post(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            headers={
                'Content-Type': 'application/json'
            },
            json={
                "contents": gemini_contents,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature
                }
            },
            timeout=30 # Add a timeout
        )

        response.raise_for_status()
        response_data = response.json()

        # Check for potential issues like blocked candidates
        if 'candidates' not in response_data or len(response_data['candidates']) == 0:
             logger.error(f"Gemini response missing candidates: {response_data}")
             # Check for safety ratings that blocked the response
             if 'promptFeedback' in response_data and 'blockReason' in response_data['promptFeedback']:
                 return None, f"الرد محظور بواسطة فلتر السلامة: {response_data['promptFeedback']['blockReason']}"
             # Check if no response parts were generated successfully
             if 'promptFeedback' in response_data and 'blockReason' not in response_data['promptFeedback']:
                 return None, "لم يتم توليد استجابة من Gemini (فشل داخلي)"

             return None, "لم يتم العثور على استجابة صالحة من Gemini"

        # Extract text, handle multi-part content if necessary (Gemini can return complex content)
        text_parts = []
        # Accessing parts might require checking structure, but for simple text response:
        if 'content' in response_data['candidates'][0] and 'parts' in response_data['candidates'][0]['content']:
             for part in response_data['candidates'][0]['content']['parts']:
                  if 'text' in part:
                      text_parts.append(part['text'])
        else:
             logger.error(f"Gemini response content structure unexpected: {response_data}")


        if text_parts:
            return "".join(text_parts), None # Join text parts into a single string
        else:
            return None, "لم يتم العثور على نص في استجابة Gemini"

    except requests.exceptions.Timeout:
         logger.error("Gemini API request timed out.")
         return None, "استجابة النموذج الاحتياطي استغرقت وقتاً طويلاً"
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Gemini API: {e}")
        return None, f"خطأ في الاتصال بالنموذج الاحتياطي: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error processing Gemini response: {e}", exc_info=True)
        return None, f"خطأ غير متوقع في معالجة استجابة النموذج الاحتياطي: {str(e)}"


# --- مسار الصفحة الرئيسية ---
@app.route('/')
def index():
    # تمرير app_title إلى القالب
    return render_template('index.html', app_title=APP_TITLE)

# --- مسار API للمحادثة ---
@app.route('/api/chat', methods=['POST'])
def chat():
    # استيراد الموديلات داخل الدالة لتجنب الاستيراد الدائري
    from models import Conversation, Message

    # استخدم try...except شاملة لتغطية الأخطاء غير المتوقعة وضمان rollback
    try:
        data = request.json
        # الواجهة الأمامية ترسل مصفوفة التاريخ الكاملة بما في ذلك رسالة المستخدم الأخيرة
        messages_for_api = data.get('history', [])
        # رسالة المستخدم هي الرسالة الأخيرة في التاريخ المرسل من الواجهة الأمامية
        user_message = messages_for_api[-1]['content'] if messages_for_api else ""

        model = data.get('model', 'mistralai/mistral-7b-instruct')
        conversation_id = data.get('conversation_id') # هذا يكون null للمحادثة الجديدة كلياً
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', 512)

        if not user_message:
             logger.warning("Received empty user message in /api/chat history.")
             # لا حاجة لـ rollback هنا لأننا لم نقم بأي تغييرات على الجلسة بعد
             return jsonify({"error": "الرسالة فارغة"}), 400

        # --- المرحلة 1: تحديد المحادثة، وإمكانية إنشائها في الجلسة (معلقة) ---
        db_conversation = None
        # استخدم متغيرًا لـ conversation_id المحتمل الجديد
        current_conversation_id = conversation_id
        # علامة لمعرفة ما إذا كنا قد أضفنا كائن محادثة جديد للجلسة
        new_conversation_created_in_session = False

        if current_conversation_id:
             # محاولة تحميل المحادثة الموجودة
             db_conversation = db.session.execute(db.select(Conversation).filter_by(id=current_conversation_id)).scalar_one_or_none()

        if not db_conversation:
            # إنشاء كائن محادثة جديد في الجلسة إذا لم تكن موجودة
            new_conversation_created_in_session = True
            current_conversation_id = str(uuid.uuid4()) # توليد معرف جديد
            # تعيين العنوان الأولي من أول رسالة مستخدم
            initial_title = user_message.split('\n')[0][:50]
            db_conversation = Conversation(id=current_conversation_id, title=initial_title or "محادثة جديدة")
            # إضافة كائن المحادثة الجديد إلى الجلسة.
            # جملة INSERT يتم تحضيرها ولكن لا يتم إرسالها حتى يتم الـ commit.
            db.session.add(db_conversation)
            logger.debug(f"New conversation added to session (pending commit): {current_conversation_id}")
            # ملاحظة: لا نقوم بالـ commit هنا بعد.

        # --- المرحلة 2: استدعاء واجهات برمجة التطبيقات الخارجية (عملية قد تستغرق وقتاً طويلاً) ---
        ai_reply = None
        error_message = None
        used_backup = False

        # نضع استدعاءات الـ API داخل كتلة try منفصلة اختيارياً
        # لتمييز الأخطاء التي تحدث أثناء الاتصال الخارجي
        try:
            # محاولة OpenRouter API أولاً
            if OPENROUTER_API_KEY:
                try:
                    logger.debug(f"Sending request to OpenRouter with model: {model}, history size: {len(messages_for_api)}")
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                            "HTTP-Referer": APP_URL,  # مطلوب من OpenRouter
                            "X-Title": APP_TITLE,     # اختياري ولكنه موصى به
                        },
                        json={
                            "model": model,
                            "messages": messages_for_api, # استخدم التاريخ الكامل بما في ذلك رسالة المستخدم الأخيرة
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                         timeout=45 # زيادة المهلة قليلاً
                    )

                    response.raise_for_status() # سيطلق استثناء لرموز الحالة 4xx/5xx

                    api_response = response.json()

                    if 'choices' in api_response and len(api_response['choices']) > 0 and 'message' in api_response['choices'][0]:
                         ai_reply = api_response['choices'][0]['message']['content']
                         # سجل التكاليف إذا كانت متاحة (خاص بـ OpenRouter)
                         if 'usage' in api_response:
                             logger.info(f"OpenRouter usage: {api_response['usage']}")
                         if 'router_utilization' in api_response:
                              logger.info(f"OpenRouter utilization: {api_response['router_utilization']}")
                    else:
                         logger.error(f"OpenRouter response missing choices/message: {api_response}")
                         error_message = "استجابة غير متوقعة من OpenRouter"


                except requests.exceptions.Timeout:
                     logger.error("OpenRouter API request timed out.")
                     error_message = "استجابة OpenRouter استغرقت وقتاً طويلاً"
                except requests.exceptions.RequestException as e:
                    logger.error(f"Error calling OpenRouter API: {e}")
                    error_message = f"خطأ في الاتصال بـ OpenRouter: {str(e)}"
                except Exception as e:
                    # التقاط الأخطاء الأخرى المتعلقة بمعالجة استجابة OpenRouter
                    logger.error(f"Unexpected error processing OpenRouter response: {e}", exc_info=True)
                    error_message = f"خطأ غير متوقع في معالجة استجابة OpenRouter: {str(e)}"


            # إذا فشل OpenRouter أو لم يكن متاحًا، حاول Gemini API كنموذج احتياطي
            if not ai_reply and GEMINI_API_KEY:
                logger.info("Trying Gemini API as backup")
                ai_reply, backup_error = call_gemini_api(messages_for_api, temperature, max_tokens)
                if ai_reply:
                    used_backup = True
                    error_message = None # مسح خطأ OpenRouter السابق إذا نجح النموذج الاحتياطي
                else:
                    # الاحتفاظ بخطأ OpenRouter إذا فشل Gemini أيضًا
                    error_message = error_message or f"فشل محاولة استخدام النموذج الاحتياطي: {backup_error}"

            # إذا لم يكن هناك رد حتى بعد محاولة كلا واجهتي برمجة التطبيقات، استخدم الردود الاحتياطية في الواجهة الخلفية
            if not ai_reply:
                 logger.warning("API calls failed, falling back to backend offline responses.")
                 # هذا الرد الاحتياطي في الواجهة الخلفية مخصص للحالات التي بدأت فيها مكالمة API ولكنها فشلت لاحقًا.
                 # الواجهة الأمامية تتعامل مع عدم الاتصال الفوري بناءً على navigator.onLine
                 matched_offline = False
                 user_msg_lower = user_message.lower()
                 for key in offline_responses:
                     if key.lower() in user_msg_lower: # تحقق بسيط بوجود الكلمة المفتاحية
                         ai_reply = offline_responses[key]
                         matched_offline = True
                         break

                 if not matched_offline:
                     ai_reply = default_offline_response
                 # ملاحظة: لا نضبط used_backup=True لردود عدم الاتصال الاحتياطية


        except Exception as e:
            # هذه الكتلة تلتقط الأخطاء التي تحدث أثناء استدعاءات الـ API الخارجية نفسها
            # إذا حدث خطأ هنا (مثل خطأ شبكة عام)، فلن يكون لدينا رد AI
            logger.error(f"Error during external API call: {e}", exc_info=True)
            error_message = error_message or f"خطأ في الاتصال بالنماذج الخارجية: {str(e)}" # احتفظ بالخطأ السابق إذا كان موجودًا

        # --- المرحلة 3: معالجة نتيجة الـ API وإجراء COMMIT لقاعدة البيانات ---

        # إذا لم يكن لدينا رد AI بعد (مثل فشل استدعاءات API ولم يتم العثور على رد احتياطي في وضع عدم الاتصال لسبب ما)
        if not ai_reply:
             # التراجع عن أي تغييرات معلقة في الجلسة، وبالتحديد كائن المحادثة الجديد إذا تم إنشاؤه
             logger.error("No AI reply generated after all attempts. Rolling back session.")
             db.session.rollback()
             return jsonify({
                 "error": error_message or "فشل توليد استجابة"
             }), 500

        # إضافة رسالة المستخدم إلى قاعدة البيانات (الآن بعد أن أصبح لدينا رد AI لنقرنه بها)
        # نحتاج إلى توخي الحذر لعدم إضافة رسالة المستخدم مرة أخرى إذا كانت هذه محاولة إعادة
        # وفشلت المحاولة السابقة *بعد* إضافة رسالة المستخدم ولكن قبل إضافة رد AI.
        # طريقة بسيطة هي التحقق من الرسالة الأخيرة في تاريخ قاعدة البيانات.
        last_db_message = db.session.execute(
             db.select(Message)
             .filter_by(conversation_id=db_conversation.id)
             .order_by(Message.created_at.desc())
             .limit(1)
        ).scalar_one_or_none()

        # إضافة رسالة المستخدم فقط إذا كانت الرسالة الأخيرة في قاعدة البيانات ليست نفس رسالة المستخدم المرسلة حديثاً
        # مع إضافة فحص زمني بسيط لتجنب التكرار في حالة إعادة المحاولة السريعة
        if not last_db_message or not (last_db_message.role == 'user' and last_db_message.content == user_message and (datetime.utcnow() - last_db_message.created_at).total_seconds() < 10): # استخدم نافذة زمنية أطول قليلاً لإعادة المحاولة
             logger.debug(f"Adding user message to DB for conversation {db_conversation.id}")
             db_conversation.add_message('user', user_message)
        else:
             logger.debug(f"Skipping adding potentially duplicate user message for conversation {db_conversation.id}")


        # إضافة رد AI إلى قاعدة البيانات
        logger.debug(f"Adding assistant message to DB for conversation {db_conversation.id}")
        db_conversation.add_message('assistant', ai_reply)

        # الآن، قم بإجراء COMMIT لجميع التغييرات المعلقة (المحادثة الجديدة إذا كانت قابلة للتطبيق، رسالة المستخدم، رسالة المساعد)
        db.session.commit()
        logger.debug(f"Commit successful for conversation {db_conversation.id}")


        # --- المرحلة 4: إرجاع استجابة النجاح ---
        return jsonify({
            # دائماً أرجع conversation_id الذي تم تحديده/إنشاؤه
            "id": current_conversation_id,
            "content": ai_reply,
            "used_backup": used_backup
        })

    except Exception as e:
        # هذه الكتلة تلتقط أي استثناءات أخرى تحدث بعد المرحلة 1،
        # بما في ذلك المشاكل أثناء إضافة الرسائل أو خلال عملية الـ commit نفسها.
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        # تأكد من التراجع عن الجلسة للتراجع عن أي تغييرات قد تكون معلقة
        # هذا أمر حيوي إذا حدث الخطأ أثناء مرحلة الـ commit
        db.session.rollback()
        return jsonify({"error": f"خطأ غير متوقع: {str(e)}"}), 500

# --- مسار API لتاريخ المحادثات ---
@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    # استيراد الموديلات داخل الدالة لتجنب الاستيراد الدائري
    from models import Conversation

    try:
        # الحصول على جميع المحادثات مرتبة حسب آخر تحديث
        conversations = db.session.execute(
            db.select(Conversation).order_by(Conversation.updated_at.desc())
        ).scalars().all()

        # التحويل إلى قائمة من القواميس (مبسطة، بدون الرسائل)
        conversations_list = [
            {
                "id": conv.id,
                "title": conv.title,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None
            }
            for conv in conversations
        ]

        return jsonify(conversations_list)
    except Exception as e:
        logger.error(f"Error getting conversations: {e}", exc_info=True)
        # لا يوجد commit هنا، لذا لا نحتاج لـ rollback بشكل صريح عادةً في GET
        # ولكن إضافة rollback في except آمنة إذا كانت الدالة تقوم بعمليات كتابة
        return jsonify({"error": f"خطأ في استرجاع المحادثات: {str(e)}"}), 500

# --- مسار API لمحادثة معينة ---
@app.route('/api/conversations/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    # استيراد الموديلات داخل الدالة لتجنب الاستيراد الدائري
    from models import Conversation

    try:
        # الحصول على المحادثة
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        # التحويل إلى قاموس مع الرسائل
        return jsonify(conversation.to_dict())
    except Exception as e:
        logger.error(f"Error getting conversation {conversation_id}: {e}", exc_info=True)
        return jsonify({"error": f"خطأ في استرجاع المحادثة: {str(e)}"}), 500

# --- مسار API لحذف محادثة ---
@app.route('/api/conversations/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    # استيراد الموديلات داخل الدالة لتجنب الاستيراد الدائري
    from models import Conversation

    try:
        # البحث عن المحادثة
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        # حذف المحادثة (هذا يجب أن يؤدي إلى حذف الرسائل المرتبطة بسبب cascade)
        db.session.delete(conversation)
        db.session.commit() # قم بالـ commit بعد الحذف

        return jsonify({"success": True, "message": "تم حذف المحادثة بنجاح"})
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {e}", exc_info=True)
        db.session.rollback() # تراجع عن الجلسة في حالة حدوث خطأ أثناء الحذف أو الـ commit
        return jsonify({"error": f"خطأ في حذف المحادثة: {str(e)}"}), 500

# --- مسار API لتحديث عنوان محادثة ---
@app.route('/api/conversations/<conversation_id>/title', methods=['PUT'])
def update_conversation_title(conversation_id):
    # استيراد الموديلات داخل الدالة لتجنب الاستيراد الدائري
    from models import Conversation

    try:
        data = request.json
        new_title = data.get('title')

        if not new_title:
            return jsonify({"error": "عنوان المحادثة مطلوب"}), 400

        # البحث عن المحادثة
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        # تحديث العنوان
        conversation.title = new_title
        db.session.commit() # قم بالـ commit بعد التحديث

        return jsonify({"success": True, "message": "تم تحديث عنوان المحادثة"})
    except Exception as e:
        logger.error(f"Error updating conversation title {conversation_id}: {e}", exc_info=True)
        db.session.rollback() # تراجع عن الجلسة في حالة حدوث خطأ أثناء التحديث أو الـ commit
        return jsonify({"error": f"خطأ في تحديث عنوان المحادثة: {str(e)}"}), 500

# --- مسار API لإعادة توليد الرد الأخير من الذكاء الاصطناعي ---
@app.route('/api/regenerate', methods=['POST'])
def regenerate_response():
    # استيراد الموديلات داخل الدالة لتجنب الاستيراد الدائري
    from models import Conversation, Message

    # استخدم try...except شاملة لضمان rollback
    try:
        data = request.json
        conversation_id = data.get('conversation_id')
        model = data.get('model', 'mistralai/mistral-7b-instruct')
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', 512)

        if not conversation_id:
            return jsonify({"error": "معرف المحادثة مطلوب"}), 400

        # الحصول على المحادثة من قاعدة البيانات
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        # الحصول على الرسائل مرتبة حسب وقت الإنشاء
        messages = db.session.execute(
            db.select(Message)
            .filter_by(conversation_id=conversation_id)
            .order_by(Message.created_at)
        ).scalars().all()

        if not messages:
            # لا نحتاج rollback هنا
            return jsonify({"error": "لا توجد رسائل في المحادثة"}), 400

        # تهيئة قائمة الرسائل لاستدعاء API
        messages_for_api = [{"role": msg.role, "content": msg.content} for msg in messages]

        # ابحث عن آخر رسالة AI وقم بإزالتها من قائمة الرسائل
        # سنعيد توليد آخر رسالة AI فقط إذا كانت موجودة
        last_message_in_db = messages[-1] if messages else None

        # قم بإزالة آخر رسالة من الواجهة الخلفية والجلسة إذا كانت رسالة assistant
        # ولكن لا تقم بالـ commit حتى يتم الحصول على الرد الجديد
        if last_message_in_db and last_message_in_db.role == 'assistant':
             # قم بإزالة الرسالة من قائمة messages_for_api التي سترسلها إلى API
             messages_for_api.pop()
             # قم بوضع علامة على الرسالة للحذف من الجلسة. لن تُحذف فعلياً من DB حتى الـ commit.
             db.session.delete(last_message_in_db)
             logger.debug(f"Marked last assistant message {last_message_in_db.id} for deletion in conversation {conversation_id}.")
        else:
            # إذا لم تكن الرسالة الأخيرة مساعد، أو إذا كانت محادثة جديدة بدون رد AI بعد
            # لا يوجد شيء لإعادة توليده بهذا المنطق
            # db.session.rollback() # لا حاجة لـ rollback هنا إذا لم نقم بحذف أي شيء
            return jsonify({"error": "الرسالة الأخيرة ليست رد من المساعد لإعادة التوليد"}), 400 # أو رسالة مناسبة أكثر

        # إذا أصبحت قائمة messages_for_api فارغة بعد إزالة رسالة المساعد (محادثة من رسالة مستخدم واحدة فقط)
        # فإن النموذج يحتاج سياقًا، لذا نترك رسالة المستخدم الأخيرة
        if not messages_for_api and messages:
             # هذه حالة خاصة: المحادثة تحتوي على رسالة مستخدم واحدة فقط ورسالة مساعد واحدة قمنا بإزالتها.
             # لكي يتمكن النموذج من التوليد، يجب أن نرسل له رسالة المستخدم.
             # messages_for_api تحتوي الآن على الرسائل حتى رسالة المستخدم قبل الأخيرة (أو تكون فارغة)
             # نحتاج إلى إعادة إضافة رسالة المستخدم الأخيرة التي كانت قبل الرسالة المحذوفة
             # ملاحظة: قائمة 'messages' الأصلية لم تتغير
             last_user_message = None
             for msg in reversed(messages[:-1]): # البحث في الرسائل قبل الأخيرة المحذوفة
                 if msg.role == 'user':
                      last_user_message = msg
                      break

             if last_user_message:
                 messages_for_api.append({"role": last_user_message.role, "content": last_user_message.content})
                 logger.debug("Added back last user message to API history for regeneration.")
             else:
                 # هذه الحالة لا ينبغي أن تحدث إذا كان هناك رسائل في الأصل
                 logger.error("Could not find last user message for regeneration after removing assistant.")
                 # db.session.rollback() # التراجع عن حذف رسالة المساعد المعلقة
                 return jsonify({"error": "لا توجد رسائل مستخدم لإعادة التوليد"}), 400


        # الآن قم بإجراء استدعاء API جديد لإعادة توليد الاستجابة
        ai_reply = None
        error_message = None
        used_backup = False

        # محاولة OpenRouter API أولاً، بنفس الطريقة في نقطة نهاية chat
        if OPENROUTER_API_KEY:
            try:
                logger.debug(f"Regenerating response with OpenRouter model: {model}")
                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "HTTP-Referer": APP_URL,
                        "X-Title": APP_TITLE,
                    },
                    json={
                        "model": model,
                        "messages": messages_for_api, # هذه القائمة لا تحتوي على رسالة المساعد الأخيرة
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=45
                )

                response.raise_for_status()
                api_response = response.json()

                if 'choices' in api_response and len(api_response['choices']) > 0 and 'message' in api_response['choices'][0]:
                    ai_reply = api_response['choices'][0]['message']['content']
                else:
                    logger.error(f"OpenRouter regeneration response missing choices/message: {api_response}")
                    error_message = "استجابة غير متوقعة من OpenRouter أثناء إعادة التوليد"

            except Exception as e:
                logger.error(f"Error regenerating response with OpenRouter: {e}", exc_info=True)
                error_message = f"خطأ أثناء إعادة التوليد: {str(e)}"

        # محاولة Gemini API كنموذج احتياطي إذا فشل OpenRouter
        if not ai_reply and GEMINI_API_KEY:
            logger.info("Trying Gemini API as backup for regeneration")
            ai_reply, backup_error = call_gemini_api(messages_for_api, temperature, max_tokens)
            if ai_reply:
                used_backup = True
                error_message = None # مسح الخطأ السابق
            else:
                error_message = error_message or f"فشل محاولة استخدام النموذج الاحتياطي: {backup_error}"

        # إذا لم يكن هناك رد حتى بعد محاولة كلا واجهتي برمجة التطبيقات، استخدم الردود الاحتياطية في الواجهة الخلفية
        if not ai_reply:
            logger.warning("API calls failed during regeneration, falling back to offline responses.")
            # يجب أن نجد آخر رسالة مستخدم في التاريخ لنستخدمها للبحث في الردود الاحتياطية
            last_user_msg_for_offline = messages_for_api[-1]['content'] if messages_for_api and messages_for_api[-1]['role'] == 'user' else ""

            matched_offline = False
            if last_user_msg_for_offline:
                user_msg_lower = last_user_msg_for_offline.lower()
                for key in offline_responses:
                    if key.lower() in user_msg_lower:
                        ai_reply = offline_responses[key]
                        matched_offline = True
                        break

            if not matched_offline:
                ai_reply = default_offline_response

        # إضافة رد AI الذي تم إعادة توليده إلى قاعدة البيانات
        if ai_reply:
            # هذا سيضيف الرسالة الجديدة ويقوم أيضاً بعملية الحذف التي تم وضع علامة عليها سابقاً
            conversation.add_message('assistant', ai_reply)
            db.session.commit() # قم بالـ commit هنا لحفظ التغييرات

            return jsonify({
                "content": ai_reply,
                "used_backup": used_backup
            })
        else:
            # شيء ما سار بشكل خاطئ ولم نحصل على رد
            # يجب التراجع عن أي تغييرات معلقة، بما في ذلك حذف رسالة المساعد المعلقة
            logger.error("Regeneration failed, rolling back session.")
            db.session.rollback()
            return jsonify({
                "error": error_message or "فشل إعادة توليد الاستجابة"
            }), 500

    except Exception as e:
        # هذه الكتلة تلتقط أي استثناءات غير متوقعة أخرى في الدالة
        logger.error(f"Error in regenerate endpoint: {e}", exc_info=True)
        # تأكد من التراجع عن أي عمليات فاشلة
        db.session.rollback()
        return jsonify({"error": f"خطأ غير متوقع أثناء إعادة التوليد: {str(e)}"}), 500


# من الممارسات الجيدة أيضاً التأكد من إزالة الجلسات
# يتم التعامل مع هذا غالبًا بواسطة Flask-SQLAlchemy، ولكن التعامل الصريح مع teardown أكثر أمانًا
@app.teardown_request
def remove_session(exception=None):
    # تأكد من عدم إغلاق الجلسة إذا كانت لا تزال في حالة خطأ معلقة
    # يمكن أن يساعد db.session.remove() في تنظيف الجلسة بعد كل طلب
    db.session.remove()


# يجب أن يتم إنشاء الجداول في قاعدة البيانات قبل تشغيل التطبيق
# يمكنك إضافة سطر لتشغيل هذا عند الحاجة، ربما في ملف منفصل أو باستخدام سياق التطبيق
# مثال (للتشغيل اليدوي أو في سكريبت النشر):
# with app.app_context():
#     db.create_all()

# if __name__ == '__main__':
#     # هذا للتطوير المحلي فقط
#     with app.app_context():
#         db.create_all() # للتطوير، يمكنك إنشاء الجداول هنا
#     app.run(debug=True)

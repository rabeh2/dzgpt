# ملف: app.py (نسخة محسنة للتشخيص على Render)

import os
import logging
import requests
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError, InterfaceError, OperationalError # استيراد أنواع أخطاء SQLAlchemy المحددة للتشخيص

# إعداد التسجيل (Logging)
# تأكد من أن مستوى التسجيل في بيئة Render مضبوط على DEBUG أو INFO لرؤية هذه الرسائل
logging.basicConfig(level=logging.DEBUG) # استخدم DEBUG لرؤية كل شيء أثناء التطوير/التشخيص
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
    "pool_recycle": 300, # إعادة تدوير الاتصالات بعد 300 ثانية. قد تحتاج إلى تقليل هذا بناءً على مهلة Render.
    "pool_pre_ping": True, # التحقق من أن الاتصال لا يزال نشطًا قبل استخدامه من التجمع.
    # قد تحتاج لإضافة خيارات أخرى إذا لم يتم حل المشكلة، مثل:
    # "pool_timeout": 10, # مهلة الانتظار للحصول على اتصال من التجمع
    # "connect_args": {"connect_timeout": 10} # مهلة الاتصال الأولية
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
offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا ياسمين. للأسف، لا يوجد اتصال بالإنترنت حاليًا.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا ياسمين. أعتذر، خدمة الإنترنت غير متوفرة حاليًا.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت."
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت."


# الدالة لاستدعاء Gemini API كنموذج احتياطي (بدون تغيير جوهري عن النسخة السابقة)
def call_gemini_api(messages_list, temperature, max_tokens=512):
    """Call the Gemini API as a backup when OpenRouter is not available"""
    if not GEMINI_API_KEY:
        logger.warning("Gemini API key not available.")
        return None, "مفتاح Gemini API غير متوفر"

    try:
        # Gemini's API expects prompt in a specific format (contents array)
        gemini_contents = []
        for msg in messages_list:
             role = "user" if msg["role"] == "user" else "model"
             if role == "model" and not gemini_contents:
                  logger.warning("Attempting to start Gemini conversation with model role. Skipping initial model messages.")
                  continue

             if msg["role"] not in ["user", "assistant"]:
                  logger.warning(f"Unsupported role '{msg['role']}' for Gemini, mapping to user.")
                  role = "user"

             if gemini_contents and gemini_contents[-1]['role'] == role == 'model':
                  logger.warning("Consecutive 'model' roles, skipping the current model message for Gemini compatibility.")
                  continue

             gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        if gemini_contents and gemini_contents[0]['role'] != 'user':
             logger.warning("Gemini history does not start with 'user'. Adjusting history.")
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
            timeout=30
        )

        response.raise_for_status()
        response_data = response.json()

        if 'candidates' not in response_data or len(response_data['candidates']) == 0:
             logger.error(f"Gemini response missing candidates: {response_data}")
             if 'promptFeedback' in response_data and 'blockReason' in response_data['promptFeedback']:
                 return None, f"الرد محظور بواسطة فلتر السلامة: {response_data['promptFeedback']['blockReason']}"
             if 'promptFeedback' in response_data and 'blockReason' not in response_data['promptFeedback']:
                 return None, "لم يتم توليد استجابة من Gemini (فشل داخلي)"
             return None, "لم يتم العثور على استجابة صالحة من Gemini"

        text_parts = []
        if 'content' in response_data['candidates'][0] and 'parts' in response_data['candidates'][0]['content']:
             for part in response_data['candidates'][0]['content']['parts']:
                  if 'text' in part:
                      text_parts.append(part['text'])
        else:
             logger.error(f"Gemini response content structure unexpected: {response_data}")

        if text_parts:
            return "".join(text_parts), None
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
    return render_template('index.html', app_title=APP_TITLE)

# --- مسار API للمحادثة ---
@app.route('/api/chat', methods=['POST'])
def chat():
    # استيراد الموديلات داخل الدالة
    from models import Conversation, Message

    # ابدأ كتلة try...except هنا لتغطية كامل منطق معالجة الطلب
    try:
        logger.debug("Handling /api/chat request.")
        data = request.json
        messages_for_api = data.get('history', [])
        user_message = messages_for_api[-1]['content'] if messages_for_api else ""

        model = data.get('model', 'mistralai/mistral-7b-instruct')
        conversation_id = data.get('conversation_id')
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', 512)

        if not user_message:
             logger.warning("Received empty user message in /api/chat history.")
             return jsonify({"error": "الرسالة فارغة"}), 400

        # --- المرحلة 1: تحديد المحادثة، وإمكانية إنشائها في الجلسة (معلقة) ---
        # يتم التعامل مع الجلسة db.session تلقائياً لكل طلب بفضل Flask-SQLAlchemy
        db_conversation = None
        current_conversation_id = conversation_id
        new_conversation_created_in_session = False

        logger.debug(f"Phase 1: Checking conversation ID: {conversation_id}")
        if current_conversation_id:
             try:
                db_conversation = db.session.execute(db.select(Conversation).filter_by(id=current_conversation_id)).scalar_one_or_none()
                logger.debug(f"Found existing conversation: {current_conversation_id}")
             except SQLAlchemyError as e:
                 # التقاط أخطاء قاعدة البيانات المحتملة أثناء جلب المحادثة
                 logger.error(f"Database error fetching conversation {current_conversation_id}: {e}", exc_info=True)
                 # في حالة خطأ DB أثناء الجلب، لا يمكننا المتابعة.
                 db.session.rollback() # تأكد من التراجع
                 return jsonify({"error": f"خطأ في قاعدة البيانات أثناء تحميل المحادثة: {str(e)}"}), 500


        if not db_conversation:
            new_conversation_created_in_session = True
            current_conversation_id = str(uuid.uuid4())
            initial_title = user_message.split('\n')[0][:50]
            db_conversation = Conversation(id=current_conversation_id, title=initial_title or "محادثة جديدة")

            # إضافة كائن المحادثة الجديد إلى الجلسة. الـ INSERT معلق حتى الـ commit.
            db.session.add(db_conversation)
            logger.debug(f"New conversation object {current_conversation_id} added to session (pending insert).")
            # لا نقوم بالـ commit هنا.

        # --- المرحلة 2: استدعاء واجهات برمجة التطبيقات الخارجية (عملية قد تستغرق وقتاً طويلاً) ---
        ai_reply = None
        error_message = None
        used_backup = False

        logger.debug("Phase 2: Calling external API(s)...")
        try:
            # محاولة OpenRouter API أولاً
            if OPENROUTER_API_KEY:
                logger.debug(f"Attempting OpenRouter API call for model: {model}")
                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "HTTP-Referer": APP_URL,
                        "X-Title": APP_TITLE,
                    },
                    json={
                        "model": model,
                        "messages": messages_for_api,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=45
                )

                response.raise_for_status()

                api_response = response.json()

                if 'choices' in api_response and len(api_response['choices']) > 0 and 'message' in api_response['choices'][0]:
                     ai_reply = api_response['choices'][0]['message']['content']
                     logger.debug("Received successful response from OpenRouter.")
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
                logger.error(f"Unexpected error processing OpenRouter response: {e}", exc_info=True)
                error_message = f"خطأ غير متوقع في معالجة استجابة OpenRouter: {str(e)}"


            # إذا فشل OpenRouter أو لم يكن متاحًا، حاول Gemini API كنموذج احتياطي
            if not ai_reply and GEMINI_API_KEY:
                logger.info("OpenRouter failed or not used. Trying Gemini API as backup.")
                ai_reply, backup_error = call_gemini_api(messages_for_api, temperature, max_tokens)
                if ai_reply:
                    used_backup = True
                    error_message = None # Clear previous OpenRouter error if backup succeeds
                    logger.debug("Received successful response from Gemini backup.")
                else:
                    # Keep the OpenRouter error if Gemini also failed
                    error_message = error_message or f"فشل محاولة استخدام النموذج الاحتياطي: {backup_error}"
                    logger.error(f"Gemini backup failed: {backup_error}")


            # إذا لم يكن هناك رد حتى بعد محاولة كلا واجهتي برمجة التطبيقات، استخدم الردود الاحتياطية في الواجهة الخلفية
            if not ai_reply:
                 logger.warning("API calls failed, falling back to backend offline responses.")
                 matched_offline = False
                 user_msg_lower = user_message.lower()
                 for key in offline_responses:
                     if key.lower() in user_msg_lower:
                         ai_reply = offline_responses[key]
                         matched_offline = True
                         logger.debug("Matched offline response.")
                         break

                 if not matched_offline:
                     ai_reply = default_offline_response
                     logger.debug("Using default offline response.")

        except Exception as e:
            # هذه الكتلة تلتقط الأخطاء التي تحدث أثناء استدعاءات الـ API الخارجية نفسها
            logger.error(f"Critical error during external API call phase: {e}", exc_info=True)
            # هنا يمكن أن يحدث الخطأ قبل أن يتوفر ai_reply
            error_message = error_message or f"خطأ في الاتصال بالنماذج الخارجية: {str(e)}"
            # بما أن هذا الخطأ خطير ومن المحتمل أنه منع الحصول على رد، يجب أن نمرر المعالجة
            # إلى كتلة except الرئيسية في الخارج للسماح بالـ rollback.
            # لا نرجع استجابة هنا، بل نسمح للاستثناء بالمرور.
            raise # أعد إطلاق الاستثناء ليتم التقاطه بواسطة كتلة except الخارجية


        # --- المرحلة 3: معالجة نتيجة الـ API وإجراء COMMIT لقاعدة البيانات ---

        # إذا لم يكن لدينا رد AI بعد (مثل فشل استدعاءات API ولم يتم العثور على رد احتياطي)
        if not ai_reply:
             # لا نحتاج لـ rollback هنا لأن الاستثناء في المرحلة 2 كان سيؤدي لذلك
             # ولكن للحذر، إذا وصلنا هنا بدون ai_reply لسبب آخر غير الاستثناء المُلتقط،
             # يجب التراجع.
             logger.error("No AI reply generated. Rolling back session if changes were made.")
             db.session.rollback() # تأكيد التراجع
             return jsonify({
                 "error": error_message or "فشل توليد استجابة"
             }), 500


        # إذا حصلنا على رد AI، نواصل حفظه والرسائل في قاعدة البيانات
        logger.debug("Phase 3: Processing API result and preparing for database commit.")

        # إضافة رسالة المستخدم
        # تحقق لتجنب التكرار في حالة إعادة المحاولة السريعة
        last_db_message = db.session.execute(
             db.select(Message)
             .filter_by(conversation_id=db_conversation.id)
             .order_by(Message.created_at.desc())
             .limit(1)
        ).scalar_one_or_none()

        if not last_db_message or not (last_db_message.role == 'user' and last_db_message.content == user_message and (datetime.utcnow() - last_db_message.created_at).total_seconds() < 10):
             logger.debug(f"Adding user message to session for conversation {db_conversation.id}")
             try:
                 db_conversation.add_message('user', user_message)
                 logger.debug("User message added to session.")
             except SQLAlchemyError as e:
                 logger.error(f"Database error adding user message to session: {e}", exc_info=True)
                 db.session.rollback()
                 return jsonify({"error": f"خطأ في قاعدة البيانات أثناء إضافة رسالة المستخدم: {str(e)}"}), 500
        else:
             logger.debug(f"Skipping adding potentially duplicate user message for conversation {db_conversation.id}")


        # إضافة رد AI
        logger.debug(f"Adding assistant message to session for conversation {db_conversation.id}")
        try:
            db_conversation.add_message('assistant', ai_reply)
            logger.debug("Assistant message added to session.")
        except SQLAlchemyError as e:
            logger.error(f"Database error adding assistant message to session: {e}", exc_info=True)
            db.session.rollback()
            return jsonify({"error": f"خطأ في قاعدة البيانات أثناء إضافة رد المساعد: {str(e)}"}), 500


        # --- محاولة الـ COMMIT النهائية ---
        logger.debug("Attempting to commit session changes (new conversation, user msg, assistant msg)...")
        try:
            db.session.commit()
            logger.debug("Database commit successful!")
        # التقاط أنواع أخطاء محددة تتعلق بالاتصال أو العمليات
        except (InterfaceError, OperationalError) as e:
            logger.error(f"Database Interface/Operational Error during commit: {e}", exc_info=True)
            # هذا هو الخطأ الذي تراه على الأرجح. يحدث هنا أثناء إرسال التغييرات.
            db.session.rollback() # التراجع عن الجلسة
            return jsonify({"error": f"خطأ في الاتصال بقاعدة البيانات أثناء الحفظ: {str(e)}"}), 500
        except SQLAlchemyError as e:
             # التقاط أي أخطاء SQLAlchemy أخرى أثناء الـ commit
             logger.error(f"SQLAlchemy error during commit: {e}", exc_info=True)
             db.session.rollback()
             return jsonify({"error": f"خطأ في قاعدة البيانات أثناء الحفظ: {str(e)}"}), 500
        except Exception as e:
             # التقاط أي أخطاء غير متوقعة أثناء الـ commit
             logger.error(f"Unexpected error during database commit: {e}", exc_info=True)
             db.session.rollback()
             return jsonify({"error": f"خطأ غير متوقع أثناء الحفظ في قاعدة البيانات: {str(e)}"}), 500


        # --- المرحلة 4: إرجاع استجابة النجاح ---
        logger.debug("Commit successful. Returning success response.")
        return jsonify({
            "id": current_conversation_id, # دائماً أرجع conversation_id الذي تم تحديده/إنشاؤه
            "content": ai_reply,
            "used_backup": used_backup
        })

    # هذه الكتلة تلتقط أي استثناءات *لم يتم التقاطها* في الكتل الداخلية
    # بما في ذلك الاستثناءات التي تم إعادة إطلاقها (raise) من الكتل الداخلية (مثل خطأ API critical)
    except Exception as e:
        logger.error(f"Caught unhandled exception in /api/chat endpoint: {e}", exc_info=True)
        # تأكد دائماً من التراجع عن الجلسة في حالة حدوث أي خطأ لم يتم التعامل معه
        db.session.rollback()
        return jsonify({"error": f"خطأ غير متوقع في الخادم: {str(e)}"}), 500


# --- مسار API لتاريخ المحادثات --- (لا تغيير جوهري)
@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    from models import Conversation
    try:
        logger.debug("Handling /api/conversations GET request.")
        conversations = db.session.execute(
            db.select(Conversation).order_by(Conversation.updated_at.desc())
        ).scalars().all()

        conversations_list = [
            {
                "id": conv.id,
                "title": conv.title,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None
            }
            for conv in conversations
        ]
        logger.debug(f"Returning {len(conversations_list)} conversations.")
        return jsonify(conversations_list)
    except Exception as e:
        logger.error(f"Error getting conversations: {e}", exc_info=True)
        # لا يوجد commit هنا عادةً في GET، لكن rollback آمن في حالة حدوث خطأ أثناء الاستعلام
        db.session.rollback()
        return jsonify({"error": f"خطأ في استرجاع المحادثات: {str(e)}"}), 500

# --- مسار API لمحادثة معينة --- (لا تغيير جوهري)
@app.route('/api/conversations/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    from models import Conversation
    try:
        logger.debug(f"Handling /api/conversations/{conversation_id} GET request.")
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Conversation {conversation_id} not found.")
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        logger.debug(f"Returning conversation {conversation_id} details.")
        return jsonify(conversation.to_dict())
    except Exception as e:
        logger.error(f"Error getting conversation {conversation_id}: {e}", exc_info=True)
        db.session.rollback() # rollback آمن
        return jsonify({"error": f"خطأ في استرجاع المحادثة: {str(e)}"}), 500

# --- مسار API لحذف محادثة --- (إضافة تسجيلات)
@app.route('/api/conversations/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    from models import Conversation
    try:
        logger.debug(f"Handling /api/conversations/{conversation_id} DELETE request.")
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Conversation {conversation_id} not found for deletion.")
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        logger.debug(f"Deleting conversation {conversation_id} and its messages.")
        db.session.delete(conversation)
        db.session.commit() # قم بالـ commit بعد الحذف
        logger.debug(f"Conversation {conversation_id} deleted successfully.")

        return jsonify({"success": True, "message": "تم حذف المحادثة بنجاح"})
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {e}", exc_info=True)
        db.session.rollback() # تراجع عن الجلسة في حالة حدوث خطأ أثناء الحذف أو الـ commit
        return jsonify({"error": f"خطأ في حذف المحادثة: {str(e)}"}), 500

# --- مسار API لتحديث عنوان محادثة --- (إضافة تسجيلات)
@app.route('/api/conversations/<conversation_id>/title', methods=['PUT'])
def update_conversation_title(conversation_id):
    from models import Conversation
    try:
        logger.debug(f"Handling /api/conversations/{conversation_id}/title PUT request.")
        data = request.json
        new_title = data.get('title')

        if not new_title:
            logger.warning("New title is missing in PUT request.")
            return jsonify({"error": "عنوان المحادثة مطلوب"}), 400

        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Conversation {conversation_id} not found for title update.")
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        logger.debug(f"Updating title for conversation {conversation_id} to '{new_title}'.")
        conversation.title = new_title
        db.session.commit() # قم بالـ commit بعد التحديث
        logger.debug("Title updated and committed successfully.")

        return jsonify({"success": True, "message": "تم تحديث عنوان المحادثة"})
    except Exception as e:
        logger.error(f"Error updating conversation title {conversation_id}: {e}", exc_info=True)
        db.session.rollback() # تراجع عن الجلسة في حالة حدوث خطأ أثناء التحديث أو الـ commit
        return jsonify({"error": f"خطأ في تحديث عنوان المحادثة: {str(e)}"}), 500

# --- مسار API لإعادة توليد الرد الأخير من الذكاء الاصطناعي --- (إضافة تسجيلات)
@app.route('/api/regenerate', methods=['POST'])
def regenerate_response():
    from models import Conversation, Message

    try:
        logger.debug("Handling /api/regenerate request.")
        data = request.json
        conversation_id = data.get('conversation_id')
        model = data.get('model', 'mistralai/mistral-7b-instruct')
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', 512)

        if not conversation_id:
            logger.warning("Conversation ID is missing for regeneration.")
            return jsonify({"error": "معرف المحادثة مطلوب"}), 400

        # الحصول على المحادثة من قاعدة البيانات
        logger.debug(f"Fetching conversation {conversation_id} for regeneration.")
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Conversation {conversation_id} not found for regeneration.")
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        # الحصول على الرسائل
        logger.debug(f"Fetching messages for conversation {conversation_id}.")
        messages = db.session.execute(
            db.select(Message)
            .filter_by(conversation_id=conversation_id)
            .order_by(Message.created_at)
        ).scalars().all()

        if not messages:
            logger.warning(f"No messages found for conversation {conversation_id} during regeneration attempt.")
            return jsonify({"error": "لا توجد رسائل في المحادثة"}), 400

        # تهيئة قائمة الرسائل لاستدعاء API
        messages_for_api = [{"role": msg.role, "content": msg.content} for msg in messages]

        # ابحث عن آخر رسالة AI وقم بإزالتها من قائمة الرسائل ووضع علامة عليها للحذف
        last_message_in_db = messages[-1] if messages else None
        original_assistant_message = None

        if last_message_in_db and last_message_in_db.role == 'assistant':
             original_assistant_message = last_message_in_db # احتفظ بالمرجع لل rollback
             messages_for_api.pop() # إزالة من قائمة API
             db.session.delete(last_message_in_db) # وضع علامة للحذف في الجلسة
             logger.debug(f"Marked last assistant message {last_message_in_db.id} for deletion.")
        else:
            logger.warning(f"Last message in conversation {conversation_id} is not an assistant message. Cannot regenerate.")
            # db.session.rollback() # لا حاجة للتراجع إذا لم نضع علامة على شيء للحذف
            return jsonify({"error": "الرسالة الأخيرة ليست رد من المساعد لإعادة التوليد"}), 400

        # إذا أصبحت قائمة API فارغة بعد إزالة رسالة المساعد (محادثة من رسالة مستخدم واحدة + رسالة مساعد واحدة)
        # نحتاج إلى ترك رسالة المستخدم الأخيرة كسياق للنموذج
        if not messages_for_api and messages: # 'messages' لا تزال تحتوي على الرسالة المحذوفة
             last_user_message = None
             for msg in reversed(messages[:-1]): # البحث في الرسائل قبل الأخيرة المحذوفة
                 if msg.role == 'user':
                      last_user_message = msg
                      break

             if last_user_message:
                 messages_for_api.append({"role": last_user_message.role, "content": last_user_message.content})
                 logger.debug("Added back last user message to API history for regeneration context.")
             else:
                 logger.error("Could not find last user message for regeneration after removing assistant. Cannot regenerate.")
                 # إذا لم نجد رسالة مستخدم، لا يمكننا إعادة التوليد. تراجع عن حذف رسالة المساعد.
                 if original_assistant_message:
                      db.session.rollback() # التراجع عن حذف رسالة المساعد المعلقة
                      logger.debug("Rolled back session due to missing user message for regeneration context.")
                 return jsonify({"error": "لا توجد رسائل مستخدم لإعادة التوليد"}), 400


        # الآن قم بإجراء استدعاء API جديد
        ai_reply = None
        error_message = None
        used_backup = False

        logger.debug("Phase 2 (Regenerate): Calling external API(s)...")
        try:
            # محاولة OpenRouter API أولاً
            if OPENROUTER_API_KEY:
                logger.debug(f"Attempting OpenRouter API call for regeneration with model: {model}")
                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "HTTP-Referer": APP_URL,
                        "X-Title": APP_TITLE,
                    },
                    json={
                        "model": model,
                        "messages": messages_for_api,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=45
                )

                response.raise_for_status()
                api_response = response.json()

                if 'choices' in api_response and len(api_response['choices']) > 0 and 'message' in api_response['choices'][0]:
                    ai_reply = api_response['choices'][0]['message']['content']
                    logger.debug("Received successful response from OpenRouter during regeneration.")
                else:
                    logger.error(f"OpenRouter regeneration response missing choices/message: {api_response}")
                    error_message = "استجابة غير متوقعة من OpenRouter أثناء إعادة التوليد"

            except requests.exceptions.Timeout:
                 logger.error("OpenRouter regeneration API request timed out.")
                 error_message = "استجابة OpenRouter استغرقت وقتاً طويلاً"
            except requests.exceptions.RequestException as e:
                logger.error(f"Error calling OpenRouter API for regeneration: {e}")
                error_message = f"خطأ في الاتصال بـ OpenRouter أثناء إعادة التوليد: {str(e)}"
            except Exception as e:
                logger.error(f"Unexpected error processing OpenRouter regeneration response: {e}", exc_info=True)
                error_message = f"خطأ غير متوقع في معالجة استجابة OpenRouter أثناء إعادة التوليد: {str(e)}"


            # إذا فشل OpenRouter أو لم يكن متاحًا، حاول Gemini API كنموذج احتياطي
            if not ai_reply and GEMINI_API_KEY:
                logger.info("OpenRouter failed for regeneration. Trying Gemini API as backup.")
                ai_reply, backup_error = call_gemini_api(messages_for_api, temperature, max_tokens)
                if ai_reply:
                    used_backup = True
                    error_message = None # مسح الخطأ السابق
                    logger.debug("Received successful response from Gemini backup during regeneration.")
                else:
                    error_message = error_message or f"فشل محاولة استخدام النموذج الاحتياطي أثناء إعادة التوليد: {backup_error}"
                    logger.error(f"Gemini backup failed for regeneration: {backup_error}")


            # إذا لم يكن هناك رد حتى بعد محاولة كلا واجهتي برمجة التطبيقات، استخدم الردود الاحتياطية
            if not ai_reply:
                logger.warning("API calls failed during regeneration, falling back to offline responses.")
                last_user_msg_for_offline = messages_for_api[-1]['content'] if messages_for_api and messages_for_api[-1]['role'] == 'user' else ""

                matched_offline = False
                if last_user_msg_for_offline:
                    user_msg_lower = last_user_msg_for_offline.lower()
                    for key in offline_responses:
                        if key.lower() in user_msg_lower:
                            ai_reply = offline_responses[key]
                            matched_offline = True
                            logger.debug("Matched offline response during regeneration.")
                            break

                if not matched_offline:
                    ai_reply = default_offline_response
                    logger.debug("Using default offline response during regeneration.")

        except Exception as e:
             logger.error(f"Critical error during external API call phase for regeneration: {e}", exc_info=True)
             error_message = error_message or f"خطأ في الاتصال بالنماذج الخارجية أثناء إعادة التوليد: {str(e)}"
             # أعد إطلاق الاستثناء ليتم التقاطه بواسطة كتلة except الخارجية
             raise

        # --- المرحلة 3 (Regenerate): معالجة نتيجة الـ API وإجراء COMMIT ---

        # إذا لم نحصل على رد AI
        if not ai_reply:
            logger.error("No AI reply generated during regeneration. Rolling back session.")
            db.session.rollback() # تراجع عن حذف رسالة المساعد
            return jsonify({
                "error": error_message or "فشل إعادة توليد الاستجابة"
            }), 500

        # إذا حصلنا على رد AI، نضيفه ونقوم بالـ commit
        logger.debug("Phase 3 (Regenerate): Processing API result and preparing for database commit.")
        try:
            # هذا سيضيف الرسالة الجديدة ويقوم أيضاً بعملية الحذف التي تم وضع علامة عليها سابقاً
            logger.debug(f"Adding new assistant message to session for conversation {conversation_id}.")
            conversation.add_message('assistant', ai_reply)
            logger.debug("New assistant message added to session.")

            # --- محاولة الـ COMMIT النهائية لإعادة التوليد ---
            logger.debug("Attempting to commit session changes (delete old msg, add new msg)...")
            db.session.commit() # قم بالـ commit هنا لحفظ التغييرات
            logger.debug("Database commit successful for regeneration!")

            return jsonify({
                "content": ai_reply,
                "used_backup": used_backup
            })

        # التقاط أنواع أخطاء محددة تتعلق بالاتصال أو العمليات أثناء الـ commit
        except (InterfaceError, OperationalError) as e:
            logger.error(f"Database Interface/Operational Error during regeneration commit: {e}", exc_info=True)
            db.session.rollback() # التراجع عن الجلسة (بما في ذلك حذف الرسالة القديمة!)
            return jsonify({"error": f"خطأ في الاتصال بقاعدة البيانات أثناء إعادة التوليد والحفظ: {str(e)}"}), 500
        except SQLAlchemyError as e:
             # التقاط أي أخطاء SQLAlchemy أخرى أثناء الـ commit
             logger.error(f"SQLAlchemy error during regeneration commit: {e}", exc_info=True)
             db.session.rollback()
             return jsonify({"error": f"خطأ في قاعدة البيانات أثناء إعادة التوليد والحفظ: {str(e)}"}), 500
        except Exception as e:
             # التقاط أي أخطاء غير متوقعة أثناء الـ commit
             logger.error(f"Unexpected error during regeneration database commit: {e}", exc_info=True)
             db.session.rollback()
             return jsonify({"error": f"خطأ غير متوقع أثناء إعادة التوليد والحفظ في قاعدة البيانات: {str(e)}"}), 500


    # هذه الكتلة تلتقط أي استثناءات *لم يتم التقاطها* في الكتل الداخلية
    # بما في ذلك الاستثناءات التي تم إعادة إطلاقها (raise)
    except Exception as e:
        logger.error(f"Caught unhandled exception in /api/regenerate endpoint: {e}", exc_info=True)
        # تأكد دائماً من التراجع عن الجلسة في حالة حدوث أي خطأ لم يتم التعامل معه
        db.session.rollback()
        return jsonify({"error": f"خطأ غير متوقع في الخادم أثناء إعادة التوليد: {str(e)}"}), 500


# من الممارسات الجيدة أيضاً التأكد من إزالة الجلسات بعد كل طلب
# يتم التعامل مع هذا غالبًا بواسطة Flask-SQLAlchemy بشكل تلقائي، ولكن التعريف الصريح آمن.
# هذه الدالة يتم استدعاؤها تلقائياً بواسطة Flask بعد معالجة كل طلب، حتى لو حدث خطأ.
@app.teardown_request
def remove_session(exception=None):
    # db.session.remove() يعيد الاتصالات المستخدمة في الجلسة إلى التجمع
    # وإذا كانت هناك استثناءات غير معالجة، فإنه يقوم أيضاً بالـ rollback تلقائياً
    # ومع ذلك، الـ rollback الصريح في كتل except يساعد في التعامل مع الأخطاء
    # وتقديم رسائل خطأ مفيدة للمستخدم قبل وصول الاستثناء إلى teardown.
    logger.debug("Removing session after request.")
    db.session.remove()

# ملاحظة: إنشاء الجداول (db.create_all()) يتم في ملف main.py أو في سكريبت النشر،
# وليس هنا في app.py.

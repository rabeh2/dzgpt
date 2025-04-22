import os
import logging
import requests
import json
import uuid
from datetime import datetime, timezone # استخدام timezone aware datetime

from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, DateTime, ForeignKey, select, delete, update, desc, func
from sqlalchemy.dialects.postgresql import UUID # لاستخدام نوع UUID الأصلي في PostgreSQL
from sqlalchemy.exc import SQLAlchemyError

# --- إعداد التسجيل ---
# في Render، سيتم التقاط المخرجات إلى stdout/stderr وعرضها في السجلات
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Base Class for SQLAlchemy models (أسلوب حديث) ---
class Base(DeclarativeBase):
    pass

# --- تهيئة Flask و SQLAlchemy ---
app = Flask(__name__)

# --- تحميل الإعدادات الحساسة من متغيرات البيئة (ضروري لـ Render) ---
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    logger.warning("SESSION_SECRET environment variable not set. Using a default insecure key for now.")
    app.secret_key = "default-insecure-secret-key-for-render" # استخدم هذا فقط إذا فشل تحميل المتغير

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.error("FATAL: DATABASE_URL environment variable is not set.")
    # قد ترغب في منع بدء التشغيل هنا
    # raise ValueError("DATABASE_URL is required")
else:
    # Render قد يوفر 'postgres://' بدلاً من 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

# إعدادات اتصال قاعدة البيانات الموصى بها للبيئات السحابية
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,  # أقل بقليل من 5 دقائق (شائع لـ timeouts)
    "pool_pre_ping": True, # للتحقق من الاتصال قبل استخدامه
    "pool_timeout": 10,   # وقت انتظار الحصول على اتصال من الـ pool
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# تهيئة SQLAlchemy مع التطبيق ونموذج Base
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# --- تحميل مفاتيح API ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY environment variable is not set. OpenRouter functionality will be disabled.")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY environment variable is not set. Gemini backup functionality will be disabled.")


# إعدادات أخرى للتطبيق
APP_URL = os.environ.get("APP_URL") # مهم لـ HTTP-Referer
if not APP_URL:
    logger.warning("APP_URL environment variable is not set. Using a default which might cause issues with OpenRouter Referer check.")
    APP_URL = "http://localhost:5000" # قيمة افتراضية قد لا تعمل بشكل صحيح

APP_TITLE = "Yasmin GPT Chat"

# --- تعريف نماذج قاعدة البيانات (مدمجة هنا) ---

class Conversation(Base):
    __tablename__ = "conversations" # استخدام صيغة الجمع أفضل

    # استخدام Mapped و mapped_column للأسلوب الحديث
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # العلاقة مع الرسائل (one-to-many)
    # cascade: حذف الرسائل تلقائيًا عند حذف المحادثة
    # back_populates: يربط العلاقة بالاتجاه المعاكس في نموذج Message
    # order_by: ترتيب الرسائل تلقائيًا عند الوصول إليها من المحادثة
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="selectin" # تحميل الرسائل مع المحادثة بكفاءة
    )

    def add_message(self, role: str, content: str):
        """ Helper method to add a message to this conversation """
        new_message = Message(
            conversation_id=self.id, # ربط الرسالة بهذه المحادثة
            role=role,
            content=content
        )
        # إضافة الرسالة إلى الجلسة (سيتم ربطها تلقائيًا بالمحادثة عبر العلاقة)
        db.session.add(new_message)
        # تحديث وقت تعديل المحادثة (يمكن أن يتم تلقائيًا عبر onupdate إذا كان الحقل موجودًا)
        self.updated_at = datetime.now(timezone.utc)
        return new_message # قد يكون مفيدًا إرجاع الرسالة المُنشأة

    def to_dict(self):
        """ Serialize conversation and its messages to a dictionary """
        return {
            "id": str(self.id), # تحويل UUID إلى سلسلة
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # تحويل كل رسالة في قائمة الرسائل إلى قاموس
            "messages": [message.to_dict() for message in self.messages]
        }

    def __repr__(self):
        return f"<Conversation(id={self.id}, title='{self.title}')>"

class Message(Base):
    __tablename__ = "messages" # استخدام صيغة الجمع

    id: Mapped[int] = mapped_column(primary_key=True) # استخدام auto-incrementing integer كـ PK
    # ربط بالـ UUID الخاص بالمحادثة
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False) # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # العلاقة العكسية مع المحادثة (many-to-one)
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    def to_dict(self):
        """ Serialize message to a dictionary """
        return {
            "id": self.id,
            "conversation_id": str(self.conversation_id), # تحويل UUID إلى سلسلة
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat()
        }

    def __repr__(self):
        return f"<Message(id={self.id}, role='{self.role}', conv_id={self.conversation_id})>"


# --- الردود الاحتياطية (للاستخدام عند فشل كل الـ APIs) ---
offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا ياسمين. للأسف، لا يوجد اتصال بالإنترنت حاليًا.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا ياسمين. أعتذر، خدمة الإنترنت غير متوفرة حاليًا.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت."
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت أو بخدمات الذكاء الاصطناعي."

# --- دالة استدعاء Gemini API (النموذج الاحتياطي) ---
def call_gemini_api(messages_list, temperature, max_tokens=512):
    """Call the Gemini API as a backup"""
    if not GEMINI_API_KEY:
        logger.warning("Gemini API key not available for backup.")
        return None, "مفتاح Gemini API غير متوفر"

    try:
        # تحويل تنسيق الرسائل لـ Gemini
        gemini_contents = []
        for msg in messages_list:
            role = "user" if msg["role"] == "user" else "model"
            gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        # التأكد من أن آخر رسالة هي من المستخدم (متطلب في بعض إصدارات Gemini API)
        if gemini_contents and gemini_contents[-1]['role'] != 'user':
             logger.warning("Gemini API call adjusted: Last message was not from user, appending dummy user message or skipping.")
             # يمكنك إما إضافة رسالة مستخدم فارغة أو محاولة الاستدعاء كما هو أو إرجاع خطأ
             # For simplicity, let's try to call anyway, but log it.
             # Or potentially return an error: return None, "Gemini requires the last message to be from the user."

        # بناء الـ URL بشكل آمن
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}" # استخدام 1.5 flash كمثال
        logger.debug(f"Calling Gemini API ({gemini_url.split('?')[0]}) with {len(gemini_contents)} parts...")

        response = requests.post(
            url=gemini_url,
            headers={'Content-Type': 'application/json'},
            json={
                "contents": gemini_contents,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature
                }
            },
            timeout=30 # مهلة معقولة
        )
        response.raise_for_status() # إثارة خطأ لأكواد 4xx/5xx
        response_data = response.json()

        # التحقق من الاستجابة ومعالجة الردود المحظورة
        if 'candidates' not in response_data or not response_data['candidates']:
            block_reason = response_data.get('promptFeedback', {}).get('blockReason', 'Unknown reason')
            safety_ratings = response_data.get('promptFeedback', {}).get('safetyRatings', [])
            logger.error(f"Gemini response missing candidates or blocked. Reason: {block_reason}. Ratings: {safety_ratings}")
            return None, f"الرد محظور بواسطة فلتر السلامة: {block_reason}"

        # استخلاص النص
        text_parts = []
        try:
            for part in response_data['candidates'][0]['content']['parts']:
                if 'text' in part:
                    text_parts.append(part['text'])
        except (KeyError, IndexError, TypeError) as e:
             logger.error(f"Error parsing Gemini response content structure: {e}. Response: {response_data}")
             return None, "خطأ في تحليل استجابة Gemini"

        if text_parts:
            return "".join(text_parts).strip(), None
        else:
            logger.warning(f"No text found in Gemini response parts. Response: {response_data}")
            return None, "لم يتم العثور على نص في استجابة Gemini"

    except requests.exceptions.Timeout:
        logger.error("Gemini API request timed out.")
        return None, "استجابة النموذج الاحتياطي (Gemini) استغرقت وقتاً طويلاً"
    except requests.exceptions.HTTPError as e:
         error_body = e.response.text
         logger.error(f"Gemini API HTTP error ({e.response.status_code}): {error_body}")
         try:
             error_json = e.response.json()
             error_details = error_json.get("error", {}).get("message", error_body)
         except json.JSONDecodeError:
             error_details = error_body[:200] # عرض جزء من النص
         return None, f"خطأ HTTP من Gemini: {error_details}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Gemini API: {e}")
        return None, f"خطأ في الاتصال بالنموذج الاحتياطي (Gemini): {e}"
    except Exception as e:
        logger.error(f"Unexpected error processing Gemini response: {e}", exc_info=True)
        return None, f"خطأ غير متوقع في معالجة استجابة Gemini: {e}"


# --- مسارات Flask (Routes) ---

@app.route('/')
def index():
    """Route for the main chat page."""
    logger.info(f"Serving main page (index.html) requested by {request.remote_addr}")
    # تمرير عنوان التطبيق إلى القالب
    return render_template('index.html', app_title=APP_TITLE)

@app.route('/api/chat', methods=['POST'])
def chat():
    """API route for handling chat messages."""
    try:
        data = request.json
        if not data:
            logger.warning("Received empty JSON payload for /api/chat")
            return jsonify({"error": "الطلب غير صالح (بيانات فارغة)"}), 400

        messages_for_api = data.get('history', []) # الواجهة الأمامية ترسل السجل كاملاً
        if not messages_for_api or not isinstance(messages_for_api, list) or messages_for_api[-1].get('role') != 'user':
             logger.warning(f"Invalid 'history' received in /api/chat: {messages_for_api}")
             return jsonify({"error": "تنسيق سجل المحادثة غير صالح أو آخر رسالة ليست للمستخدم"}), 400

        user_message = messages_for_api[-1]['content'].strip()
        model = data.get('model', 'mistralai/mistral-7b-instruct-v0.2') # نموذج افتراضي محدث
        conversation_id_str = data.get('conversation_id') # قد يكون null
        temperature = float(data.get('temperature', 0.7)) # تأكد من تحويله إلى float
        max_tokens = int(data.get('max_tokens', 1024)) # تأكد من تحويله إلى int وزيادة القيمة الافتراضية قليلاً

        if not user_message:
             logger.warning("Received empty user message content in /api/chat history.")
             return jsonify({"error": "محتوى الرسالة فارغ"}), 400

        # --- الحصول على المحادثة أو إنشاؤها ---
        db_conversation = None
        conversation_id = None
        if conversation_id_str:
            try:
                conversation_id = uuid.UUID(conversation_id_str) # تحويل النص إلى UUID
                # استخدام الأسلوب الحديث للاستعلام
                stmt = select(Conversation).filter_by(id=conversation_id)
                db_conversation = db.session.execute(stmt).scalar_one_or_none()
                if db_conversation:
                    logger.info(f"Found existing conversation: {conversation_id}")
                else:
                     logger.warning(f"Conversation ID '{conversation_id_str}' provided but not found in DB.")
                     conversation_id = None # اعتبرها محادثة جديدة
            except ValueError:
                logger.warning(f"Invalid UUID format received for conversation_id: {conversation_id_str}")
                conversation_id = None # اعتبرها محادثة جديدة

        if not db_conversation:
            conversation_id = uuid.uuid4() # إنشاء UUID جديد
            initial_title = user_message.split('\n')[0][:60] # عنوان أطول قليلاً
            logger.info(f"Creating new conversation with ID: {conversation_id}, title: '{initial_title}'")
            db_conversation = Conversation(id=conversation_id, title=initial_title or "محادثة جديدة")
            db.session.add(db_conversation)
            # لا تقم بعمل commit الآن، انتظر حتى نهاية العملية

        # --- إضافة رسالة المستخدم (مع منع التكرار البسيط) ---
        # جلب آخر رسالة محفوظة *لهذه المحادثة*
        stmt_last_msg = select(Message)\
                        .filter_by(conversation_id=db_conversation.id)\
                        .order_by(Message.created_at.desc())\
                        .limit(1)
        last_db_message = db.session.execute(stmt_last_msg).scalar_one_or_none()

        # التحقق من التكرار (إذا كانت نفس الرسالة ونفس الدور ومنذ فترة قصيرة)
        time_since_last = (datetime.now(timezone.utc) - last_db_message.created_at).total_seconds() if last_db_message else float('inf')
        if not last_db_message or not (last_db_message.role == 'user' and last_db_message.content == user_message and time_since_last < 10): # زد الوقت قليلاً
            logger.debug(f"Adding user message to DB for conversation {db_conversation.id}")
            user_msg_db = db_conversation.add_message('user', user_message)
            # قد نحتاج لعمل flush للحصول على معرف الرسالة إذا احتجناه، لكن لا يبدو ضروريًا الآن
            # db.session.flush([user_msg_db])
        else:
             logger.warning(f"Skipping duplicate user message for conversation {db_conversation.id}. Last message time diff: {time_since_last:.2f}s")
             # إذا كانت مكررة، استخدم آخر رسالة مستخدم موجودة كمرجع
             user_msg_db = last_db_message

        # --- استدعاء واجهات برمجة التطبيقات (API Calls) ---
        ai_reply = None
        error_message = None
        used_backup = False
        api_source = "N/A" # لتتبع مصدر الرد

        # 1. محاولة OpenRouter
        if OPENROUTER_API_KEY:
            api_source = "OpenRouter"
            try:
                logger.debug(f"Sending request to OpenRouter with model: {model}, history size: {len(messages_for_api)}")
                openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json", # إضافة Content-Type
                    "HTTP-Referer": APP_URL,
                    "X-Title": APP_TITLE,
                }
                payload = {
                    "model": model,
                    "messages": messages_for_api,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                response = requests.post(url=openrouter_url, headers=headers, json=payload, timeout=45)
                response.raise_for_status() # Check for 4xx/5xx errors
                api_response = response.json()

                # التحقق من صحة الرد
                if api_response.get('choices') and api_response['choices'][0].get('message'):
                    ai_reply = api_response['choices'][0]['message'].get('content', '').strip()
                    if not ai_reply:
                         logger.warning(f"OpenRouter returned an empty content string for model {model}. Response: {api_response}")
                         # لا تعتبره خطأ فادحًا، قد يكون بسبب مرشحات المحتوى
                    else:
                        logger.info(f"Received reply from OpenRouter ({model}).")
                    # تسجيل التكلفة والاستخدام إذا كانت متوفرة
                    if 'usage' in api_response: logger.info(f"OpenRouter usage: {api_response['usage']}")
                else:
                    logger.error(f"OpenRouter response structure invalid: {api_response}")
                    error_message = "استجابة غير متوقعة من OpenRouter"

            except requests.exceptions.Timeout:
                logger.error("OpenRouter API request timed out.")
                error_message = "استجابة OpenRouter استغرقت وقتاً طويلاً"
            except requests.exceptions.HTTPError as e:
                error_body = e.response.text
                logger.error(f"OpenRouter API HTTP error ({e.response.status_code}): {error_body}")
                try:
                     error_json = e.response.json()
                     error_details = error_json.get("error", {}).get("message", error_body)
                except json.JSONDecodeError:
                     error_details = error_body[:200]
                error_message = f"خطأ HTTP من OpenRouter: {error_details}"
            except requests.exceptions.RequestException as e:
                logger.error(f"Error calling OpenRouter API: {e}", exc_info=True)
                error_message = f"خطأ في الاتصال بـ OpenRouter: {e}"
            except Exception as e:
                logger.error(f"Unexpected error processing OpenRouter response: {e}", exc_info=True)
                error_message = f"خطأ غير متوقع في معالجة استجابة OpenRouter: {e}"

        # 2. محاولة Gemini كاحتياطي إذا فشل OpenRouter
        if not ai_reply and GEMINI_API_KEY:
            api_source = "Gemini (Backup)"
            logger.info("OpenRouter failed or unavailable. Trying Gemini API as backup...")
            # نمرر نفس قائمة الرسائل التي أُرسلت إلى OpenRouter
            ai_reply, backup_error = call_gemini_api(messages_for_api, temperature, max_tokens)
            if ai_reply:
                used_backup = True
                error_message = None # مسح خطأ OpenRouter إذا نجح Gemini
                logger.info("Received reply from Gemini (backup).")
            else:
                logger.error(f"Gemini backup also failed: {backup_error}")
                # احتفظ بخطأ OpenRouter الأصلي إذا كان موجودًا، أو استخدم خطأ Gemini
                error_message = error_message or f"فشل النموذج الاحتياطي (Gemini): {backup_error}"

        # 3. إذا فشل كلاهما، استخدم الردود المحددة مسبقًا
        if not ai_reply:
            api_source = "Offline Fallback"
            logger.warning("Both API calls failed. Falling back to predefined offline responses.")
            matched_offline = False
            user_msg_lower = user_message.lower()
            for key, response_text in offline_responses.items():
                if key.lower() in user_msg_lower:
                    ai_reply = response_text
                    matched_offline = True
                    logger.info(f"Matched offline response for key: '{key}'")
                    break
            if not matched_offline:
                ai_reply = default_offline_response
                logger.info("Using default offline response.")

        # --- حفظ رد الـ AI وعمل Commit ---
        if ai_reply:
            logger.debug(f"Adding assistant reply (from {api_source}) to DB for conversation {db_conversation.id}")
            assistant_msg_db = db_conversation.add_message('assistant', ai_reply)
            try:
                db.session.commit() # حفظ كل التغييرات (المحادثة الجديدة، رسالة المستخدم، رسالة المساعد)
                logger.info(f"Successfully committed messages for conversation {db_conversation.id}")
                # إعادة الرد إلى الواجهة الأمامية
                return jsonify({
                    "id": str(db_conversation.id), # تأكد من إرسال المعرف دائمًا
                    "content": ai_reply,
                    "used_backup": used_backup,
                    "new_conversation_id": str(conversation_id) if not conversation_id_str else None # إشارة إذا كانت المحادثة جديدة
                })
            except SQLAlchemyError as e:
                 logger.error(f"Database commit error after getting AI reply: {e}", exc_info=True)
                 db.session.rollback()
                 return jsonify({"error": f"حدث خطأ أثناء حفظ الرد في قاعدة البيانات: {e}"}), 500
        else:
            # هذا لا يجب أن يحدث نظريًا بسبب الـ Fallback، لكن كإجراء احترازي
            logger.error("Failed to generate any response (AI or offline).")
            db.session.rollback() # تراجع عن إضافة رسالة المستخدم إذا لم نتمكن من الرد
            return jsonify({"error": error_message or "فشل توليد استجابة"}), 500

    except Exception as e:
        # معالجة أي أخطاء غير متوقعة في نقطة النهاية بأكملها
        logger.error(f"Critical error in /api/chat endpoint: {e}", exc_info=True)
        # محاولة التراجع عن أي تغييرات قد تكون معلقة
        try:
            db.session.rollback()
        except Exception as rollback_err:
             logger.error(f"Error during rollback after critical chat error: {rollback_err}", exc_info=True)
        return jsonify({"error": f"حدث خطأ داخلي خطير في الخادم: {e}"}), 500


# --- نقاط نهاية إدارة المحادثات ---

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """API route to get a list of all conversations (simplified)."""
    try:
        logger.info("Fetching conversation list...")
        # الاستعلام عن المحادثات مرتبة حسب آخر تحديث
        stmt = select(Conversation).order_by(desc(Conversation.updated_at))
        conversations = db.session.execute(stmt).scalars().all()

        # تحويل القائمة إلى تنسيق JSON المطلوب
        conversations_list = [
            {
                "id": str(conv.id),
                "title": conv.title,
                "updated_at": conv.updated_at.isoformat()
            }
            for conv in conversations
        ]
        logger.info(f"Retrieved {len(conversations_list)} conversations.")
        return jsonify(conversations_list)
    except SQLAlchemyError as e:
        logger.error(f"Database error getting conversations list: {e}", exc_info=True)
        return jsonify({"error": f"خطأ في استرجاع قائمة المحادثات من قاعدة البيانات: {e}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error getting conversations list: {e}", exc_info=True)
        return jsonify({"error": f"خطأ غير متوقع في استرجاع المحادثات: {e}"}), 500


@app.route('/api/conversations/<uuid:conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    """API route to get a specific conversation with all its messages."""
    # استخدام محول <uuid:> في المسار للتحقق من التنسيق وتمرير كائن UUID
    try:
        logger.info(f"Fetching conversation details for ID: {conversation_id}")
        # الاستعلام عن المحادثة المحددة (مع تحميل الرسائل تلقائيًا بسبب lazy='selectin')
        stmt = select(Conversation).filter_by(id=conversation_id)
        conversation = db.session.execute(stmt).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Conversation not found for ID: {conversation_id}")
            return jsonify({"error": "المحادثة المطلوبة غير موجودة"}), 404

        logger.info(f"Conversation found: '{conversation.title}', returning details.")
        # استخدام دالة to_dict للحصول على البيانات المنظمة
        return jsonify(conversation.to_dict())
    except SQLAlchemyError as e:
        logger.error(f"Database error getting conversation {conversation_id}: {e}", exc_info=True)
        return jsonify({"error": f"خطأ قاعدة بيانات عند استرجاع تفاصيل المحادثة: {e}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error getting conversation {conversation_id}: {e}", exc_info=True)
        return jsonify({"error": f"خطأ غير متوقع في استرجاع المحادثة: {e}"}), 500


@app.route('/api/conversations/<uuid:conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    """API route to delete a specific conversation."""
    try:
        logger.info(f"Attempting to delete conversation with ID: {conversation_id}")
        # الاستعلام عن المحادثة المراد حذفها
        stmt = select(Conversation).filter_by(id=conversation_id)
        conversation = db.session.execute(stmt).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Attempted to delete non-existent conversation: {conversation_id}")
            return jsonify({"error": "المحادثة المطلوب حذفها غير موجودة"}), 404

        # حذف المحادثة (سيتم حذف الرسائل تلقائيًا بسبب cascade)
        db.session.delete(conversation)
        db.session.commit()
        logger.info(f"Successfully deleted conversation: {conversation_id}")
        return jsonify({"success": True, "message": "تم حذف المحادثة وجميع رسائلها بنجاح"})

    except SQLAlchemyError as e:
        logger.error(f"Database error deleting conversation {conversation_id}: {e}", exc_info=True)
        db.session.rollback() # تراجع عن أي تغييرات
        return jsonify({"error": f"خطأ قاعدة بيانات أثناء حذف المحادثة: {e}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error deleting conversation {conversation_id}: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": f"خطأ غير متوقع أثناء حذف المحادثة: {e}"}), 500


@app.route('/api/conversations/<uuid:conversation_id>/title', methods=['PUT'])
def update_conversation_title(conversation_id):
    """API route to update the title of a specific conversation."""
    try:
        data = request.json
        new_title = data.get('title', '').strip()

        if not new_title or len(new_title) > 100: # تحقق من الطول أيضًا
            logger.warning(f"Invalid title received for conversation {conversation_id}: '{new_title}'")
            return jsonify({"error": "عنوان المحادثة مطلوب ويجب ألا يتجاوز 100 حرف"}), 400

        logger.info(f"Attempting to update title for conversation {conversation_id} to '{new_title}'")
        # استخدام الأسلوب الحديث للتحديث (أكثر كفاءة)
        stmt = update(Conversation)\
               .where(Conversation.id == conversation_id)\
               .values(title=new_title, updated_at=datetime.now(timezone.utc))\
               .returning(Conversation.id) # للتأكد من أن الصف تم تحديثه

        result = db.session.execute(stmt)
        updated_id = result.scalar_one_or_none() # سيحتوي على الـ ID إذا تم التحديث

        if updated_id:
            db.session.commit()
            logger.info(f"Successfully updated title for conversation: {conversation_id}")
            return jsonify({"success": True, "message": "تم تحديث عنوان المحادثة بنجاح"})
        else:
            # التحقق مما إذا كانت المحادثة موجودة أصلاً
            exists_stmt = select(Conversation.id).filter_by(id=conversation_id)
            exists = db.session.execute(exists_stmt).scalar_one_or_none()
            if not exists:
                 logger.warning(f"Attempted to update title for non-existent conversation: {conversation_id}")
                 return jsonify({"error": "المحادثة المطلوب تحديثها غير موجودة"}), 404
            else:
                 # هذا لا ينبغي أن يحدث إذا كان الصف موجودًا ولم يتم تحديثه
                 logger.error(f"Failed to update title for conversation {conversation_id}, but it exists.")
                 db.session.rollback()
                 return jsonify({"error": "فشل تحديث العنوان لسبب غير معروف."}), 500

    except SQLAlchemyError as e:
        logger.error(f"Database error updating title for conversation {conversation_id}: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": f"خطأ قاعدة بيانات أثناء تحديث العنوان: {e}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error updating title for conversation {conversation_id}: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": f"خطأ غير متوقع أثناء تحديث العنوان: {e}"}), 500


@app.route('/api/regenerate', methods=['POST'])
def regenerate_response():
    """API route for regenerating the last AI response."""
    try:
        data = request.json
        if not data:
             return jsonify({"error": "الطلب غير صالح (بيانات فارغة)"}), 400

        conversation_id_str = data.get('conversation_id')
        model = data.get('model', 'mistralai/mistral-7b-instruct-v0.2')
        temperature = float(data.get('temperature', 0.7))
        max_tokens = int(data.get('max_tokens', 1024))

        if not conversation_id_str:
            return jsonify({"error": "معرف المحادثة مطلوب لإعادة التوليد"}), 400

        try:
            conversation_id = uuid.UUID(conversation_id_str)
        except ValueError:
            return jsonify({"error": "تنسيق معرف المحادثة غير صالح"}), 400

        logger.info(f"Received regenerate request for conversation: {conversation_id}, using model: {model}")

        # --- الحصول على المحادثة والرسائل ---
        # استخدام joinload لتحميل الرسائل بكفاءة أكبر هنا
        stmt = select(Conversation).options(relationship(Conversation.messages)).filter_by(id=conversation_id)
        conversation = db.session.execute(stmt).scalar_one_or_none()

        if not conversation:
            return jsonify({"error": "المحادثة المطلوبة لإعادة التوليد غير موجودة"}), 404

        # الرسائل مرتبة بالفعل حسب created_at بفضل order_by في العلاقة
        messages = conversation.messages

        if not messages:
            return jsonify({"error": "لا توجد رسائل في المحادثة لإعادة التوليد"}), 400

        # --- حذف آخر رسالة للـ AI ---
        last_message = messages[-1]
        if last_message.role != 'assistant':
            logger.warning(f"Last message in conv {conversation_id} is not from assistant. Cannot regenerate.")
            return jsonify({"error": "آخر رسالة ليست من المساعد، لا يمكن إعادة التوليد."}), 400

        logger.debug(f"Deleting last assistant message (ID: {last_message.id}) for regeneration.")
        # حذف الرسالة من الجلسة (سيتم حذفها من قاعدة البيانات عند الـ commit)
        db.session.delete(last_message)
        # إزالتها أيضًا من القائمة المحلية للرسائل
        messages_for_api = [msg.to_dict() for msg in messages[:-1]] # استبعاد الرسالة الأخيرة المحذوفة

        if not messages_for_api:
            logger.warning(f"No user messages left after removing assistant message in conv {conversation_id}.")
            db.session.rollback() # تراجع عن الحذف
            return jsonify({"error": "لا توجد رسائل متبقية لإرسالها بعد حذف رد المساعد"}), 400

        # --- إعادة استدعاء واجهات برمجة التطبيقات ---
        ai_reply = None
        error_message = None
        used_backup = False
        api_source = "N/A"

        # 1. محاولة OpenRouter
        if OPENROUTER_API_KEY:
            api_source = "OpenRouter (Regen)"
            try:
                logger.debug(f"Regen: Sending request to OpenRouter with model: {model}, history size: {len(messages_for_api)}")
                # (نفس كود استدعاء OpenRouter كما في /api/chat)
                openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
                headers = { "Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": APP_URL, "X-Title": APP_TITLE }
                payload = { "model": model, "messages": messages_for_api, "temperature": temperature, "max_tokens": max_tokens }
                response = requests.post(url=openrouter_url, headers=headers, json=payload, timeout=45)
                response.raise_for_status()
                api_response = response.json()
                if api_response.get('choices') and api_response['choices'][0].get('message'):
                    ai_reply = api_response['choices'][0]['message'].get('content', '').strip()
                    if ai_reply: logger.info(f"Regen: Received reply from OpenRouter ({model}).")
                else:
                     logger.error(f"Regen: OpenRouter response structure invalid: {api_response}")
                     error_message = "استجابة غير متوقعة من OpenRouter أثناء إعادة التوليد"
            except Exception as e: # التقاط جميع الأخطاء من استدعاء API
                logger.error(f"Regen: Error calling OpenRouter: {e}", exc_info=True)
                # قم بتحليل الخطأ وتعيين error_message كما في /api/chat
                if isinstance(e, requests.exceptions.Timeout): error_message = "مهلة OpenRouter أثناء إعادة التوليد"
                elif isinstance(e, requests.exceptions.HTTPError): error_message = f"خطأ HTTP من OpenRouter أثناء إعادة التوليد: {e.response.status_code}"
                else: error_message = f"خطأ OpenRouter أثناء إعادة التوليد: {e}"


        # 2. محاولة Gemini كاحتياطي
        if not ai_reply and GEMINI_API_KEY:
            api_source = "Gemini (Backup Regen)"
            logger.info("Regen: OpenRouter failed. Trying Gemini backup...")
            # تحويل الرسائل المتبقية إلى تنسيق Gemini
            gemini_api_messages = [{"role": msg['role'], "content": msg['content']} for msg in messages_for_api]
            ai_reply, backup_error = call_gemini_api(gemini_api_messages, temperature, max_tokens)
            if ai_reply:
                used_backup = True
                error_message = None
                logger.info("Regen: Received reply from Gemini (backup).")
            else:
                 logger.error(f"Regen: Gemini backup also failed: {backup_error}")
                 error_message = error_message or f"فشل إعادة التوليد بالنموذج الاحتياطي: {backup_error}"

        # 3. استخدام الردود المحددة مسبقًا (قد لا يكون منطقيًا في إعادة التوليد، لكن كاحتياطي أخير)
        if not ai_reply:
            api_source = "Offline Fallback (Regen)"
            logger.warning("Regen: Both APIs failed. Falling back to offline responses.")
            # يمكنك إما إرجاع خطأ مباشرة أو استخدام نفس منطق الـ offline
            # user_msg_lower = messages_for_api[-1]['content'].lower() # آخر رسالة للمستخدم
            # ... (نفس كود الـ offline fallback) ...
            # للتبسيط، سنرجع خطأ هنا بدلاً من رد offline غير ذي صلة ربما
            ai_reply = None # التأكد من عدم وجود رد
            error_message = error_message or "فشل إعادة توليد الرد من جميع المصادر."


        # --- حفظ الرد الجديد أو التراجع ---
        if ai_reply:
            logger.debug(f"Regen: Adding new assistant reply (from {api_source}) to DB for conv {conversation_id}")
            new_assistant_msg = conversation.add_message('assistant', ai_reply)
            try:
                db.session.commit() # حفظ حذف الرسالة القديمة وإضافة الجديدة
                logger.info(f"Regen: Successfully committed regenerated message for conv {conversation_id}")
                return jsonify({
                    "content": ai_reply,
                    "used_backup": used_backup,
                    # قد ترغب في إرسال معرف الرسالة الجديدة أيضًا
                    # "new_message_id": new_assistant_msg.id
                })
            except SQLAlchemyError as e:
                 logger.error(f"Regen: Database commit error: {e}", exc_info=True)
                 db.session.rollback() # تراجع عن كل شيء (الحذف والإضافة)
                 return jsonify({"error": f"حدث خطأ أثناء حفظ الرد المُعاد توليده: {e}"}), 500
        else:
            # فشلت إعادة التوليد، تراجع عن حذف الرسالة الأصلية
            logger.warning(f"Regen: Failed to generate new reply for conv {conversation_id}. Rolling back deletion.")
            db.session.rollback()
            return jsonify({"error": error_message or "فشل إعادة توليد الاستجابة"}), 500

    except Exception as e:
        logger.error(f"Critical error in /api/regenerate endpoint: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception as rollback_err:
             logger.error(f"Error during rollback after critical regenerate error: {rollback_err}", exc_info=True)
        return jsonify({"error": f"خطأ داخلي خطير أثناء إعادة التوليد: {e}"}), 500

# --- معالجات الأخطاء العامة ---
@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        logger.warning(f"404 Not Found for API route: {request.path} from {request.remote_addr}")
        return jsonify({"error": "نقطة النهاية المطلوبة غير موجودة."}), 404
    logger.warning(f"404 Not Found for page: {request.path} from {request.remote_addr}")
    # تأكد من وجود 'templates/404.html' أو قدم رسالة بسيطة
    return render_template('error.html', error_code=404, error_message="الصفحة غير موجودة"), 404

@app.errorhandler(500)
def internal_error(error):
    original_exception = getattr(error, 'original_exception', error)
    logger.error(f"500 Internal Server Error for {request.path} from {request.remote_addr}: {original_exception}", exc_info=True)
    try:
        db.session.rollback()
        logger.info("Database session rolled back after 500 error.")
    except Exception as e:
        logger.error(f"Error during rollback after 500 error: {e}", exc_info=True)

    if request.path.startswith('/api/'):
        return jsonify({"error": "حدث خطأ داخلي غير متوقع في الخادم."}), 500
    # تأكد من وجود 'templates/500.html' أو 'templates/error.html'
    return render_template('error.html', error_code=500, error_message="حدث خطأ داخلي في الخادم"), 500

@app.errorhandler(Exception) # معالج عام لأي استثناءات أخرى
def handle_exception(e):
     # التعامل مع أخطاء HTTP التي قد لا تكون 500
     if isinstance(e, requests.exceptions.HTTPError):
         # تم التعامل معها غالبًا في نقاط النهاية، لكن كإجراء احترازي
         logger.error(f"Unhandled HTTPError for {request.path}: {e}", exc_info=True)
         status_code = e.response.status_code if e.response else 500
         if request.path.startswith('/api/'):
            return jsonify({"error": f"خطأ في الاتصال بخدمة خارجية: {e}"}), status_code
         else:
             return render_template('error.html', error_code=status_code, error_message=f"خطأ في الاتصال بخدمة خارجية: {e}"), status_code

     # التعامل مع أخطاء SQLAlchemy التي قد لا تكون 500
     if isinstance(e, SQLAlchemyError):
         logger.error(f"Unhandled SQLAlchemyError for {request.path}: {e}", exc_info=True)
         db.session.rollback()
         if request.path.startswith('/api/'):
             return jsonify({"error": "حدث خطأ في قاعدة البيانات."}), 500
         else:
             return render_template('error.html', error_code=500, error_message="حدث خطأ في قاعدة البيانات."), 500

     # للأخطاء العامة الأخرى
     logger.error(f"Unhandled Exception for {request.path}: {e}", exc_info=True)
     try:
         db.session.rollback()
     except Exception as rollback_err:
         logger.error(f"Error during rollback after unhandled exception: {rollback_err}", exc_info=True)

     if request.path.startswith('/api/'):
         return jsonify({"error": "حدث خطأ غير متوقع."}), 500
     else:
         return render_template('error.html', error_code=500, error_message="حدث خطأ غير متوقع."), 500


# --- إنشاء جداول قاعدة البيانات عند بدء التشغيل ---
# هذا ضروري ليعمل التطبيق عند تشغيله لأول مرة على Render أو محليًا
def initialize_database():
    with app.app_context():
        logger.info("Application context acquired. Attempting to create database tables...")
        try:
            # هذا الأمر آمن للتشغيل عدة مرات
            db.create_all()
            logger.info("Database tables checked/created successfully.")
        except SQLAlchemyError as e:
            # حاول إظهار الخطأ بدون بيانات الاعتماد إذا كان خطأ اتصال
            db_uri_safe = str(app.config.get("SQLALCHEMY_DATABASE_URI"))
            if "@" in db_uri_safe:
                db_uri_safe = db_uri_safe.split("@")[1] # إظهار ما بعد @ فقط
            logger.error(f"FATAL: SQLAlchemyError occurred during db.create_all() for DB: ...@{db_uri_safe}. Error: {e}", exc_info=False) # لا تظهر تفاصيل كثيرة
            raise SystemExit(f"Database initialization failed: {e}") from e
        except Exception as e:
            logger.error(f"FATAL: An unexpected error occurred during db.create_all(): {e}", exc_info=True)
            raise SystemExit(f"Unexpected database initialization error: {e}") from e

# استدعاء دالة تهيئة قاعدة البيانات
initialize_database()
logger.info("Database initialization routine finished.")

# --- نقطة الدخول لـ Gunicorn/WSGI Server (لا حاجة لـ app.run) ---
# Render سيستخدم أمرًا مثل `gunicorn app:app`
# الكود التالي اختياري ولكنه يساعد في تهيئة التسجيل عند استخدام Gunicorn
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    logger.info("Application started via WSGI server (like Gunicorn). Logging handlers configured.")
else:
     # يمكنك إضافة هذا لتشغيل التطبيق محليًا بسهولة للتجربة
     logger.info("Starting Flask development server (use Gunicorn/WSGI for production)...")
     # Render لن يستخدم هذا الجزء، لكنه مفيد للاختبار المحلي
     port = int(os.environ.get("PORT", 5001)) # استخدم منفذ مختلف عن الشائع 5000 لتجنب التعارضات
     app.run(host='0.0.0.0', port=port, debug=False) # لا تستخدم debug=True في الإنتاج

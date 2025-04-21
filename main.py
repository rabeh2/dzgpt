import os
import logging
from datetime import datetime, timezone
from functools import wraps
import json # لاستخدامه في معالجة أخطاء API بشكل أفضل

from flask import (
    Flask,
    render_template,
    jsonify,
    session,
    request
)
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session # للجلسات من جانب الخادم
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
import requests # لاستدعاء OpenRouter API

# --- التهيئة ---
load_dotenv() # تحميل متغيرات البيئة من ملف .env

# تهيئة التسجيل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- تهيئة تطبيق فلاسك ---
app = Flask(__name__)

# --- إعدادات الأمان والجلسات ---
# هام: حافظ على SECRET_KEY سريًا تمامًا في بيئة الإنتاج! قم بتحميله من البيئة.
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'default-insecure-secret-key-please-change')
if app.config['SECRET_KEY'] == 'default-insecure-secret-key-please-change':
    logger.warning("SESSION_SECRET is set to the default insecure value. Please set a strong secret key in your environment variables.")

# تهيئة الجلسات من جانب الخادم (تتجنب ملفات تعريف الارتباط الكبيرة، أكثر أمانًا)
app.config['SESSION_TYPE'] = 'filesystem' # أو 'redis', 'sqlalchemy', إلخ. مناسب لـ Replit/Render مبدئيًا
app.config['SESSION_PERMANENT'] = True # جعل الجلسات دائمة
app.config['SESSION_USE_SIGNER'] = True # توقيع كوكي الجلسة
# تأكد من أن APP_URL يبدأ بـ https في الإنتاج لتعيين Secure=True
is_production = not os.environ.get('FLASK_DEBUG', '').lower() in ['true', '1', 't']
app.config['SESSION_COOKIE_SECURE'] = is_production and os.environ.get('APP_URL', '').startswith('https')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' # أو 'Strict'

Session(app)

# --- تهيئة قاعدة البيانات ---
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    logger.error("DATABASE_URL environment variable not set.")
    # يمكنك هنا إيقاف التطبيق أو استخدام قاعدة بيانات مؤقتة إذا أردت
else:
    # التعامل مع البادئة 'postgres://' إذا قدمها Heroku/Render لـ SQLAlchemy < 1.4
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # تعطيل الحمل الإضافي لتتبع التعديلات
app.config['SQLALCHEMY_ECHO'] = False # اضبط على True لتصحيح استعلامات قاعدة البيانات

db = SQLAlchemy(app)

# --- نماذج قاعدة البيانات ---
class Message(db.Model):
    __tablename__ = 'messages' # اسم الجدول الصريح ممارسة جيدة
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(80), nullable=False, index=True) # مطلوب ومفهرس للبحث السريع
    role = db.Column(db.String(20), nullable=False) # 'user', 'assistant'
    content = db.Column(db.Text, nullable=False)
    model_used = db.Column(db.String(100), nullable=True) # تتبع النموذج الذي استجاب
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False) # استخدام timezone aware datetime

    def __repr__(self):
        return f'<Message {self.id} by {self.role} in session {self.session_id}>'

    def to_dict(self):
        """يقوم بتحويل كائن Message إلى قاموس."""
        return {
            'id': self.id,
            'session_id': self.session_id, # قد لا تحتاج لإرساله للواجهة دائمًا
            'role': self.role,
            'content': self.content,
            'model_used': self.model_used,
            'timestamp': self.timestamp.isoformat() # ISO 8601 format (includes timezone)
        }

    def to_api_format(self):
        """يحول الرسالة إلى التنسيق المطلوب لواجهات برمجة التطبيقات مثل OpenRouter."""
        return {"role": self.role, "content": self.content}


# --- النماذج المتاحة (مثال - يمكن تحميلها من ملف إعدادات) ---
# تأكد من تطابق هذه المعرفات مع المستخدمة في OpenRouter
AVAILABLE_MODELS = [
    {"id": "mistralai/mistral-7b-instruct-v0.2", "name": "Mistral 7B Instruct v0.2"},
    {"id": "google/gemma-7b-it", "name": "Google Gemma 7B"},
    {"id": "anthropic/claude-3-haiku-20240307", "name": "Claude 3 Haiku"},
    {"id": "meta-llama/llama-3-8b-instruct", "name": "LLaMA 3 8B Instruct"},
    {"id": "openai/gpt-3.5-turbo", "name": "GPT-3.5 Turbo"},
    # أضف نماذج أخرى يدعمها إعدادك وتأكد من صحة المعرفات من OpenRouter
]
# إنشاء قاموس للبحث السريع عن اسم النموذج إذا لزم الأمر
MODEL_ID_TO_NAME = {model['id']: model['name'] for model in AVAILABLE_MODELS}


# --- الدوال المساعدة / المُزخرفات (Decorators) ---
def ensure_session(f):
    """مُزخرف (Decorator) للتأكد من وجود جلسة قبل المتابعة."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'session_id' not in session:
            # إنشاء معرف جلسة فريد إذا لم يكن موجودًا
            session['session_id'] = os.urandom(24).hex()
            logger.info(f"New session created: {session['session_id']}")
        elif not isinstance(session['session_id'], str) or len(session['session_id']) != 48:
             # تحقق إضافي للتأكد من أن معرف الجلسة سليم
             logger.warning(f"Invalid session_id format found: {session.get('session_id')}. Creating new session.")
             session['session_id'] = os.urandom(24).hex()
        return f(*args, **kwargs)
    return decorated_function

# --- المسارات (Routes) ---

@app.route('/')
@ensure_session # التأكد من وجود الجلسة عند تحميل الصفحة الرئيسية
def index():
    """يقدم واجهة الدردشة الرئيسية (HTML)."""
    session_id = session.get('session_id')
    logger.info(f"Serving index.html for session: {session_id}")
    # تمرير البيانات الأولية اللازمة للواجهة
    return render_template('index.html',
                           available_models=AVAILABLE_MODELS,
                           initial_dark_mode=session.get('dark_mode', False),
                           initial_tts_enabled=session.get('tts_enabled', True))

@app.route('/api/history', methods=['GET'])
@ensure_session # نحتاج إلى الجلسة لجلب السجل
def get_history():
    """يجلب سجل الدردشة للجلسة الحالية."""
    session_id = session['session_id']
    logger.info(f"Fetching history for session: {session_id}")
    try:
        # استخدام SQLAlchemy 2.0 style query
        stmt = db.select(Message).filter_by(session_id=session_id).order_by(Message.timestamp.asc())
        messages = db.session.execute(stmt).scalars().all()

        history = [msg.to_dict() for msg in messages]
        logger.info(f"Retrieved {len(history)} messages for session {session_id}")
        return jsonify(history)

    except SQLAlchemyError as e:
        logger.error(f"Database error fetching history for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "Database error retrieving chat history."}), 500
    except Exception as e:
        logger.error(f"Unexpected error fetching history for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred."}), 500

@app.route('/api/models', methods=['GET'])
def get_models():
    """يُرجع قائمة النماذج المتاحة للذكاء الاصطناعي."""
    logger.info("Fetching available models list.")
    return jsonify(AVAILABLE_MODELS)

@app.route('/api/settings', methods=['GET'])
@ensure_session
def get_settings():
    """يحصل على إعدادات المستخدم المحددة المخزنة في الجلسة."""
    session_id = session['session_id']
    logger.debug(f"Fetching settings for session: {session_id}") # استخدام debug level هنا
    settings = {
        'darkMode': session.get('dark_mode', False), # الافتراضي هو False إذا لم يتم تعيينه
        'ttsEnabled': session.get('tts_enabled', True), # الافتراضي هو True
    }
    return jsonify(settings)

@app.route('/api/chat', methods=['POST'])
@ensure_session
def handle_chat():
    """يعالج رسائل المستخدم الواردة ويحصل على رد من الذكاء الاصطناعي."""
    session_id = session['session_id']
    data = request.get_json()

    # --- التحقق من صحة المدخلات ---
    if not data or 'message' not in data or 'model' not in data:
        logger.error(f"Invalid chat request data for session {session_id}: {data}")
        return jsonify({"error": "الطلب غير صالح. يجب أن يحتوي على 'message' و 'model'."}), 400

    user_message_content = data['message'].strip()
    selected_model = data['model']

    if not user_message_content:
         logger.warning(f"Empty message received for session {session_id}")
         return jsonify({"error": "الرسالة لا يمكن أن تكون فارغة."}), 400

    if selected_model not in MODEL_ID_TO_NAME:
        logger.error(f"Invalid model requested by session {session_id}: {selected_model}")
        return jsonify({"error": "النموذج المحدد غير مدعوم أو غير صالح."}), 400

    logger.info(f"Session {session_id}: User message received for model '{MODEL_ID_TO_NAME.get(selected_model, selected_model)}': '{user_message_content[:100]}...'") # تسجيل جزء من الرسالة

    # --- بدء التعامل مع قاعدة البيانات (بدون commit فوري) ---
    try:
        # --- 1. حفظ رسالة المستخدم في قاعدة البيانات ---
        user_message_db = Message(
            session_id=session_id,
            role='user',
            content=user_message_content
            # timestamp يتم تعيينه تلقائيًا
        )
        db.session.add(user_message_db)
        # يجب عمل flush للحصول على id إذا احتجته قبل الـ commit، ولكننا لا نحتاجه هنا الآن
        # db.session.flush()

        # --- 2. جلب السياق (آخر N رسائل) ---
        # تحديد عدد الرسائل للسياق (يمكن جعله قابلاً للتكوين)
        CONTEXT_MESSAGES_COUNT = 10
        stmt = db.select(Message)\
                 .filter_by(session_id=session_id)\
                 .order_by(Message.timestamp.desc())\
                 .limit(CONTEXT_MESSAGES_COUNT)
        recent_messages_db = db.session.execute(stmt).scalars().all()
        recent_messages_db.reverse() # ترتيبها من الأقدم للأحدث لتناسب API

        # إنشاء قائمة الرسائل للـ API (يجب أن تتضمن الرسالة الحالية للمستخدم)
        # إذا كانت الرسالة الحالية غير موجودة في recent_messages_db (بسبب limit أو أنها جديدة تمامًا)
        # يجب التأكد من وجودها. الطريقة الأبسط هي إضافتها دائمًا في النهاية بعد جلب السجل.
        # لكن بما أننا أضفناها للتو ولم نعمل commit/flush، فقد لا تكون موجودة في الاستعلام أعلاه.
        # لذا، نستخدم الكائن الذي أنشأناه مباشرة.
        # نأخذ الرسائل السابقة من الاستعلام (باستثناء الرسالة الحالية إن وجدت بالصدفة)
        api_messages_context = [msg.to_api_format() for msg in recent_messages_db if msg.id != user_message_db.id]
        # ثم نضيف رسالة المستخدم الحالية في النهاية
        api_messages_context.append(user_message_db.to_api_format())


        # --- 3. استدعاء OpenRouter API ---
        openrouter_api_key = os.environ.get('OPENROUTER_API_KEY')
        app_url = os.environ.get('APP_URL')
        if not app_url:
            app_url = request.url_root # كقيمة احتياطية إذا لم يتم تعيين APP_URL
            logger.warning(f"APP_URL environment variable not set. Using request.url_root as fallback for Referer: {app_url}")

        if not openrouter_api_key:
            logger.error("Fatal: OPENROUTER_API_KEY environment variable not set.")
            db.session.rollback() # تراجع عن إضافة رسالة المستخدم
            return jsonify({"error": "خدمة الدردشة غير مهيأة بشكل صحيح (Missing API Key)."}), 503 # Service Unavailable

        headers = {
            'Authorization': f'Bearer {openrouter_api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': app_url,
            'X-Title': 'Yasmin GPT Chat' # أو أي اسم تفضله لتطبيقك
        }
        payload = {
            'model': selected_model,
            'messages': api_messages_context,
            # يمكنك إضافة بارامترات أخرى هنا مثل temperature, max_tokens حسب الحاجة
            # 'temperature': 0.7,
            # 'max_tokens': 1000,
        }
        OPENROUTER_API_ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
        # زيادة مهلة الاستجابة قليلًا لأن النماذج قد تستغرق وقتًا
        API_TIMEOUT_SECONDS = 90

        logger.info(f"Session {session_id}: Calling OpenRouter ({OPENROUTER_API_ENDPOINT}) with model {selected_model}")
        api_response = requests.post(OPENROUTER_API_ENDPOINT, headers=headers, json=payload, timeout=API_TIMEOUT_SECONDS)

        # --- 4. معالجة رد الـ API ---
        api_response.raise_for_status() # سيثير خطأ HTTPError للأكواد 4xx أو 5xx

        response_data = api_response.json()
        # التحقق من وجود الرد بالشكل المتوقع
        if not response_data.get('choices') or not isinstance(response_data['choices'], list) or len(response_data['choices']) == 0:
            raise ValueError("Invalid response structure from API: 'choices' array is missing or empty.")

        ai_message_data = response_data['choices'][0].get('message', {})
        ai_message_content = ai_message_data.get('content', '').strip()

        if not ai_message_content:
             # أحيانًا تُرجع الـ API ردًا فارغًا لأسباب مثل مرشحات المحتوى
             logger.warning(f"Session {session_id}: Received empty content from model {selected_model}.")
             # يمكنك هنا إرجاع رسالة مخصصة أو محاولة نموذج احتياطي
             ai_message_content = "(لم يتمكن النموذج من إنشاء رد لهذه الرسالة)" # رسالة مؤقتة

        logger.info(f"Session {session_id}: AI response received from {selected_model}: '{ai_message_content[:100]}...'")

        # --- 5. حفظ رد الذكاء الاصطناعي في قاعدة البيانات ---
        ai_message_db = Message(
            session_id=session_id,
            role='assistant',
            content=ai_message_content,
            model_used=selected_model # حفظ النموذج المستخدم لهذا الرد
            # timestamp يتم تعيينه تلقائيًا
        )
        db.session.add(ai_message_db)

        # --- 6. Commit التغييرات في قاعدة البيانات ---
        db.session.commit()
        logger.info(f"Session {session_id}: User and AI messages committed to DB.")

        # --- 7. إرجاع الرد إلى الواجهة الأمامية ---
        # أرسل الكائن الكامل للرسالة المحفوظة في قاعدة البيانات (أو أجزاء منه حسب حاجة الواجهة)
        return jsonify(ai_message_db.to_dict())

    # --- معالجة الأخطاء المتوقعة ---
    except requests.exceptions.Timeout as e:
        logger.error(f"Session {session_id}: Timeout error calling OpenRouter API: {e}", exc_info=True)
        db.session.rollback()
        # --- مكان جيد لمحاولة النموذج الاحتياطي (Gemini) ---
        return jsonify({"error": "انتهت مهلة الاستجابة من خدمة الذكاء الاصطناعي. حاول مرة أخرى."}), 504 # Gateway Timeout
    except requests.exceptions.HTTPError as e:
        logger.error(f"Session {session_id}: HTTP error calling OpenRouter API ({e.response.status_code}): {e.response.text}", exc_info=False) # لا تسجل exc_info لأنه خطأ HTTP متوقع
        db.session.rollback()
        error_details = "خطأ غير محدد من خدمة الذكاء الاصطناعي."
        try:
            # محاولة قراءة تفاصيل الخطأ من رد API إذا كان JSON
            error_json = e.response.json()
            error_details = error_json.get("error", {}).get("message", e.response.text)
        except json.JSONDecodeError:
             error_details = e.response.text[:200] # عرض جزء من النص إذا لم يكن JSON
        # --- مكان جيد لمحاولة النموذج الاحتياطي (Gemini) ---
        return jsonify({"error": f"فشل الاتصال بخدمة الذكاء الاصطناعي: {error_details}"}), e.response.status_code if e.response.status_code >= 500 else 502 # استخدم 502 للخطأ العام
    except requests.exceptions.RequestException as e:
        logger.error(f"Session {session_id}: Network error calling OpenRouter: {e}", exc_info=True)
        db.session.rollback()
        # --- مكان جيد لمحاولة النموذج الاحتياطي (Gemini) ---
        return jsonify({"error": "حدث خطأ في الشبكة أثناء الاتصال بخدمة الذكاء الاصطناعي."}), 503 # Service Unavailable
    except SQLAlchemyError as e:
         logger.error(f"Session {session_id}: Database error during chat handling: {e}", exc_info=True)
         db.session.rollback()
         return jsonify({"error": "حدث خطأ في قاعدة البيانات أثناء معالجة رسالتك."}), 500
    except Exception as e: # لأي أخطاء أخرى غير متوقعة
        logger.error(f"Session {session_id}: Unexpected error in handle_chat: {e}", exc_info=True)
        # محاولة التراجع احترازيًا
        try:
            db.session.rollback()
        except Exception as rollback_err:
            logger.error(f"Session {session_id}: Error during rollback after unexpected error: {rollback_err}", exc_info=True)
        return jsonify({"error": "حدث خطأ داخلي غير متوقع في الخادم."}), 500


@app.route('/api/regenerate', methods=['POST'])
@ensure_session
def handle_regenerate():
    """يعالج طلب إعادة إنشاء آخر رد للذكاء الاصطناعي."""
    session_id = session['session_id']
    logger.warning(f"Session {session_id}: Received request for /api/regenerate (Not fully implemented yet).")
    # --- المنطق المطلوب هنا ---
    # 1. جلب آخر رسالة للمستخدم وآخر رسالة للـ AI من السجل.
    # 2. التأكد من أن آخر رسالة كانت من الـ AI.
    # 3. حذف آخر رسالة للـ AI من قاعدة البيانات (أو وضع علامة عليها).
    # 4. جلب السياق مرة أخرى (الرسائل قبل رسالة المستخدم الأخيرة).
    # 5. استدعاء `handle_chat` مرة أخرى بنفس رسالة المستخدم ونفس النموذج (أو نموذج مختلف).
    # 6. معالجة الرد كما في `handle_chat`.
    # هذا يتطلب إعادة هيكلة بسيطة أو استدعاء منطق API بشكل منفصل.
    # حاليًا، سنعيد خطأ "غير منفذ".
    return jsonify({"error": "ميزة إعادة الإنشاء لم يتم تنفيذها بعد."}), 501


@app.route('/api/settings', methods=['POST'])
@ensure_session
def update_settings():
    """يحدّث إعدادات المستخدم المحددة في الجلسة."""
    session_id = session['session_id']
    data = request.get_json()
    if not data:
        logger.warning(f"Session {session_id}: Received empty request body for POST /api/settings")
        return jsonify({"error": "جسم الطلب غير صالح"}), 400

    logger.info(f"Updating settings for session {session_id}: {data}")
    updated_settings = {}
    if 'darkMode' in data and isinstance(data['darkMode'], bool):
        session['dark_mode'] = data['darkMode']
        updated_settings['darkMode'] = data['darkMode']
    if 'ttsEnabled' in data and isinstance(data['ttsEnabled'], bool):
        session['tts_enabled'] = data['ttsEnabled']
        updated_settings['ttsEnabled'] = data['ttsEnabled']

    if updated_settings:
        session.modified = True # التأكد من حفظ التغييرات في الجلسة
        logger.info(f"Session {session_id}: Settings updated: {updated_settings}")
        # إرجاع الإعدادات المحدثة كاملة
        current_settings = {
             'darkMode': session.get('dark_mode', False),
             'ttsEnabled': session.get('tts_enabled', True)
        }
        return jsonify({"success": True, "settings": current_settings})
    else:
        logger.info(f"Session {session_id}: No valid settings found in update request.")
        return jsonify({"error": "لم يتم تقديم إعدادات صالحة للتحديث."}), 400


@app.route('/api/history', methods=['DELETE'])
@ensure_session
def delete_history():
    """يحذف جميع رسائل الدردشة للجلسة الحالية."""
    session_id = session['session_id']
    logger.info(f"Attempting to delete history for session: {session_id}")
    try:
        # استخدام SQLAlchemy 2.0 style delete
        stmt = db.delete(Message).where(Message.session_id == session_id)
        result = db.session.execute(stmt)
        num_deleted = result.rowcount # عدد الصفوف المحذوفة
        db.session.commit()
        logger.info(f"Deleted {num_deleted} messages for session {session_id}")
        return jsonify({"success": True, "message": f"تم حذف {num_deleted} رسالة بنجاح."}), 200
    except SQLAlchemyError as e:
        db.session.rollback() # التراجع في حالة الخطأ
        logger.error(f"Database error deleting history for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "خطأ في قاعدة البيانات عند مسح سجل الدردشة."}), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error deleting history for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "حدث خطأ غير متوقع."}), 500


# --- معالجات الأخطاء العامة ---
@app.errorhandler(404)
def not_found_error(error):
    # إذا كان الطلب لواجهة برمجة التطبيقات، أرجع JSON
    if request.path.startswith('/api/'):
        logger.warning(f"404 Not Found for API route: {request.path} from {request.remote_addr}")
        return jsonify({"error": "نقطة النهاية غير موجودة."}), 404
    # وإلا، اعرض صفحة 404 HTML
    logger.warning(f"404 Not Found for page: {request.path} from {request.remote_addr}")
    # تأكد من وجود 'templates/404.html'
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    # تسجيل الخطأ الفعلي الذي سبب الـ 500
    # الخطأ الأصلي موجود في error.original_exception إذا كان خطأ HTTP تم التقاطه
    original_exception = getattr(error, 'original_exception', error)
    logger.error(f"500 Internal Server Error for {request.path} from {request.remote_addr}: {original_exception}", exc_info=True)

    # محاولة التراجع عن أي تعاملات قاعدة بيانات قد تكون عالقة
    try:
        db.session.rollback()
        logger.info("Database session rolled back after 500 error.")
    except Exception as e:
        logger.error(f"Error during rollback after 500 error: {e}", exc_info=True)

    if request.path.startswith('/api/'):
        return jsonify({"error": "حدث خطأ داخلي في الخادم."}), 500
    # تأكد من وجود 'templates/500.html'
    return render_template('500.html'), 500

@app.errorhandler(Exception) # معالج عام لأي استثناءات أخرى غير معالجة
def handle_exception(e):
     # هذا يلتقط أي استثناء لم يتم التقاطه بواسطة المعالجات المحددة أعلاه
     logger.error(f"Unhandled Exception for {request.path} from {request.remote_addr}: {e}", exc_info=True)
     try:
         db.session.rollback()
     except Exception as rollback_err:
         logger.error(f"Error during rollback after unhandled exception: {rollback_err}", exc_info=True)

     if request.path.startswith('/api/'):
        # لا تكشف تفاصيل الخطأ في الإنتاج
        error_message = "An unexpected error occurred." if is_production else str(e)
        return jsonify({"error": error_message}), 500
     # لا تظهر صفحة الخطأ 500 مباشرة من هنا إلا إذا كنت متأكدًا
     # من الأفضل ترك @app.errorhandler(500) يتعامل مع العرض
     # لكن تأكد من أن الخطأ يُسجل بشكل صحيح
     # يمكن إعادة إثارة الخطأ ليتم التقاطه بواسطة معالج 500، أو التعامل معه هنا مباشرة
     if isinstance(e, (json.JSONDecodeError, TypeError)): # مثال لخطأ محدد
         return jsonify({"error": f"Invalid request format: {e}"}), 400

     # Fallback to generic 500 response
     if request.path.startswith('/api/'):
        return jsonify({"error": "An unexpected internal error occurred."}), 500
     else:
         try:
             return render_template('500.html'), 500
         except Exception: # إذا فشل عرض القالب أيضًا
              return "Internal Server Error", 500


# --- تهيئة قاعدة البيانات عند بدء التشغيل ---
# هذا جيد للتطوير و Replit/Render، ولكن في الإنتاج قد تفضل استخدام أدوات الترحيل (Migrations) مثل Alembic
def initialize_database():
    with app.app_context():
        logger.info("Application context pushed. Checking database connection and tables...")
        if db_url: # محاولة فقط إذا تم تكوين عنوان URL لقاعدة البيانات
            try:
                # محاولة إنشاء الجداول إذا لم تكن موجودة
                # create_all() آمنة للتشغيل عدة مرات؛ لن تعيد إنشاء الجداول الموجودة.
                db.create_all()
                logger.info("Database tables ensured successfully.")
            except SQLAlchemyError as e:
                 logger.error(f"FATAL: Failed to connect to database or create tables. DB URL: {db_url[:db_url.find('@') + 1]}... Error: {e}", exc_info=False) # إخفاء بيانات الاعتماد
                 # قد ترغب في إيقاف التطبيق هنا إذا كانت قاعدة البيانات ضرورية
                 # raise SystemExit("Database connection failed.") from e
            except Exception as e:
                 logger.error(f"FATAL: An unexpected error occurred during DB initialization: {e}", exc_info=True)
                 # raise SystemExit("Unexpected database initialization error.") from e
        else:
            logger.warning("Database URL not configured. Database features (like history) will be unavailable.")

# استدعاء تهيئة قاعدة البيانات قبل بدء تشغيل الخادم
initialize_database()

# --- التنفيذ الرئيسي ---
if __name__ == '__main__':
    # استخدام متغير البيئة للمنفذ، الافتراضي هو 5000 أو 8080 الشائع في بعض المنصات
    port = int(os.environ.get("PORT", 5000))
    # وضع التصحيح يجب أن يكون False في الإنتاج! يتم تحميله من متغير البيئة FLASK_DEBUG.
    debug_mode = not is_production
    logger.info(f"Starting Flask app. Production mode: {is_production}, Debug mode: {debug_mode}")
    # استخدم host='0.0.0.0' ليكون متاحًا خارجيًا (مثل Replit/Docker/Render)
    # خادم التطوير (app.run) غير موصى به للإنتاج. استخدم Gunicorn أو Waitress.
    # مثال: gunicorn -w 4 -b 0.0.0.0:{port} main:app
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
else:
     # إذا تم استيراد الملف (كما يفعل Gunicorn)، تأكد من أن التسجيل يعمل بشكل جيد
     gunicorn_logger = logging.getLogger('gunicorn.error')
     app.logger.handlers = gunicorn_logger.handlers
     app.logger.setLevel(gunicorn_logger.level)
     logger.info("Application started via WSGI server (like Gunicorn). Logging configured.")

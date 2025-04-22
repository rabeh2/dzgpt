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
    app.secret_key = "default-insecure-secret-key-for-render" # Use this only if loading fails

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.error("FATAL: DATABASE_URL environment variable is not set.")
    # Fallback to SQLite for local dev if needed, but error out in production
    # default_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_chat.db')
    # DATABASE_URL = f'sqlite:///{default_db_path}'
    # logger.warning(f"Using default local SQLite database: {DATABASE_URL}")
    raise ValueError("DATABASE_URL environment variable is required.") # Fail fast if not set
else:
    # Render might provide 'postgres://' instead of 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

# إعدادات اتصال قاعدة البيانات الموصى بها للبيئات السحابية
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 280,  # Less than 5 min (common timeout)
        "pool_pre_ping": True, # Check connection before use
        "pool_timeout": 10,   # Wait time for connection from pool
    }
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# تهيئة SQLAlchemy مع التطبيق ونموذج Base
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# --- تحميل مفاتيح API ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not OPENROUTER_API_KEY: logger.warning("OPENROUTER_API_KEY not set. OpenRouter disabled.")
if not GEMINI_API_KEY: logger.warning("GEMINI_API_KEY not set. Gemini backup disabled.")


# إعدادات أخرى للتطبيق
APP_URL = os.environ.get("APP_URL") # Important for HTTP-Referer check by OpenRouter
if not APP_URL:
    logger.warning("APP_URL environment variable is not set. Using a default which might cause issues.")
    APP_URL = "http://localhost:5001" # Default for local dev, may not work correctly on Render

# --- Changed App Title ---
APP_TITLE = "dzteck Chat"

# --- تعريف نماذج قاعدة البيانات (مدمجة هنا) ---
# ... (Database models: Conversation, Message remain the same as original) ...
class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at", lazy="selectin")
    def add_message(self, role: str, content: str): # Simplified add_message
        new_message = Message(conversation_id=self.id, role=role, content=content)
        db.session.add(new_message)
        return new_message
    def to_dict(self): return {"id": str(self.id), "title": self.title, "created_at": self.created_at.isoformat(), "updated_at": self.updated_at.isoformat(), "messages": [m.to_dict() for m in self.messages]}
    def __repr__(self): return f"<Conversation(id={self.id}, title='{self.title}')>"

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False) # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    def to_dict(self): return {"id": self.id, "conversation_id": str(self.conversation_id), "role": self.role, "content": self.content, "created_at": self.created_at.isoformat()}
    def __repr__(self): return f"<Message(id={self.id}, role='{self.role}', conv_id={self.conversation_id})>"


# --- الردود الاحتياطية (للاستخدام عند فشل كل الـ APIs) ---
# Updated offline responses to use "dzteck"
offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا مساعد dzteck الرقمي. للأسف، لا يوجد اتصال بالإنترنت حاليًا.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا مساعد dzteck الرقمي. أعتذر، خدمة الإنترنت غير متوفرة حاليًا.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت."
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت أو بخدمات الذكاء الاصطناعي."

# --- دالة استدعاء Gemini API (النموذج الاحتياطي) ---
# ... (call_gemini_api function remains the same as original) ...
def call_gemini_api(messages_list, temperature, max_tokens=512):
    """Call the Gemini API as a backup"""
    if not GEMINI_API_KEY: return None, "مفتاح Gemini API غير متوفر"
    try:
        gemini_contents = [{"role": ("user" if msg["role"] == "user" else "model"), "parts": [{"text": msg["content"]}]} for msg in messages_list]
        if gemini_contents and gemini_contents[-1]['role'] != 'user': logger.warning("Gemini API call adjusted: Last message was not from user.")
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
        logger.debug(f"Calling Gemini API ({gemini_url.split('?')[0]}) with {len(gemini_contents)} parts...")
        response = requests.post(url=gemini_url, headers={'Content-Type': 'application/json'}, json={"contents": gemini_contents, "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}}, timeout=35)
        response.raise_for_status()
        response_data = response.json()
        if 'candidates' not in response_data or not response_data['candidates']:
            block_reason = response_data.get('promptFeedback', {}).get('blockReason', 'Unknown'); logger.error(f"Gemini response blocked/missing: {block_reason}"); return None, f"الرد محظور: {block_reason}"
        text_parts = [part['text'] for part in response_data['candidates'][0]['content']['parts'] if 'text' in part]
        if text_parts: return "".join(text_parts).strip(), None
        else: logger.warning(f"No text in Gemini response: {response_data}"); return None, "لم يتم العثور على نص في استجابة Gemini"
    except requests.exceptions.Timeout: logger.error("Gemini timeout."); return None, "مهلة Gemini"
    except requests.exceptions.HTTPError as e:
        try: error_details = e.response.json().get("error", {}).get("message", e.response.text)
        except json.JSONDecodeError: error_details = e.response.text[:200]
        logger.error(f"Gemini HTTP error ({e.response.status_code}): {error_details}"); return None, f"خطأ HTTP Gemini: {error_details}"
    except requests.exceptions.RequestException as e: logger.error(f"Gemini connection error: {e}"); return None, f"خطأ اتصال Gemini: {e}"
    except Exception as e: logger.error(f"Gemini processing error: {e}", exc_info=True); return None, f"خطأ معالجة Gemini: {e}"

# --- مسارات Flask (Routes) ---

@app.route('/')
def index():
    """Route for the main chat page."""
    logger.info(f"Serving main page (index.html) requested by {request.remote_addr}")
    # Pass the updated application title to the template
    return render_template('index.html', app_title=APP_TITLE)

@app.route('/api/chat', methods=['POST'])
def chat():
    """API route for handling chat messages."""
    # ... (Logic remains the same as original, but APP_TITLE is now 'dzteck Chat') ...
    # Key parts:
    # - Get data from request
    # - Find/Create Conversation
    # - Add user message to DB
    # - Call OpenRouter (using updated APP_TITLE in headers)
    # - Call Gemini if OpenRouter fails
    # - Use offline_responses if both fail
    # - Add AI reply to DB
    # - Commit and return response
    start_time = datetime.now(timezone.utc)
    try:
        data = request.json
        if not data: return jsonify({"error": "الطلب فارغ"}), 400

        messages_for_api = data.get('history', [])
        if not messages_for_api or messages_for_api[-1].get('role') != 'user': return jsonify({"error": "سجل غير صالح"}), 400
        user_message = messages_for_api[-1]['content'].strip()
        if not user_message: return jsonify({"error": "رسالة فارغة"}), 400

        model = data.get('model', 'mistralai/mistral-7b-instruct')
        conversation_id_str = data.get('conversation_id')
        temperature = float(data.get('temperature', 0.7))
        max_tokens = int(data.get('max_tokens', 1024))

        db_conversation, conversation_id = None, None
        if conversation_id_str:
            try: conversation_id = uuid.UUID(conversation_id_str); stmt = select(Conversation).filter_by(id=conversation_id); db_conversation = db.session.execute(stmt).scalar_one_or_none()
            except ValueError: conversation_id = None
            if not db_conversation: logger.warning(f"Conv ID {conversation_id_str} not found."); conversation_id = None

        if not db_conversation:
            conversation_id = uuid.uuid4(); initial_title = user_message.split('\n')[0][:80]
            logger.info(f"Creating new conv: {conversation_id}, title: '{initial_title}'")
            db_conversation = Conversation(id=conversation_id, title=initial_title or "محادثة جديدة"); db.session.add(db_conversation)

        user_msg_db = db_conversation.add_message('user', user_message)

        ai_reply, error_message, used_backup, api_source = None, None, False, "N/A"

        if OPENROUTER_API_KEY:
            api_source = "OpenRouter"
            try:
                 logger.debug(f"Calling OpenRouter: model={model}")
                 headers = { "Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": APP_URL, "X-Title": APP_TITLE } # Use updated APP_TITLE
                 payload = { "model": model, "messages": messages_for_api, "temperature": temperature, "max_tokens": max_tokens }
                 response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=45)
                 response.raise_for_status()
                 api_response = response.json()
                 if api_response.get('choices') and api_response['choices'][0].get('message'):
                     ai_reply = api_response['choices'][0]['message'].get('content', '').strip()
                     if ai_reply: logger.info("Reply from OpenRouter.")
                     else: logger.warning("OpenRouter empty content.")
                 else: logger.error(f"OpenRouter invalid response: {api_response}"); error_message = "رد OpenRouter غير صالح"
            except Exception as e: # Simplified error handling for brevity
                 logger.error(f"OpenRouter Error: {e}"); error_message = f"خطأ OpenRouter: {e}"

        if not ai_reply and GEMINI_API_KEY:
             api_source = "Gemini (Backup)"
             logger.info("Trying Gemini backup...")
             ai_reply, backup_error = call_gemini_api(messages_for_api, temperature, max_tokens)
             if ai_reply: used_backup = True; error_message = None; logger.info("Reply from Gemini backup.")
             else: logger.error(f"Gemini backup failed: {backup_error}"); error_message = error_message or f"فشل Gemini: {backup_error}"

        if not ai_reply:
            api_source = "Offline Fallback"
            logger.warning("Using offline fallback.")
            ai_reply = offline_responses.get(user_message.lower(), default_offline_response)

        if ai_reply:
             assistant_msg_db = db_conversation.add_message('assistant', ai_reply)
             try:
                 db.session.commit(); elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                 logger.info(f"Chat request processed in {elapsed:.2f}s.")
                 return jsonify({"id": str(db_conversation.id), "content": ai_reply, "used_backup": used_backup})
             except SQLAlchemyError as e: logger.error(f"DB commit error: {e}", exc_info=True); db.session.rollback(); return jsonify({"error": f"خطأ DB: {e}"}), 500
        else: logger.error("Failed to generate response."); db.session.rollback(); return jsonify({"error": error_message or "فشل توليد رد"}), 500
    except Exception as e: logger.error(f"Critical /api/chat error: {e}", exc_info=True); db.session.rollback(); return jsonify({"error": f"خطأ خادم داخلي: {e}"}), 500


# --- Conversation Management Endpoints ---
# ... (GET /api/conversations, GET /api/conversations/<uuid>, DELETE /api/conversations/<uuid>, PUT /api/conversations/<uuid>/title, POST /api/regenerate remain the same as original, but APP_TITLE in regenerate headers will be updated) ...

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """API route to get a list of all conversations (simplified)."""
    try:
        stmt = select(Conversation.id, Conversation.title, Conversation.updated_at).order_by(desc(Conversation.updated_at))
        results = db.session.execute(stmt).all()
        conversations_list = [{"id": str(row.id), "title": row.title, "updated_at": row.updated_at.isoformat()} for row in results]
        return jsonify(conversations_list)
    except Exception as e:
        logger.error(f"Error getting conversations list: {e}", exc_info=True)
        return jsonify({"error": "فشل استرجاع المحادثات"}), 500

@app.route('/api/conversations/<uuid:conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    """API route to get a specific conversation with all its messages."""
    try:
        stmt = select(Conversation).filter_by(id=conversation_id) # lazy='selectin' loads messages
        conversation = db.session.execute(stmt).scalar_one_or_none()
        if not conversation: return jsonify({"error": "المحادثة غير موجودة"}), 404
        return jsonify(conversation.to_dict())
    except Exception as e:
        logger.error(f"Error getting conversation {conversation_id}: {e}", exc_info=True)
        return jsonify({"error": "فشل استرجاع المحادثة"}), 500

@app.route('/api/conversations/<uuid:conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    """API route to delete a specific conversation."""
    try:
        stmt = select(Conversation).filter_by(id=conversation_id)
        conversation = db.session.execute(stmt).scalar_one_or_none()
        if not conversation: return jsonify({"error": "المحادثة غير موجودة"}), 404
        db.session.delete(conversation)
        db.session.commit()
        return jsonify({"success": True, "message": "تم الحذف بنجاح"})
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {e}", exc_info=True); db.session.rollback()
        return jsonify({"error": "فشل حذف المحادثة"}), 500

@app.route('/api/conversations/<uuid:conversation_id>/title', methods=['PUT'])
def update_conversation_title(conversation_id):
    """API route to update the title of a specific conversation."""
    try:
        data = request.json; new_title = data.get('title', '').strip()
        if not new_title or len(new_title) > 100: return jsonify({"error": "العنوان غير صالح"}), 400
        stmt = update(Conversation).where(Conversation.id == conversation_id).values(title=new_title, updated_at=datetime.now(timezone.utc))
        result = db.session.execute(stmt)
        if result.rowcount == 0:
            exists_stmt = select(Conversation.id).filter_by(id=conversation_id)
            if not db.session.execute(exists_stmt).scalar_one_or_none(): return jsonify({"error": "المحادثة غير موجودة"}), 404
        db.session.commit()
        return jsonify({"success": True, "message": "تم تحديث العنوان"})
    except Exception as e:
        logger.error(f"Error updating title for {conversation_id}: {e}", exc_info=True); db.session.rollback()
        return jsonify({"error": "فشل تحديث العنوان"}), 500

@app.route('/api/regenerate', methods=['POST'])
def regenerate_response():
    """API route for regenerating the last AI response."""
    # ... (Same logic as original, but X-Title header will use updated APP_TITLE) ...
    start_time = datetime.now(timezone.utc)
    try:
        data = request.json
        if not data: return jsonify({"error": "طلب غير صالح"}), 400

        conversation_id_str = data.get('conversation_id')
        model = data.get('model', 'mistralai/mistral-7b-instruct')
        temperature = float(data.get('temperature', 0.7))
        max_tokens = int(data.get('max_tokens', 1024))

        if not conversation_id_str: return jsonify({"error": "معرف المحادثة مطلوب"}), 400
        try: conversation_id = uuid.UUID(conversation_id_str)
        except ValueError: return jsonify({"error": "تنسيق المعرف غير صالح"}), 400

        logger.info(f"Regenerate request for conv: {conversation_id}")

        stmt = select(Conversation).filter_by(id=conversation_id)
        conversation = db.session.execute(stmt).scalar_one_or_none()
        if not conversation: return jsonify({"error": "المحادثة غير موجودة"}), 404
        messages_db = conversation.messages
        if not messages_db: return jsonify({"error": "لا توجد رسائل"}), 400

        last_ai_message_index = -1
        for i in range(len(messages_db) - 1, -1, -1):
            if messages_db[i].role == 'assistant': last_ai_message_index = i; break
        if last_ai_message_index == -1: return jsonify({"error": "لا يوجد رد سابق للمساعد"}), 400

        last_ai_message = messages_db[last_ai_message_index]
        messages_for_api = [msg.to_dict() for msg in messages_db[:last_ai_message_index]]
        if not messages_for_api or messages_for_api[-1].get('role') != 'user': return jsonify({"error": "سجل غير كافٍ لإعادة التوليد"}), 400

        db.session.delete(last_ai_message) # Stage deletion

        ai_reply, error_message, used_backup, api_source = None, None, False, "N/A"

        if OPENROUTER_API_KEY:
             api_source = "OpenRouter (Regen)"
             try:
                 headers = { "Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": APP_URL, "X-Title": APP_TITLE } # Use updated APP_TITLE
                 payload = { "model": model, "messages": messages_for_api, "temperature": temperature, "max_tokens": max_tokens }
                 response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=45)
                 response.raise_for_status()
                 api_response = response.json()
                 if api_response.get('choices') and api_response['choices'][0].get('message'): ai_reply = api_response['choices'][0]['message'].get('content', '').strip()
                 else: error_message = "رد OpenRouter غير صالح"; logger.error(f"Regen Invalid OpenRouter Resp: {api_response}")
             except Exception as e: logger.error(f"Regen OpenRouter Error: {e}"); error_message = f"خطأ Regen OpenRouter: {e}"

        if not ai_reply and GEMINI_API_KEY:
            api_source = "Gemini (Backup Regen)"
            logger.info("Regen trying Gemini backup...")
            gemini_history = [{"role": m["role"], "content": m["content"]} for m in messages_for_api]
            ai_reply, backup_error = call_gemini_api(gemini_history, temperature, max_tokens)
            if ai_reply: used_backup = True; error_message = None
            else: error_message = error_message or f"فشل Regen Gemini: {backup_error}"; logger.error(f"Regen Gemini failed: {backup_error}")

        if not ai_reply: # Regenerate failed
            db.session.rollback(); # Rollback deletion
            return jsonify({"error": error_message or "فشل إعادة التوليد"}), 500

        new_assistant_msg = conversation.add_message('assistant', ai_reply)
        try:
            db.session.commit(); elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"Regen processed in {elapsed:.2f}s.")
            return jsonify({"content": ai_reply, "used_backup": used_backup})
        except SQLAlchemyError as e: logger.error(f"Regen DB commit error: {e}", exc_info=True); db.session.rollback(); return jsonify({"error": f"خطأ DB Regen: {e}"}), 500

    except Exception as e: logger.error(f"Critical /api/regenerate error: {e}", exc_info=True); db.session.rollback(); return jsonify({"error": f"خطأ خادم داخلي Regen: {e}"}), 500


# --- معالجات الأخطاء العامة ---
# ... (Error handlers 404, 500, Exception remain the same as original) ...
@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'): return jsonify({"error": "نقطة النهاية غير موجودة."}), 404
    return "<h1>404 Not Found</h1><p>الصفحة المطلوبة غير موجودة.</p>", 404

@app.errorhandler(500)
def internal_error(error):
    original_exception = getattr(error, 'original_exception', error)
    logger.error(f"500 Error: {request.path}: {original_exception}", exc_info=True)
    try: db.session.rollback()
    except Exception as e: logger.error(f"Rollback failed after 500: {e}")
    if request.path.startswith('/api/'): return jsonify({"error": "حدث خطأ داخلي في الخادم."}), 500
    return "<h1>500 Internal Server Error</h1><p>حدث خطأ غير متوقع.</p>", 500

@app.errorhandler(Exception)
def handle_exception(e):
     logger.error(f"Unhandled Exception: {request.path}: {e}", exc_info=True)
     try: db.session.rollback()
     except Exception as rb_err: logger.error(f"Rollback failed after unhandled exception: {rb_err}")
     status_code = 500; error_message = "حدث خطأ غير متوقع."
     if isinstance(e, requests.exceptions.HTTPError): status_code = e.response.status_code if e.response else 500; error_message = f"خطأ اتصال خارجي: {e}"
     elif isinstance(e, SQLAlchemyError): error_message = "حدث خطأ في قاعدة البيانات."
     if request.path.startswith('/api/'): return jsonify({"error": error_message}), status_code
     return f"<h1>Error {status_code}</h1><p>{error_message}</p>", status_code


# --- إنشاء جداول قاعدة البيانات عند بدء التشغيل ---
# ... (initialize_database function remains the same as original) ...
def initialize_database():
    with app.app_context():
        logger.info("Initializing database...")
        try:
            db.create_all()
            logger.info("Database tables checked/created.")
        except Exception as e:
            db_uri_safe = str(app.config.get("SQLALCHEMY_DATABASE_URI")).split('@')[-1]
            logger.error(f"FATAL: DB init error for '{db_uri_safe}': {e}", exc_info=False)
            raise SystemExit(f"Database initialization failed: {e}") from e
initialize_database()
logger.info("DB initialization routine finished.")

# --- نقطة الدخول لـ Gunicorn/WSGI Server (لا حاجة لـ app.run في الإنتاج) ---
# ... (WSGI entry point remains the same as original) ...
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)
    logger.info(f"'{APP_TITLE}' starting via WSGI server.")
else:
     # Run locally for testing
     logger.info(f"Starting Flask development server for '{APP_TITLE}'...")
     port = int(os.environ.get("PORT", 5001))
     # Set debug=False for production simulation, or True for local dev features
     use_debug = os.environ.get("FLASK_DEBUG", "0") == "1"
     app.run(host='0.0.0.0', port=port, debug=use_debug)

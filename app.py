import os
import logging
import requests
import json
import uuid
import re
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, DateTime, ForeignKey, select, delete, update, desc, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import SQLAlchemyError

log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

app = Flask(__name__)

app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    logger.warning("SESSION_SECRET environment variable not set. Using a default insecure key.")
    app.secret_key = "default-insecure-secret-key-for-render"

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.error("FATAL: DATABASE_URL environment variable is not set.")
    # Consider adding a more robust check/exit here in production
    # import sys
    # sys.exit("DATABASE_URL environment variable not set.")
else:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,
    "pool_pre_ping": True,
    "pool_timeout": 10,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(model_class=Base)
db.init_app(app)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY environment variable is not set. OpenRouter functionality will be disabled.")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY environment variable is not set. Gemini backup functionality may be limited.")

APP_URL = os.environ.get("APP_URL", "http://localhost:5000")
APP_TITLE = "Yasmin GPT Chat"

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="selectin"
    )
    def add_message(self, role: str, content: str):
        new_message = Message(
            conversation_id=self.id,
            role=role,
            content=content,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(new_message)
        return new_message
    def to_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [message.to_dict() for message in self.messages]
        }
    def __repr__(self):
        return f"<Conversation(id={self.id}, title='{self.title}')>"

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    votes: Mapped[list["MessageVote"]] = relationship(
        "MessageVote",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="noload"
    )
    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": str(self.conversation_id),
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat()
        }
    def __repr__(self):
        return f"<Message(id={self.id}, role='{self.role}', conv_id={self.conversation_id})>"

class MessageVote(Base):
    __tablename__ = "message_votes"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    vote_type: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    message: Mapped["Message"] = relationship("Message", back_populates="votes")
    conversation: Mapped["Conversation"] = relationship("Conversation")
    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "conversation_id": str(self.conversation_id),
            "vote_type": self.vote_type,
            "created_at": self.created_at.isoformat()
        }
    def __repr__(self):
        return f"<MessageVote(id={self.id}, message_id={self.message_id}, vote_type='{self.vote_type}')>"

offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا ياسمين. للأسف، لا يوجد اتصال بالإنترنت حاليًا.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا ياسمين. أعتذر، خدمة الإنترنت غير متوفرة حاليًا.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت.",
    "ما هي قدراتك": "لا يمكنني الوصول إلى الإنترنت حاليًا، لذا لا يمكنني عرض قدراتي الكاملة.",
    "ما هو الذكاء الاصطناعي": "في وضع عدم الاتصال، لا يمكنني تقديم تعريف كامل للذكاء الاصطناعي. يرجى التحقق من اتصالك بالإنترنت.",
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت أو بخدمات الذكاء الاصطناعي."

def call_gemini_api(messages_list, temperature, max_tokens=1024):
    if not GEMINI_API_KEY:
        logger.warning("Gemini API key not available for backup.")
        return None, "مفتاح Gemini API غير متوفر"
    try:
        gemini_contents = []
        last_role = None
        for msg in messages_list:
            role = "user" if msg["role"] == "user" else "model"
            if role != last_role:
                gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})
                last_role = role
            else:
                 logger.warning(f"Gemini API call: Skipping consecutive message with same role ({role}). Content: {msg['content'][:50]}...")

        if gemini_contents and gemini_contents[-1]['role'] == 'model':
             logger.warning("Gemini API call: Last message in constructed history is from model. Appending empty user turn.")
             gemini_contents.append({"role": "user", "parts": [{"text": ""}]})
        elif not gemini_contents and messages_list:
             logger.error(f"Gemini API call: Constructed history is empty, but original was not. Original size: {len(messages_list)}")
             return None, "فشل في إعداد سجل المحادثة للنموذج الاحتياطي"
        elif not gemini_contents and not messages_list:
             logger.warning("Gemini API call: History is empty. Cannot call API.")
             return None, "سجل المحادثة فارغ أو غير صالح للنموذج الاحتياطي"

        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
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
            timeout=40
        )
        response.raise_for_status()
        response_data = response.json()

        if 'candidates' not in response_data or not response_data['candidates']:
            block_reason = response_data.get('promptFeedback', {}).get('blockReason', 'Unknown reason')
            safety_ratings = response_data.get('promptFeedback', {}).get('safetyRatings', [])
            logger.error(f"Gemini response missing candidates or blocked. Reason: {block_reason}. Ratings: {safety_ratings}")
            if 'candidates' in response_data and len(response_data['candidates']) > 0 and 'finishReason' in response_data['candidates'][0]:
                 finish_reason = response_data['candidates'][0]['finishReason']
                 error_text = f"تم إنهاء الرد بسبب: {finish_reason}"
            else:
                 error_text = f"الرد محظور بواسطة فلتر السلامة: {block_reason}"
            return None, error_text

        text_parts = []
        try:
            if 'parts' in response_data['candidates'][0].get('content', {}):
                for part in response_data['candidates'][0]['content']['parts']:
                    if 'text' in part:
                        text_parts.append(part['text'])
                    else:
                        logger.warning(f"Gemini response part missing 'text' key: {part}")
            else:
                 logger.warning(f"Gemini response candidate content missing 'parts' key. Response: {response_data}")
        except (KeyError, IndexError, TypeError) as e:
             logger.error(f"Error parsing Gemini response content structure: {e}. Response: {response_data}")
             return None, "خطأ في تحليل استجابة النموذج الاحتياطي"

        if text_parts:
            return "".join(text_parts).strip(), None
        else:
            logger.warning(f"No text found in Gemini response parts. Response: {response_data}")
            finish_reason = response_data['candidates'][0].get('finishReason', 'No text content') if response_data.get('candidates') else 'No candidates'
            return None, f"لم يتم العثور على نص في الاستجابة. السبب: {finish_reason}"
    except requests.exceptions.Timeout:
        logger.error("Gemini API request timed out.")
        return None, "استجابة النموذج الاحتياطي (Gemini) استغرقت وقتاً طويلاً"
    except requests.exceptions.HTTPError as e:
         error_body = e.response.text
         logger.error(f"Gemini API HTTP error ({e.response.status_code}): {error_body}")
         try: error_json = e.response.json(); error_details = error_json.get("error", {}).get("message", error_body)
         except json.JSONDecodeError: error_details = error_body[:200]
         return None, f"خطأ HTTP من النموذج الاحتياطي: {error_details}"
    except requests.exceptions.RequestException as e: logger.error(f"Error calling Gemini API: {e}", exc_info=True); return None, f"خطأ في الاتصال بالنموذج الاحتياطي (Gemini): {e}"
    except Exception as e: logger.error(f"Unexpected error processing Gemini response: {e}", exc_info=True); return None, f"خطأ غير متوقع في معالجة استجابة النموذج الاحتياطي: {e}"

@app.route('/')
def index():
    return render_template('index.html', app_title=APP_TITLE)

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        if not data:
            logger.warning("Received empty JSON payload for /api/chat")
            return jsonify({"error": "الطلب غير صالح (بيانات فارغة)"}), 400

        messages_for_api = data.get('history', [])
        if not isinstance(messages_for_api, list) or not messages_for_api:
             logger.warning(f"Invalid or empty 'history' received in /api/chat: {messages_for_api}")
             return jsonify({"error": "تنسيق سجل المحادثة غير صالح"}), 400

        if messages_for_api[-1].get('role') != 'user':
             logger.warning(f"Last message in history is not from user: {messages_for_api[-1]}")
             return jsonify({"error": "آخر رسالة في السجل يجب أن تكون للمستخدم"}), 400

        user_message_content = messages_for_api[-1].get('content', '').strip()
        if not user_message_content:
             logger.warning("Received empty user message content in /api/chat history.")
             return jsonify({"error": "محتوى الرسالة فارغ"}), 400

        model = data.get('model', 'mistralai/mistral-7b-instruct-v0.2')
        conversation_id_str = data.get('conversation_id')
        temperature = float(data.get('temperature', 0.7))
        max_tokens = int(data.get('max_tokens', 1024))

        db_conversation = None
        conversation_id = None

        if conversation_id_str:
            try:
                conversation_id = uuid.UUID(conversation_id_str)
                stmt = select(Conversation).filter_by(id=conversation_id)
                db_conversation = db.session.execute(stmt).scalar_one_or_none()
                if db_conversation:
                    logger.debug(f"Found existing conversation: {conversation_id}")
                else:
                     logger.warning(f"Conversation ID '{conversation_id_str}' provided but not found in DB. Treating as new conversation.")
                     conversation_id = None
            except ValueError:
                logger.warning(f"Invalid UUID format received for conversation_id: {conversation_id_str}. Treating as new conversation.")
                conversation_id = None

        if not db_conversation:
            conversation_id = uuid.uuid4()
            initial_title = user_message_content.split('\n')[0][:80]
            logger.info(f"Creating new conversation with ID: {conversation_id}, initial title: '{initial_title or 'محادثة جديدة'}'")
            db_conversation = Conversation(id=conversation_id, title=initial_title or "محادثة جديدة")
            db.session.add(db_conversation)

        user_msg_db = Message(
             conversation_id=db_conversation.id,
             role='user',
             content=user_message_content,
             created_at=datetime.now(timezone.utc)
        )
        db.session.add(user_msg_db)
        db.session.flush()

        api_history = messages_for_api

        ai_reply_content = None
        error_message = None
        used_backup = False
        api_source = "N/A"

        if OPENROUTER_API_KEY:
            api_source = "OpenRouter"
            try:
                logger.debug(f"Calling OpenRouter with model: {model}, history size: {len(api_history)}")
                openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
                headers = { "Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": APP_URL, "X-Title": APP_TITLE, }
                payload = { "model": model, "messages": api_history, "temperature": temperature, "max_tokens": max_tokens, }
                response = requests.post(url=openrouter_url, headers=headers, json=payload, timeout=60)
                response.raise_for_status()
                api_response = response.json()
                if api_response.get('choices') and api_response['choices'][0].get('message'):
                    ai_reply_content = api_response['choices'][0]['message'].get('content', '').strip()
                    if not ai_reply_content: logger.warning(f"OpenRouter returned empty content for model {model}. Response: {api_response}")
                    else: logger.info(f"Received reply from OpenRouter ({model}).")
                    if 'usage' in api_response: logger.info(f"OpenRouter usage: {api_response['usage']}")
                else: logger.error(f"OpenRouter response structure invalid: {api_response}"); error_message = "استجابة غير متوقعة من OpenRouter"
            except requests.exceptions.Timeout: logger.error("OpenRouter API request timed out."); error_message = "استجابة OpenRouter استغرقت وقتاً طويلاً"
            except requests.exceptions.HTTPError as e:
                error_body = e.response.text; logger.error(f"OpenRouter API HTTP error ({e.response.status_code}): {error_body}")
                try: error_json = e.response.json(); error_details = error_json.get("error", {}).get("message", error_body)
                except json.JSONDecodeError: error_details = error_body[:200]
                error_message = f"خطأ HTTP من OpenRouter: {error_details}"
            except requests.exceptions.RequestException as e: logger.error(f"Error calling OpenRouter API: {e}", exc_info=True); error_message = f"خطأ في الاتصال بـ OpenRouter: {e}"
            except Exception as e: logger.error(f"Unexpected error processing OpenRouter response: {e}", exc_info=True); error_message = f"خطأ غير متوقع في معالجة استجابة OpenRouter: {e}"

        if not ai_reply_content and GEMINI_API_KEY:
            api_source = "Gemini (Backup)"; logger.info("OpenRouter failed. Trying Gemini backup...");
            ai_reply_content, backup_error = call_gemini_api(api_history, temperature, max_tokens)
            if ai_reply_content: used_backup = True; error_message = None; logger.info("Received reply from Gemini (backup).")
            else: logger.error(f"Gemini backup also failed: {backup_error}"); error_message = error_message or f"فشل النموذج الاحتياطي (Gemini): {backup_error}"

        if not ai_reply_content:
            api_source = "Offline Fallback"; logger.warning("Both API calls failed. Falling back to predefined offline responses.");
            matched_offline = False
            user_msg_lower = user_message.lower()
            for key, response_text in offline_responses.items():
                if key.lower() in user_msg_lower:
                    ai_reply = response_text; matched_offline = True; logger.info(f"Matched offline response for key: '{key}'")
                    break
            if not matched_offline: ai_reply = default_offline_response; logger.info("Using default offline response.")

        if ai_reply:
            logger.debug(f"Adding assistant reply (from {api_source}) to DB for conversation {db_conversation.id}")
            assistant_msg_db = Message( conversation_id=db_conversation.id, role='assistant', content=ai_reply, created_at=datetime.now(timezone.utc) )
            db.session.add(assistant_msg_db)
            try:
                db.session.commit(); logger.info(f"Successfully committed messages for conversation {db_conversation.id}")
                return jsonify({
                    "id": str(db_conversation.id), "content": ai_reply,
                    "user_message_id": user_msg_db.id, "assistant_message_id": assistant_msg_db.id,
                    "used_backup": used_backup, "new_conversation_id": str(conversation_id) if data.get('conversation_id') is None else None
                })
            except SQLAlchemyError as e:
                 logger.error(f"Database commit error after getting AI reply: {e}", exc_info=True); db.session.rollback()
                 return jsonify({
                     "content": ai_reply, "user_message_id": user_msg_db.id, "assistant_message_id": None,
                     "used_backup": used_backup, "new_conversation_id": None,
                     "error": f"تم توليد الرد ولكن حدث خطأ أثناء حفظه في قاعدة البيانات: {e}"
                     }), 500
        else:
            logger.error("Failed to generate any response (AI or offline)."); db.session.rollback()
            return jsonify({"error": error_message or "فشل توليد استجابة"}), 500
    except Exception as e:
        logger.error(f"Critical error in /api/chat endpoint: {e}", exc_info=True)
        # Corrected try...except block
        try:
            db.session.rollback()
            logger.info("Database session rolled back after critical chat error.")
        except Exception as rollback_err:
             logger.error(f"Error during rollback after critical chat error: {rollback_err}", exc_info=True)
        return jsonify({"error": f"حدث خطأ داخلي خطير في الخادم: {e}"}), 500


@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    try:
        stmt = select(Conversation.id, Conversation.title, Conversation.updated_at).order_by(desc(Conversation.updated_at))
        conversations = db.session.execute(stmt).all()
        conversations_list = [ { "id": str(conv.id), "title": conv.title, "updated_at": conv.updated_at.isoformat() } for conv in conversations ]
        return jsonify(conversations_list)
    except SQLAlchemyError as e: logger.error(f"Database error getting conversations list: {e}", exc_info=True); return jsonify({"error": f"خطأ في استرجاع قائمة المحادثات من قاعدة البيانات: {e}"}), 500
    except Exception as e: logger.error(f"Unexpected error getting conversations list: {e}", exc_info=True); return jsonify({"error": f"خطأ غير متوقع في استرجاع المحادثات: {e}"}), 500

@app.route('/api/conversations/<uuid:conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    try:
        logger.info(f"Fetching conversation details for ID: {conversation_id}")
        stmt = select(Conversation).filter_by(id=conversation_id).options(relationship(Conversation.messages)); conversation = db.session.execute(stmt).scalar_one_or_none()
        if not conversation: logger.warning(f"Conversation not found for ID: {conversation_id}"); return jsonify({"error": "المحادثة المطلوبة غير موجودة"}), 404
        logger.info(f"Conversation found: '{conversation.title}', returning details."); return jsonify(conversation.to_dict())
    except SQLAlchemyError as e: logger.error(f"Database error getting conversation {conversation_id}: {e}", exc_info=True); return jsonify({"error": f"خطأ قاعدة بيانات عند استرجاع تفاصيل المحادثة: {e}"}), 500
    except Exception as e: logger.error(f"Unexpected error getting conversation {conversation_id}: {e}", exc_info=True); return jsonify({"error": f"خطأ غير متوقع في استرجاع المحادثة: {e}"}), 500

@app.route('/api/conversations/<uuid:conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    try:
        logger.info(f"Attempting to delete conversation with ID: {conversation_id}")
        stmt = select(Conversation).filter_by(id=conversation_id); conversation = db.session.execute(stmt).scalar_one_or_none()
        if not conversation: logger.warning(f"Attempted to delete non-existent conversation: {conversation_id}"); return jsonify({"error": "المحادثة المطلوب حذفها غير موجودة"}), 404
        db.session.delete(conversation); db.session.commit(); logger.info(f"Successfully deleted conversation: {conversation_id}"); return jsonify({"success": True, "message": "تم حذف المحادثة وجميع رسائلها بنجاح"})
    except SQLAlchemyError as e: logger.error(f"Database error deleting conversation {conversation_id}: {e}", exc_info=True); db.session.rollback(); return jsonify({"error": f"خطأ قاعدة بيانات أثناء حذف المحادثة: {e}"}), 500
    except Exception as e: logger.error(f"Unexpected error deleting conversation {conversation_id}: {e}", exc_info=True); db.session.rollback(); return jsonify({"error": f"خطأ غير متوقع أثناء حذف المحادثة: {e}"}), 500

@app.route('/api/conversations/<uuid:conversation_id>/title', methods=['PUT'])
def update_conversation_title(conversation_id):
    try:
        data = request.json; new_title = data.get('title', '').strip()
        if not new_title or len(new_title) > 100: logger.warning(f"Invalid title received for conversation {conversation_id}: '{new_title}'"); return jsonify({"error": "عنوان المحادثة مطلوب ويجب ألا يتجاوز 100 حرف"}), 400
        logger.info(f"Attempting to update title for conversation {conversation_id} to '{new_title}'")
        stmt = update(Conversation).where(Conversation.id == conversation_id).values(title=new_title, updated_at=datetime.now(timezone.utc)).returning(Conversation.id)
        result = db.session.execute(stmt); updated_id = result.scalar_one_or_none()
        if updated_id: db.session.commit(); logger.info(f"Successfully updated title for conversation: {conversation_id}"); return jsonify({"success": True, "message": "تم تحديث عنوان المحادثة بنجاح"})
        else:
            exists_stmt = select(Conversation.id).filter_by(id=conversation_id); exists = db.session.execute(exists_stmt).scalar_one_or_none()
            if not exists: logger.warning(f"Attempted to update title for non-existent conversation: {conversation_id}"); return jsonify({"error": "المحادثة المطلوب تحديثها غير موجودة"}), 404
            else: logger.error(f"Failed to update title for conversation {conversation_id}, but it exists."); db.session.rollback(); return jsonify({"error": "فشل تحديث العنوان لسبب غير معروف."}), 500
    except SQLAlchemyError as e: logger.error(f"Database error updating title for conversation {conversation_id}: {e}", exc_info=True); db.session.rollback(); return jsonify({"error": f"خطأ قاعدة بيانات أثناء تحديث العنوان: {e}"}), 500
    except Exception as e: logger.error(f"Unexpected error updating title for conversation {conversation_id}: {e}", exc_info=True); db.session.rollback(); return jsonify({"error": f"خطأ غير متوقع أثناء تحديث العنوان: {e}"}), 500

@app.route('/api/regenerate', methods=['POST'])
def regenerate_response():
    """API route for regenerating the last AI response."""
    try:
        data = request.json
        if not data: return jsonify({"error": "الطلب غير صالح (بيانات فارغة)"}), 400
        conversation_id_str = data.get('conversation_id'); model = data.get('model', 'mistralai/mistral-7b-instruct-v0.2'); temperature = float(data.get('temperature', 0.7)); max_tokens = int(data.get('max_tokens', 1024))
        if not conversation_id_str: return jsonify({"error": "معرف المحادثة مطلوب لإعادة التوليد"}), 400
        try: conversation_id = uuid.UUID(conversation_id_str); except ValueError: return jsonify({"error": "تنسيق معرف المحادثة غير صالح"}), 400
        logger.info(f"Received regenerate request for conversation: {conversation_id}, using model: {model}")
        stmt = select(Conversation).options(relationship(Conversation.messages)).filter_by(id=conversation_id); conversation = db.session.execute(stmt).scalar_one_or_none()
        if not conversation: logger.warning(f"Conversation not found for regeneration: {conversation_id}"); return jsonify({"error": "المحادثة المطلوبة لإعادة التوليد غير موجودة"}), 404
        messages = list(conversation.messages)
        if not messages: logger.warning(f"No messages found for regeneration in conversation {conversation_id}."); return jsonify({"error": "لا توجد رسائل في المحادثة لإعادة التوليد"}), 400
        last_message = messages[-1]
        if last_message.role != 'assistant': logger.warning(f"Last message in conv {conversation_id} is not from assistant. Cannot regenerate."); return jsonify({"error": "آخر رسالة ليست من المساعد، لا يمكن إعادة التوليد."}), 400
        logger.debug(f"Deleting last assistant message (ID: {last_message.id}) for regeneration.")
        db.session.delete(last_message)
        messages_for_api = [msg.to_dict() for msg in messages[:-1]]
        if not messages_for_api: logger.warning(f"No user messages left after removing assistant message in conv {conversation_id}."); db.session.rollback(); return jsonify({"error": "لا توجد رسائل متبقية لإرسالها بعد حذف رد المساعد"}), 400

        ai_reply = None; error_message = None; used_backup = False; api_source = "N/A"
        if OPENROUTER_API_KEY:
            api_source = "OpenRouter (Regen)"
            try:
                logger.debug(f"Regen: Sending request to OpenRouter with model: {model}, history size: {len(messages_for_api)}")
                openrouter_url = "https://openrouter.ai/api/v1/chat/completions"; headers = { "Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": APP_URL, "X-Title": APP_TITLE }; payload = { "model": model, "messages": messages_for_api, "temperature": temperature, "max_tokens": max_tokens }
                response = requests.post(url=openrouter_url, headers=headers, json=payload, timeout=45); response.raise_for_status(); api_response = response.json()
                if api_response.get('choices') and api_response['choices'][0].get('message'): ai_reply = api_response['choices'][0]['message'].get('content', '').strip(); if ai_reply: logger.info(f"Regen: Received reply from OpenRouter ({model})."); if 'usage' in api_response: logger.info(f"Regen: OpenRouter usage: {api_response['usage']}")
                else: logger.error(f"Regen: OpenRouter response structure invalid: {api_response}"); error_message = "استجابة غير متوقعة من OpenRouter أثناء إعادة التوليد"
            except requests.exceptions.Timeout: logger.error("Regen: OpenRouter API request timed out."); error_message = "مهلة OpenRouter أثناء إعادة التوليد"
            except requests.exceptions.HTTPError as e: error_body = e.response.text; logger.error(f"Regen: OpenRouter API HTTP error ({e.response.status_code}): {error_body}"); try: error_json = e.response.json(); error_details = error_json.get("error", {}).get("message", error_body); except json.JSONDecodeError: error_details = error_body[:200]; error_message = f"خطأ HTTP من OpenRouter أثناء إعادة التوليد: {error_details}"
            except requests.exceptions.RequestException as e: logger.error(f"Regen: Error calling OpenRouter: {e}", exc_info=True); error_message = f"خطأ في الاتصال بـ OpenRouter أثناء إعادة التوليد: {e}"
            except Exception as e: logger.error(f"Regen: Unexpected error processing OpenRouter response: {e}", exc_info=True); error_message = f"خطأ غير متوقع في معالجة استجابة OpenRouter أثناء إعادة التوليد: {e}"

        if not ai_reply and GEMINI_API_KEY:
            api_source = "Gemini (Backup Regen)"; logger.info("Regen: OpenRouter failed. Trying Gemini backup...");
            gemini_api_messages = [{"role": msg['role'], "content": msg['content']} for msg in messages_for_api]; ai_reply, backup_error = call_gemini_api(gemini_api_messages, temperature, max_tokens)
            if ai_reply: used_backup = True; error_message = None; logger.info("Regen: Received reply from Gemini (backup).")
            else: logger.error(f"Gemini backup also failed: {backup_error}"); error_message = error_message or f"فشل إعادة التوليد بالنموذج الاحتياطي: {backup_error}"

        if not ai_reply:
            api_source = "Offline Fallback (Regen)"; logger.warning("Regen: Both APIs failed. Falling back to offline responses.");
            ai_reply = None; error_message = error_message or "فشل إعادة توليد الرد من جميع المصادر."

        if ai_reply:
            logger.debug(f"Regen: Adding new assistant reply (from {api_source}) to DB for conv {conversation_id}")
            new_assistant_msg = conversation.add_message('assistant', ai_reply)
            try:
                db.session.commit(); logger.info(f"Regen: Successfully committed regenerated message for conv {conversation_id}")
                return jsonify({ "content": ai_reply, "used_backup": used_backup, })
            except SQLAlchemyError as e:
                 logger.error(f"Regen: Database commit error: {e}", exc_info=True); db.session.rollback()
                 return jsonify({"error": f"حدث خطأ أثناء حفظ الرد المُعاد توليده: {e}"}), 500
        else:
            logger.warning(f"Regen: Failed to generate new reply for conv {conversation_id}. Rolling back deletion.")
            db.session.rollback()
            return jsonify({"error": error_message or "فشل إعادة توليد الاستجابة"}), 500

    except Exception as e:
        logger.error(f"Critical error in /api/regenerate endpoint: {e}", exc_info=True); try: db.session.rollback(); except Exception as rollback_err: logger.error(f"Error during rollback after critical regenerate error: {rollback_err}", exc_info=True)
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

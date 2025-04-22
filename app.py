--- START OF FILE app.py ---

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
# Import SmallInteger if you plan to use the vote column
# from sqlalchemy import SmallInteger

# --- إعداد التسجيل ---
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Base Class for SQLAlchemy models (أسلوب حديث) ---
class Base(DeclarativeBase):
    pass

# --- تهيئة Flask و SQLAlchemy ---
app = Flask(__name__)

# --- تحميل الإعدادات الحساسة من متغيرات البيئة ---
app.secret_key = os.environ.get("SESSION_SECRET", "default-insecure-secret-key-for-dev") # Use a default for local dev if not set

# Database Configuration (Handles PostgreSQL and fallback to SQLite for local dev)
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    # Use a default SQLite DB for local development if DATABASE_URL is missing
    # Ensure the directory exists if using a relative path, though absolute is safer.
    db_dir = os.path.dirname(os.path.abspath(__file__))
    # os.makedirs(db_dir, exist_ok=True) # Ensure directory exists if needed
    default_db_path = os.path.join(db_dir, 'local_chat.db')
    DATABASE_URL = f'sqlite:///{default_db_path}'
    logger.warning(f"DATABASE_URL not set. Using default local SQLite database: {DATABASE_URL}")
    # Optionally raise error for production:
    # if os.environ.get('FLASK_ENV') == 'production':
    #     raise ValueError("DATABASE_URL environment variable is required for production.")
else:
    # Adjust for Render/Heroku 'postgres://' prefix
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

# Recommended DB connection settings for cloud environments (adjust if using SQLite)
# Only apply these options if using PostgreSQL
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 280,  # Recycle connections slightly before 5 min timeouts
        "pool_pre_ping": True, # Check connection validity before use
        "pool_timeout": 10,   # Max time to wait for a connection from pool
    }
else:
    # SQLite specific options if needed (e.g., timeout)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"timeout": 10}}


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize SQLAlchemy
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# --- تحميل مفاتيح API ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not OPENROUTER_API_KEY: logger.warning("OPENROUTER_API_KEY not set. OpenRouter functionality will be disabled.")
if not GEMINI_API_KEY: logger.warning("GEMINI_API_KEY not set. Gemini backup functionality will be disabled.")

# --- إعدادات أخرى للتطبيق ---
APP_URL = os.environ.get("APP_URL", "http://localhost:5001") # Default for local dev, update PORT if needed
# --- Changed App Title ---
APP_TITLE = "dzteck Chat"

# --- تعريف نماذج قاعدة البيانات ---
# Using Mapped and mapped_column for modern SQLAlchemy
class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(100), nullable=False) # Increased title length slightly
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan",
        order_by="Message.created_at", lazy="selectin" # Eagerly load messages with conversation
    )

    def add_message(self, role: str, content: str):
        """Helper method to add a message to this conversation's session."""
        new_message = Message(conversation_id=self.id, role=role, content=content)
        db.session.add(new_message)
        # self.updated_at = datetime.now(timezone.utc) # onupdate handles this automatically
        return new_message

    def to_dict(self):
        """Serialize conversation and its messages to a dictionary."""
        return {
            "id": str(self.id), # Convert UUID to string for JSON
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [message.to_dict() for message in self.messages] # Messages are pre-loaded due to lazy='selectin'
        }
    def __repr__(self): return f"<Conversation(id={self.id}, title='{self.title}')>"

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True) # Auto-incrementing integer PK
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False) # 'user', 'assistant', 'system', 'error' (maybe add 'error')
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # New: Add field for voting/feedback (optional)
    # vote: Mapped[int] = mapped_column(SmallInteger, nullable=True) # e.g., 1 for like, -1 for dislike

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    def to_dict(self):
        """Serialize message to a dictionary."""
        return {
            "id": self.id,
            "conversation_id": str(self.conversation_id), # Convert UUID to string
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            # "vote": self.vote # Include vote if added
        }
    def __repr__(self): return f"<Message(id={self.id}, role='{self.role}', conv_id={self.conversation_id})>"


# --- API Failure Fallback Responses (Keep these separate from JS predefined) ---
offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا مساعد dzteck الرقمي. للأسف، لا يوجد اتصال بالإنترنت حاليًا.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا مساعد dzteck الرقمي. أعتذر، خدمة الإنترنت غير متوفرة حاليًا.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت."
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت أو بخدمات الذكاء الاصطناعي."


# --- Call Gemini API (Backup) ---
def call_gemini_api(messages_list, temperature, max_tokens=512):
    """Calls the Gemini API as a backup. Expects messages_list format: [{'role': '...', 'content': '...'}]"""
    if not GEMINI_API_KEY:
        logger.warning("Gemini API key not available for backup.")
        return None, "مفتاح Gemini API غير متوفر"

    try:
        # Convert to Gemini format
        gemini_contents = []
        for msg in messages_list:
            # Gemini uses 'model' for assistant role
            role = "user" if msg["role"] == "user" else "model"
            gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        # Gemini prefers the last message to be from the user, but often works without it.
        if gemini_contents and gemini_contents[-1]['role'] != 'user':
             logger.warning("Gemini API call: Last message was not from user. Proceeding anyway.")
             # Optional: Add a dummy user message if strictly needed by the API version
             # gemini_contents.append({"role": "user", "parts": [{"text": "(Continue)"}]})

        # Use a generally available and capable model like 1.5 Flash
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
        logger.debug(f"Calling Gemini API ({gemini_url.split('?')[0]}) with {len(gemini_contents)} history parts...")

        response = requests.post(
            url=gemini_url,
            headers={'Content-Type': 'application/json'},
            json={
                "contents": gemini_contents,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature
                    # Add other parameters like stop sequences if needed
                }
            },
            timeout=35 # Give Gemini a reasonable timeout
        )
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        response_data = response.json()

        # Check for blocked content or empty candidates list
        if 'candidates' not in response_data or not response_data['candidates']:
            block_reason = response_data.get('promptFeedback', {}).get('blockReason', 'Unknown')
            safety_ratings = response_data.get('promptFeedback', {}).get('safetyRatings', [])
            logger.error(f"Gemini response missing candidates or blocked. Reason: {block_reason}. Ratings: {safety_ratings}")
            return None, f"الرد محظور بواسطة فلتر السلامة: {block_reason}"

        # Extract text from the response parts
        text_parts = []
        try:
            # Ensure path exists before accessing parts
            if 'content' in response_data['candidates'][0] and 'parts' in response_data['candidates'][0]['content']:
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
         # Attempt to parse JSON error, otherwise use text
         try:
             error_json = e.response.json()
             error_details = error_json.get("error", {}).get("message", e.response.text)
         except json.JSONDecodeError:
             error_details = e.response.text[:200] # Show first 200 chars of non-JSON error
         logger.error(f"Gemini API HTTP error ({e.response.status_code}): {error_details}")
         return None, f"خطأ HTTP ({e.response.status_code}) من Gemini: {error_details}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error calling Gemini API: {e}")
        return None, f"خطأ في الاتصال بالنموذج الاحتياطي (Gemini): {e}"
    except Exception as e:
        logger.error(f"Unexpected error processing Gemini response: {e}", exc_info=True)
        return None, f"خطأ غير متوقع في معالجة استجابة Gemini: {e}"


# --- Flask Routes ---

@app.route('/')
def index():
    """Route for the main chat page."""
    logger.info(f"Serving main page (index.html) request from {request.remote_addr}")
    # Pass the application title to the template
    return render_template('index.html', app_title=APP_TITLE)

@app.route('/api/chat', methods=['POST'])
def chat():
    """API route for handling chat messages. Triggered only if JS predefined responses don't match."""
    start_time = datetime.now() # Track processing time
    try:
        data = request.json
        if not data:
            logger.warning("Received empty JSON payload for /api/chat")
            return jsonify({"error": "الطلب غير صالح (بيانات فارغة)"}), 400

        # History sent from frontend includes the latest user message
        messages_for_api = data.get('history', [])
        if not messages_for_api or not isinstance(messages_for_api, list) or messages_for_api[-1].get('role') != 'user':
             logger.warning(f"Invalid 'history' received in /api/chat: {messages_for_api}")
             return jsonify({"error": "تنسيق سجل المحادثة غير صالح أو آخر رسالة ليست للمستخدم"}), 400

        user_message = messages_for_api[-1]['content'].strip()
        if not user_message:
             logger.warning("Received empty user message content in /api/chat history.")
             return jsonify({"error": "محتوى الرسالة فارغ"}), 400

        model = data.get('model', 'mistralai/mistral-7b-instruct') # Default model
        conversation_id_str = data.get('conversation_id') # Can be null for new conversations
        temperature = float(data.get('temperature', 0.7))
        max_tokens = int(data.get('max_tokens', 1024)) # Default max tokens

        # --- Get or Create Conversation in Database ---
        db_conversation = None
        conversation_id = None
        is_new_conversation = False

        if conversation_id_str:
            try:
                conversation_id = uuid.UUID(conversation_id_str)
                stmt = select(Conversation).filter_by(id=conversation_id)
                db_conversation = db.session.execute(stmt).scalar_one_or_none()
                if db_conversation:
                    logger.info(f"Continuing existing conversation: {conversation_id}")
                else:
                     logger.warning(f"Conversation ID '{conversation_id_str}' provided but not found in DB. Creating new.")
                     conversation_id = None # Treat as new if ID not found
            except ValueError:
                logger.warning(f"Invalid UUID format received for conversation_id: {conversation_id_str}. Creating new.")
                conversation_id = None # Treat as new if format is wrong

        if not db_conversation:
            is_new_conversation = True
            conversation_id = uuid.uuid4()
            # Create a title from the first ~80 chars of the first user message
            initial_title = user_message.split('\n', 1)[0][:80]
            logger.info(f"Creating new conversation with ID: {conversation_id}, title: '{initial_title}'")
            db_conversation = Conversation(id=conversation_id, title=initial_title or "محادثة جديدة")
            db.session.add(db_conversation)
            # If it's the very first message, add the preceding AI welcome message too for context, if desired
            # This assumes the *frontend* doesn't send the welcome message in its history array
            # if len(messages_for_api) == 1:
            #     db_conversation.add_message('assistant', "السلام عليكم! أنا مساعد dzteck الرقمي...") # Add welcome msg to DB history

        # --- Add the current user message to the DB ---
        # The 'history' from frontend already contains this message for context,
        # but we need to persist it in our DB.
        user_msg_db = db_conversation.add_message('user', user_message)
        # No need to check for duplicates here, assume frontend handles rapid clicks. Add every API request message.

        # --- API Calls ---
        ai_reply = None
        error_message = None
        used_backup = False
        api_source = "N/A" # To track which API succeeded

        # 1. Try OpenRouter
        if OPENROUTER_API_KEY:
            api_source = "OpenRouter"
            try:
                logger.debug(f"Sending request to OpenRouter: model={model}, history_len={len(messages_for_api)}")
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": APP_URL, # Required by OpenRouter
                    "X-Title": APP_TITLE,     # Optional site name
                }
                # Ensure message format matches API requirements ({role: 'user'/'assistant', content: '...'})
                payload = {
                    "model": model,
                    "messages": messages_for_api, # Send the history received from frontend
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    # Optional: Add other parameters like 'stream: false' if needed
                }
                response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=45) # Increased timeout
                response.raise_for_status() # Raises HTTPError for 4xx/5xx responses
                api_response = response.json()

                # Extract response, checking structure carefully
                if api_response.get('choices') and isinstance(api_response['choices'], list) and len(api_response['choices']) > 0:
                    message_data = api_response['choices'][0].get('message')
                    if message_data and isinstance(message_data, dict):
                        ai_reply = message_data.get('content', '').strip()
                        if ai_reply:
                            logger.info(f"Received reply from OpenRouter ({model}).")
                            # Log usage if available
                            if 'usage' in api_response: logger.info(f"OpenRouter usage: {api_response['usage']}")
                        else:
                             logger.warning(f"OpenRouter ({model}) returned an empty content string. Response: {api_response}")
                             # Treat empty content as potentially valid (e.g., filtered), not necessarily an error yet.
                    else:
                         logger.error(f"OpenRouter response structure invalid (missing message object): {api_response}")
                         error_message = "استجابة غير متوقعة من OpenRouter (message)"
                else:
                    logger.error(f"OpenRouter response structure invalid (missing choices array): {api_response}")
                    error_message = "استجابة غير متوقعة من OpenRouter (choices)"

            except requests.exceptions.Timeout:
                logger.error("OpenRouter API request timed out.")
                error_message = "استجابة OpenRouter استغرقت وقتاً طويلاً"
            except requests.exceptions.HTTPError as e:
                # Try to get detailed error from response body
                try: error_details = e.response.json().get("error", {}).get("message", e.response.text)
                except json.JSONDecodeError: error_details = e.response.text[:200]
                logger.error(f"OpenRouter API HTTP error ({e.response.status_code}): {error_details}")
                error_message = f"خطأ HTTP ({e.response.status_code}) من OpenRouter: {error_details}"
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error calling OpenRouter API: {e}", exc_info=True)
                error_message = f"خطأ في الاتصال بـ OpenRouter: {e}"
            except Exception as e:
                logger.error(f"Unexpected error processing OpenRouter response: {e}", exc_info=True)
                error_message = f"خطأ غير متوقع في معالجة استجابة OpenRouter: {e}"

        # 2. Try Gemini Backup if OpenRouter failed or returned no content
        if not ai_reply and GEMINI_API_KEY:
            api_source = "Gemini (Backup)"
            logger.info("OpenRouter failed or unavailable. Trying Gemini API as backup...")
            # Pass the same history used for OpenRouter
            ai_reply, backup_error = call_gemini_api(messages_for_api, temperature, max_tokens)
            if ai_reply:
                used_backup = True
                error_message = None # Clear previous OpenRouter error if Gemini succeeds
                logger.info("Received reply from Gemini (backup).")
            else:
                logger.error(f"Gemini backup also failed: {backup_error}")
                # Keep the original error_message if it exists, otherwise use the Gemini error
                error_message = error_message or f"فشل النموذج الاحتياطي (Gemini): {backup_error}"

        # 3. If both APIs fail, use predefined offline responses
        if not ai_reply:
            api_source = "Offline Fallback"
            logger.warning("Both API calls failed. Falling back to predefined offline responses.")
            # Match user message against keys in offline_responses
            user_msg_lower = user_message.lower() # Match case-insensitively
            matched_response = None
            for key, response_text in offline_responses.items():
                if key.lower() in user_msg_lower: # Simple substring match
                    matched_response = response_text
                    logger.info(f"Matched offline response for key: '{key}'")
                    break
            ai_reply = matched_response or default_offline_response
            if not matched_response: logger.info("Using default offline response.")

        # --- Save AI reply to Database and Commit Transaction ---
        if ai_reply:
            logger.debug(f"Adding assistant reply (from {api_source}) to DB for conversation {db_conversation.id}")
            assistant_msg_db = db_conversation.add_message('assistant', ai_reply)
            try:
                db.session.commit() # Commit user message and AI reply (and new conversation if applicable)
                elapsed = (datetime.now(timezone.utc) - start_time.replace(tzinfo=timezone.utc)).total_seconds()
                logger.info(f"Chat request processed for conv {db_conversation.id} in {elapsed:.2f}s.")
                # Return the AI reply and conversation ID
                response_payload = {
                    "id": str(db_conversation.id), # Always return the ID
                    "content": ai_reply,
                    "used_backup": used_backup,
                    # Optionally send the new message ID if needed by frontend
                    # "new_message_id": assistant_msg_db.id
                }
                # Indicate if a new conversation was created
                # if is_new_conversation: response_payload["new_conversation_created"] = True # Frontend doesn't strictly need this if ID is sent

                return jsonify(response_payload)
            except SQLAlchemyError as e:
                 logger.error(f"Database commit error after getting AI reply: {e}", exc_info=True)
                 db.session.rollback() # Rollback the transaction
                 # Return error, indicating DB save failed
                 return jsonify({"error": f"حدث خطأ أثناء حفظ الرد في قاعدة البيانات: {e}"}), 500
        else:
            # This block should theoretically not be reached due to offline fallback, but acts as a safeguard.
            logger.error("Critical: Failed to generate any response (AI or offline). This should not happen.")
            db.session.rollback() # Rollback the user message add if no AI reply could be generated/saved
            return jsonify({"error": error_message or "فشل توليد استجابة"}), 500

    except Exception as e:
        # Catch-all for any unexpected errors within the endpoint logic
        logger.error(f"Critical error in /api/chat endpoint: {e}", exc_info=True)
        # Attempt to rollback any pending DB changes
        try:
            db.session.rollback()
        except Exception as rollback_err:
             logger.error(f"Error during rollback after critical chat error: {rollback_err}", exc_info=True)
        return jsonify({"error": f"حدث خطأ داخلي خطير في الخادم: {e}"}), 500


# --- Conversation Management Endpoints ---

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """API route to get a list of all conversations (ID, title, updated_at)."""
    try:
        logger.info("Fetching conversation list...")
        # Select only necessary columns for the list view, order by most recent
        stmt = select(Conversation.id, Conversation.title, Conversation.updated_at).order_by(desc(Conversation.updated_at))
        results = db.session.execute(stmt).all() # Fetch rows
        # Convert rows to list of dictionaries
        conversations_list = [
            {"id": str(row.id), "title": row.title, "updated_at": row.updated_at.isoformat()}
            for row in results
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
    # UUID converter in route handles basic format validation
    try:
        logger.info(f"Fetching conversation details for ID: {conversation_id}")
        # lazy='selectin' on the relationship automatically loads messages efficiently here
        stmt = select(Conversation).filter_by(id=conversation_id)
        conversation = db.session.execute(stmt).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Conversation not found for ID: {conversation_id}")
            return jsonify({"error": "المحادثة المطلوبة غير موجودة"}), 404

        logger.info(f"Conversation '{conversation.title}' found, returning details including {len(conversation.messages)} messages.")
        return jsonify(conversation.to_dict()) # Use the model's serialization method
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
        stmt = select(Conversation).filter_by(id=conversation_id)
        conversation = db.session.execute(stmt).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Attempted to delete non-existent conversation: {conversation_id}")
            return jsonify({"error": "المحادثة المطلوب حذفها غير موجودة"}), 404

        # Delete the conversation. Cascade='all, delete-orphan' handles associated messages.
        db.session.delete(conversation)
        db.session.commit()
        logger.info(f"Successfully deleted conversation: {conversation_id}")
        return jsonify({"success": True, "message": "تم حذف المحادثة وجميع رسائلها بنجاح"})

    except SQLAlchemyError as e:
        logger.error(f"Database error deleting conversation {conversation_id}: {e}", exc_info=True)
        db.session.rollback() # Rollback on error
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

        if not new_title or len(new_title) > 100:
            logger.warning(f"Invalid title received for conversation {conversation_id}: '{new_title}'")
            return jsonify({"error": "عنوان المحادثة مطلوب ويجب ألا يتجاوز 100 حرف"}), 400

        logger.info(f"Attempting to update title for conversation {conversation_id} to '{new_title}'")
        # Use efficient update statement
        stmt = update(Conversation).\
               where(Conversation.id == conversation_id).\
               values(title=new_title, updated_at=datetime.now(timezone.utc))
               # .returning(Conversation.id) # Optional: verify update, though rowcount check is simpler

        result = db.session.execute(stmt)

        if result.rowcount == 0:
            # Check if the conversation exists at all before concluding failure
            exists_stmt = select(Conversation.id).filter_by(id=conversation_id)
            if not db.session.execute(exists_stmt).scalar_one_or_none():
                 logger.warning(f"Attempted to update title for non-existent conversation: {conversation_id}")
                 return jsonify({"error": "المحادثة المطلوب تحديثها غير موجودة"}), 404
            else:
                 # Row exists but wasn't updated (e.g., title was the same). Log and proceed to commit anyway to update timestamp.
                 logger.warning(f"Title update for conversation {conversation_id} affected 0 rows, but it exists (title might be unchanged). Proceeding to commit.")

        db.session.commit()
        logger.info(f"Successfully updated title/timestamp for conversation: {conversation_id}")
        return jsonify({"success": True, "message": "تم تحديث عنوان المحادثة بنجاح"})

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
    """API route for regenerating the last AI response in a conversation."""
    start_time = datetime.now()
    try:
        data = request.json
        if not data: return jsonify({"error": "الطلب غير صالح"}), 400

        conversation_id_str = data.get('conversation_id')
        model = data.get('model', 'mistralai/mistral-7b-instruct') # Use same default as /chat
        temperature = float(data.get('temperature', 0.7))
        max_tokens = int(data.get('max_tokens', 1024))

        if not conversation_id_str: return jsonify({"error": "معرف المحادثة مطلوب لإعادة التوليد"}), 400
        try: conversation_id = uuid.UUID(conversation_id_str)
        except ValueError: return jsonify({"error": "تنسيق معرف المحادثة غير صالح"}), 400

        logger.info(f"Regenerate request for conversation: {conversation_id}, using model: {model}")

        # --- Get Conversation and Messages ---
        # lazy='selectin' loads messages automatically
        stmt = select(Conversation).filter_by(id=conversation_id)
        conversation = db.session.execute(stmt).scalar_one_or_none()
        if not conversation: return jsonify({"error": "المحادثة المطلوبة لإعادة التوليد غير موجودة"}), 404

        messages_db = conversation.messages # Messages are ordered by created_at
        if not messages_db: return jsonify({"error": "لا توجد رسائل في المحادثة لإعادة التوليد"}), 400

        # --- Find last assistant message and history BEFORE it ---
        last_ai_message_index = -1
        for i in range(len(messages_db) - 1, -1, -1):
            if messages_db[i].role == 'assistant':
                last_ai_message_index = i
                break

        if last_ai_message_index == -1:
             logger.warning(f"No assistant message found to regenerate in conv {conversation_id}.")
             return jsonify({"error": "لم يتم العثور على ردود سابقة من المساعد لإعادة توليدها."}), 400

        last_ai_message = messages_db[last_ai_message_index]
        # History for API call includes all messages *before* the last AI message
        messages_for_api = [msg.to_dict() for msg in messages_db[:last_ai_message_index]]

        # Ensure there's valid history (at least one user message usually)
        if not messages_for_api or messages_for_api[-1].get('role') != 'user':
             logger.warning(f"Regen: No valid user message found before the last AI message in conv {conversation_id}.")
             return jsonify({"error": "لا توجد رسائل كافية قبل رد المساعد لإعادة التوليد."}), 400

        # --- Delete the last AI message from the session (will be deleted on commit) ---
        logger.debug(f"Regen: Deleting last assistant message (ID: {last_ai_message.id}) for regeneration.")
        db.session.delete(last_ai_message)
        # Flush to ensure deletion is staged before API call, in case API depends on DB state (unlikely here)
        # db.session.flush() # Usually not necessary unless reading immediately after delete

        # --- Re-call APIs (using the history *before* the deleted message) ---
        ai_reply, error_message, used_backup, api_source = None, None, False, "N/A"

        # 1. Try OpenRouter... (Similar logic as /chat)
        if OPENROUTER_API_KEY:
            api_source = "OpenRouter (Regen)"
            try:
                 logger.debug(f"Regen: Sending request to OpenRouter: model={model}, history_len={len(messages_for_api)}")
                 headers = { "Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": APP_URL, "X-Title": APP_TITLE }
                 payload = { "model": model, "messages": messages_for_api, "temperature": temperature, "max_tokens": max_tokens }
                 response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=45)
                 response.raise_for_status()
                 api_response = response.json()
                 if api_response.get('choices') and api_response['choices'][0].get('message'):
                     ai_reply = api_response['choices'][0]['message'].get('content', '').strip()
                     if ai_reply: logger.info(f"Regen: Received reply from OpenRouter ({model}).")
                     else: logger.warning(f"Regen: OpenRouter returned empty content for {model}.")
                 else: logger.error(f"Regen: OpenRouter response invalid: {api_response}"); error_message = "استجابة غير متوقعة من OpenRouter"
            except Exception as e: # Catch broad errors
                 if isinstance(e, requests.exceptions.Timeout): error_message = "مهلة OpenRouter أثناء إعادة التوليد"
                 elif isinstance(e, requests.exceptions.HTTPError):
                     try: error_details = e.response.json().get("error", {}).get("message", e.response.text)
                     except json.JSONDecodeError: error_details = e.response.text[:200]
                     error_message = f"خطأ HTTP ({e.response.status_code}) من OpenRouter: {error_details}"
                 else: error_message = f"خطأ OpenRouter أثناء إعادة التوليد: {e}"
                 logger.error(f"Regen: OpenRouter error: {error_message}", exc_info=isinstance(e, requests.exceptions.RequestException))

        # 2. Try Gemini Backup... (Similar logic as /chat)
        if not ai_reply and GEMINI_API_KEY:
            api_source = "Gemini (Backup Regen)"
            logger.info("Regen: OpenRouter failed. Trying Gemini backup...")
            gemini_history = [{"role": m["role"], "content": m["content"]} for m in messages_for_api] # Ensure correct format
            ai_reply, backup_error = call_gemini_api(gemini_history, temperature, max_tokens)
            if ai_reply: used_backup = True; error_message = None; logger.info("Regen: Received reply from Gemini (backup).")
            else: logger.error(f"Regen: Gemini backup also failed: {backup_error}"); error_message = error_message or f"فشل إعادة التوليد بالنموذج الاحتياطي: {backup_error}"

        # --- Handle API Failure during Regenerate ---
        if not ai_reply:
            logger.error(f"Regen: Both APIs failed for conv {conversation_id}. Rolling back deletion.")
            # IMPORTANT: Rollback the deletion of the original AI message since we couldn't get a new one.
            db.session.rollback()
            return jsonify({"error": error_message or "فشل إعادة توليد الرد من جميع المصادر."}), 500

        # --- Save the NEW AI reply and Commit (includes deleting the old one) ---
        if ai_reply:
            logger.debug(f"Regen: Adding new assistant reply (from {api_source}) to DB for conv {conversation.id}")
            new_assistant_msg = conversation.add_message('assistant', ai_reply)
            try:
                # Commit the transaction (deletes old AI message, adds new AI message, updates conversation timestamp)
                db.session.commit()
                elapsed = (datetime.now(timezone.utc) - start_time.replace(tzinfo=timezone.utc)).total_seconds()
                logger.info(f"Regen request processed for conv {conversation.id} in {elapsed:.2f}s.")
                # Return only the new content and backup status
                return jsonify({
                    "content": ai_reply,
                    "used_backup": used_backup,
                    # Optionally return new message ID: "new_message_id": new_assistant_msg.id
                })
            except SQLAlchemyError as e:
                 logger.error(f"Regen: Database commit error after getting new reply: {e}", exc_info=True)
                 db.session.rollback() # Rollback if commit fails
                 return jsonify({"error": f"حدث خطأ أثناء حفظ الرد المُعاد توليده: {e}"}), 500

    except Exception as e:
        logger.error(f"Critical error in /api/regenerate endpoint: {e}", exc_info=True)
        try: db.session.rollback() # Attempt rollback on any critical error
        except Exception as rollback_err: logger.error(f"Error during rollback after critical regenerate error: {rollback_err}", exc_info=True)
        return jsonify({"error": f"خطأ داخلي خطير أثناء إعادة التوليد: {e}"}), 500


# --- General Error Handlers ---
@app.errorhandler(404)
def not_found_error(error):
    """Handles 404 Not Found errors."""
    logger.warning(f"404 Not Found: {request.path} from {request.remote_addr}")
    if request.path.startswith('/api/'):
        return jsonify({"error": "نقطة النهاية المطلوبة غير موجودة."}), 404
    # You might want to create a simple templates/404.html page
    # return render_template('404.html'), 404
    return "<h1>404 Not Found</h1><p>الصفحة المطلوبة غير موجودة.</p>", 404

@app.errorhandler(500)
def internal_error(error):
    """Handles 500 Internal Server errors."""
    original_exception = getattr(error, 'original_exception', error)
    logger.error(f"500 Internal Server Error: {request.path} from {request.remote_addr}: {original_exception}", exc_info=True)
    try:
        db.session.rollback() # Rollback any pending transactions
        logger.info("Database session rolled back after 500 error.")
    except Exception as e:
        logger.error(f"Error during rollback after 500 error: {e}", exc_info=True)

    if request.path.startswith('/api/'):
        return jsonify({"error": "حدث خطأ داخلي غير متوقع في الخادم."}), 500
    # You might want to create a simple templates/500.html page
    # return render_template('500.html'), 500
    return "<h1>500 Internal Server Error</h1><p>حدث خطأ غير متوقع في الخادم. يرجى المحاولة مرة أخرى لاحقاً.</p>", 500

@app.errorhandler(Exception) # Catch-all for any other unhandled exceptions
def handle_exception(e):
     """Handles any other unhandled exceptions."""
     logger.error(f"Unhandled Exception: {request.path} from {request.remote_addr}: {e}", exc_info=True)
     # Attempt rollback just in case
     try: db.session.rollback()
     except Exception as rollback_err: logger.error(f"Rollback failed after unhandled exception: {rollback_err}", exc_info=True)

     # Determine status code (default to 500)
     status_code = 500
     error_message = "حدث خطأ غير متوقع."
     if isinstance(e, requests.exceptions.HTTPError):
         status_code = e.response.status_code if e.response else 500
         error_message = f"خطأ في الاتصال بخدمة خارجية: {e}"
     elif isinstance(e, SQLAlchemyError):
         error_message = "حدث خطأ في قاعدة البيانات."
     elif isinstance(e, (ValueError, TypeError)): # Handle common programming errors gracefully
        status_code = 400 # Bad request likely caused it
        error_message = f"خطأ في بيانات الطلب: {e}"


     if request.path.startswith('/api/'):
         return jsonify({"error": error_message}), status_code
     # Render a generic error page for non-API routes
     # return render_template('error.html', error_code=status_code, error_message=error_message), status_code
     return f"<h1>Error {status_code}</h1><p>{error_message}</p>", status_code


# --- Database Initialization ---
def initialize_database():
    """Creates database tables if they don't exist."""
    with app.app_context():
        logger.info("Checking and initializing database...")
        try:
            # db.reflect() # Optional: check existing tables before creating
            db.create_all() # Creates tables based on models defined above, safe to run multiple times
            logger.info("Database tables checked/created successfully.")
        except SQLAlchemyError as e:
            # Try to show DB path safely without credentials
            db_uri_safe = str(app.config.get("SQLALCHEMY_DATABASE_URI"))
            if "@" in db_uri_safe: db_uri_safe = db_uri_safe.split("@", 1)[1] # Show only host/db part
            logger.error(f"FATAL: SQLAlchemyError occurred during db.create_all() for DB: ...@{db_uri_safe}. Error: {e}", exc_info=False) # Avoid full stack trace in basic log
            # Consider raising SystemExit only in production or if DB is absolutely essential at startup
            # raise SystemExit(f"Database initialization failed: {e}") from e
        except Exception as e:
            logger.error(f"FATAL: An unexpected error occurred during db.create_all(): {e}", exc_info=True)
            # raise SystemExit(f"Unexpected database initialization error: {e}") from e

# Call the initialization function when the app starts
initialize_database()
logger.info("Database initialization routine finished.")

# --- WSGI Entry Point / Local Development Server ---
if __name__ == '__main__':
    # This block runs only when script is executed directly (python app.py)
    # NOT used by Gunicorn/Render
    logger.info("Starting Flask development server (use Gunicorn/WSGI for production)...")
    # Use PORT environment variable provided by Render, or 5001 for local dev
    port = int(os.environ.get("PORT", 5001))
    # Set debug=True ONLY for local development for auto-reload and better error pages.
    # NEVER run with debug=True in production! Render sets FLASK_DEBUG=0 by default.
    use_debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host='0.0.0.0', port=port, debug=use_debug)
else:
    # This block runs when imported as a module (e.g., by Gunicorn)
    # Configure logging to integrate with Gunicorn's logging if available
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)
    logger.info(f"Application '{APP_TITLE}' starting via WSGI server (e.g., Gunicorn).")

--- END OF FILE app.py ---

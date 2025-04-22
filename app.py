import os
import logging
import requests
import json
import uuid
import re # Import regex module for better offline matching
from datetime import datetime, timezone # Import timezone-aware datetime

from flask import Flask, request, jsonify, render_template, g # Import g for request-specific context
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, DateTime, ForeignKey, select, delete, update, desc, func
from sqlalchemy.dialects.postgresql import UUID # Import UUID type for PostgreSQL
from sqlalchemy.exc import SQLAlchemyError

# --- إعداد التسجيل ---
# On platforms like Render, stdout/stderr output is captured and displayed in logs
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Base Class for SQLAlchemy models (Modern Style) ---
class Base(DeclarativeBase):
    pass

# --- تهيئة Flask و SQLAlchemy ---
app = Flask(__name__)

# --- Load sensitive settings from environment variables (Essential for Render) ---
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    logger.warning("SESSION_SECRET environment variable not set. Using a default insecure key.")
    app.secret_key = "default-insecure-secret-key-for-render" # Use only if variable is not set

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.error("FATAL: DATABASE_URL environment variable is not set.")
    # You might want to exit startup here
    # import sys
    # sys.exit("DATABASE_URL environment variable not set.")
else:
    # Render might provide 'postgres://' instead of 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

# Recommended database connection settings for cloud environments
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,  # Slightly less than 5 minutes (common timeout)
    "pool_pre_ping": True, # Check connection before using it
    "pool_timeout": 10,   # Wait time for getting a connection from the pool
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize SQLAlchemy with the app and Base model
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# --- Load API Keys ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY environment variable is not set. OpenRouter functionality will be disabled.")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY environment variable is not set. Gemini backup functionality may be limited.")


# Other app settings
APP_URL = os.environ.get("APP_URL", "http://localhost:5000") # Default value for local testing
APP_TITLE = "Yasmin GPT Chat"

# --- Define Database Models (Integrated Here) ---

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
    # messages relationship will automatically handle deleting related MessageVote objects due to cascade on Message

    def add_message(self, role: str, content: str):
        """ Helper method to add a message to this conversation """
        new_message = Message(
            conversation_id=self.id,
            role=role,
            content=content,
            created_at=datetime.now(timezone.utc) # Ensure server time is used
        )
        db.session.add(new_message)
        # The updated_at on Conversation is handled by onupdate=...
        # db.session.flush() # Optional: to get the ID if needed immediately
        return new_message

    def to_dict(self):
        """ Serialize conversation and its messages to a dictionary """
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

    id: Mapped[int] = mapped_column(primary_key=True) # Use auto-incrementing integer as PK
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False) # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    # Relationship to MessageVote (one-to-many) - one message can have multiple votes (from different users)
    votes: Mapped[list["MessageVote"]] = relationship(
        "MessageVote",
        back_populates="message",
        cascade="all, delete-orphan", # Delete votes if message is deleted
        lazy="noload" # Don't load votes when fetching messages by default
    )


    def to_dict(self):
        """ Serialize message to a dictionary """
        return {
            "id": self.id, # Include DB ID
            "conversation_id": str(self.conversation_id),
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() # Include timestamp
            # Aggregated vote counts are not included by default for performance
            # You could add a method to fetch votes specifically if needed
        }

    def __repr__(self):
        return f"<Message(id={self.id}, role='{self.role}', conv_id={self.conversation_id})>"

class MessageVote(Base):
    __tablename__ = "message_votes" # New table for votes

    id: Mapped[int] = mapped_column(primary_key=True) # Use auto-incrementing integer as PK
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True) # Redundant but useful index
    vote_type: Mapped[str] = mapped_column(String(10), nullable=False) # 'like' or 'dislike'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    message: Mapped["Message"] = relationship("Message", back_populates="votes")
    conversation: Mapped["Conversation"] = relationship("Conversation") # Simple relationship

    # Optional: Add a constraint to prevent duplicate votes from the same user on the same message
    # This requires tracking users, which is not in scope yet.
    # __table_args__ = (UniqueConstraint('message_id', 'user_id', name='_message_user_vote_uc'),) # requires 'user_id' column

    def to_dict(self):
        """ Serialize vote to a dictionary """
        return {
            "id": self.id,
            "message_id": self.message_id,
            "conversation_id": str(self.conversation_id),
            "vote_type": self.vote_type,
            "created_at": self.created_at.isoformat()
        }

    def __repr__(self):
        return f"<MessageVote(id={self.id}, message_id={self.message_id}, vote_type='{self.vote_type}')>"


# --- الردود الاحتياطية (للاستخدام عند فشل كل الـ APIs) ---
offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا ياسمين. للأسف، لا يوجد اتصال بالإنترنت حاليًا.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا ياسمين. أعتذر، خدمة الإنترنت غير متوفرة حاليًا.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت.",
     "ما هي قدراتك": "لا يمكنني الوصول إلى الإنترنت حاليًا، لذا لا يمكنني عرض قدراتي الكاملة.", # Fallback specific to offline
     "ما هو الذكاء الاصطناعي": "في وضع عدم الاتصال، لا يمكنني تقديم تعريف كامل للذكاء الاصطناعي. يرجى التحقق من اتصالك بالإنترنت.", # Fallback specific to offline
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت أو بخدمات الذكاء الاصطناعي."

# --- دالة استدعاء Gemini API (النموذج الاحتياطي) ---
def call_gemini_api(messages_list, temperature, max_tokens=1024):
    """Call the Gemini API as a backup"""
    if not GEMINI_API_KEY:
        logger.warning("Gemini API key not available for backup.")
        return None, "مفتاح Gemini API غير متوفر"

    try:
        # تحويل تنسيق الرسائل لـ Gemini
        # Gemini API expects alternating user/model roles, starting with user
        gemini_contents = []
        last_role = None
        for msg in messages_list:
            role = "user" if msg["role"] == "user" else "model" # Gemini uses 'model' for assistant
            # Only add message if role is different from the last one added, or it's the very first message
            if role != last_role:
                gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})
                last_role = role
            else:
                 logger.warning(f"Gemini API call: Skipping consecutive message with same role ({role}). Content: {msg['content'][:50]}...")


        # Ensure the last entry is from the user role before sending to models that require it
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
            # Attempt to get rejection reason from candidates if available but empty
            if 'candidates' in response_data and len(response_data['candidates']) > 0 and 'finishReason' in response_data['candidates'][0]:
                 finish_reason = response_data['candidates'][0]['finishReason']
                 error_text = f"تم إنهاء الرد بسبب: {finish_reason}"
            else:
                 error_text = f"الرد محظور بواسطة فلتر السلامة: {block_reason}"
            return None, error_text


        text_parts = []
        try:
            # Iterate through parts, specifically looking for 'text'
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
         try:
             error_json = e.response.json()
             error_details = error_json.get("error", {}).get("message", error_body)
         except json.JSONDecodeError:
             error_details = error_body[:200]
         return None, f"خطأ HTTP من النموذج الاحتياطي: {error_details}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Gemini API: {e}", exc_info=True)
        return None, f"خطأ في الاتصال بالنموذج الاحتياطي (Gemini): {e}"
    except Exception as e:
        logger.error(f"Unexpected error processing Gemini response: {e}", exc_info=True)
        return None, f"خطأ غير متوقع في معالجة استجابة النموذج الاحتياطي: {e}"


# --- مسارات Flask (Routes) ---

@app.route('/')
def index():
    """Route for the main chat page."""
    # logger.info(f"Serving main page (index.html) requested by {request.remote_addr}") # Too noisy
    return render_template('index.html', app_title=APP_TITLE)

@app.route('/api/chat', methods=['POST'])
def chat():
    """API route for handling chat messages."""
    try:
        data = request.json
        if not data:
            logger.warning("Received empty JSON payload for /api/chat")
            return jsonify({"error": "الطلب غير صالح (بيانات فارغة)"}), 400

        messages_for_api = data.get('history', [])
        # Ensure history is a list of dicts and has at least one message
        if not isinstance(messages_for_api, list) or not messages_for_api:
             logger.warning(f"Invalid or empty 'history' received in /api/chat: {messages_for_api}")
             return jsonify({"error": "تنسيق سجل المحادثة غير صالح"}), 400

        # The last message must be from the user in this flow
        if messages_for_api[-1].get('role') != 'user':
             logger.warning(f"Last message in history is not from user: {messages_for_api[-1]}")
             return jsonify({"error": "آخر رسالة في السجل يجب أن تكون للمستخدم"}), 400

        user_message_content = messages_for_api[-1].get('content', '').strip()
        if not user_message_content:
             logger.warning("Received empty user message content in /api/chat history.")
             return jsonify({"error": "محتوى الرسالة فارغ"}), 400

        model = data.get('model', 'mistralai/mistral-7b-instruct-v0.2')
        conversation_id_str = data.get('conversation_id') # Can be null for new conversation
        temperature = float(data.get('temperature', 0.7))
        max_tokens = int(data.get('max_tokens', 1024))

        db_conversation = None
        conversation_id = None
        user_msg_db = None # To store the DB message object for the user's message

        # --- Get or Create Conversation ---
        if conversation_id_str:
            try:
                conversation_id = uuid.UUID(conversation_id_str)
                # Load conversation but not all messages yet (can optimize here if history is huge)
                stmt = select(Conversation).filter_by(id=conversation_id)
                db_conversation = db.session.execute(stmt).scalar_one_or_none()
                if db_conversation:
                    logger.debug(f"Found existing conversation: {conversation_id}")
                else:
                     logger.warning(f"Conversation ID '{conversation_id_str}' provided but not found in DB. Treating as new conversation.")
                     conversation_id = None # Treat as new
            except ValueError:
                logger.warning(f"Invalid UUID format received for conversation_id: {conversation_id_str}. Treating as new conversation.")
                conversation_id = None # Treat as new

        if not db_conversation:
            conversation_id = uuid.uuid4() # Create a new UUID
            initial_title = user_message_content.split('\n')[0][:80] # Use up to 80 chars for title
            logger.info(f"Creating new conversation with ID: {conversation_id}, initial title: '{initial_title or 'محادثة جديدة'}'")
            db_conversation = Conversation(id=conversation_id, title=initial_title or "محادثة جديدة")
            db.session.add(db_conversation)
            # Don't commit yet, wait until we have the AI reply

        # --- Add User Message to DB ---
        # We need the DB ID for the user message to return it and for potential future features
        # Using server time for created_at
        user_msg_db = Message(
             conversation_id=db_conversation.id,
             role='user',
             content=user_message_content,
             created_at=datetime.now(timezone.utc)
        )
        db.session.add(user_msg_db)
        db.session.flush() # Use flush to get the user_msg_db.id before commit


        # --- Prepare message history for the API call ---
        # Use the messages_for_api list received from frontend directly for the AI call.
        # This list includes the new user message.
        api_history = messages_for_api


        # --- Call APIs ---
        ai_reply_content = None
        error_message = None
        used_backup = False
        api_source = "N/A"

        # 1. Attempt OpenRouter
        if OPENROUTER_API_KEY:
            api_source = "OpenRouter"
            try:
                logger.debug(f"Calling OpenRouter with model: {model}, history size: {len(api_history)}")
                openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": APP_URL, # Required for OpenRouter tracking
                    "X-Title": APP_TITLE,
                }
                payload = {
                    "model": model,
                    "messages": api_history, # Use history from frontend
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                response = requests.post(url=openrouter_url, headers=headers, json=payload, timeout=60) # Increased timeout
                response.raise_for_status()
                api_response = response.json()

                if api_response.get('choices') and api_response['choices'][0].get('message'):
                    ai_reply_content = api_response['choices'][0]['message'].get('content', '').strip()
                    if not ai_reply_content:
                         logger.warning(f"OpenRouter returned empty content for model {model}. Response: {api_response}")
                    else:
                        logger.info(f"Received reply from OpenRouter ({model}).")
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

        # 2. Attempt Gemini as backup
        if not ai_reply_content and GEMINI_API_KEY:
            api_source = "Gemini (Backup)"
            logger.info("OpenRouter failed or unavailable. Trying Gemini API as backup...")
            # Pass the same history list to Gemini
            ai_reply_content, backup_error = call_gemini_api(api_history, temperature, max_tokens)
            if ai_reply_content:
                used_backup = True
                error_message = None # Clear OpenRouter error if Gemini succeeded
                logger.info("Received reply from Gemini (backup).")
            else:
                logger.error(f"Gemini backup also failed: {backup_error}")
                error_message = error_message or f"فشل النموذج الاحتياطي (Gemini): {backup_error}"

        # 3. If both failed, use offline fallback
        if not ai_reply_content:
            api_source = "Offline Fallback"
            logger.warning("Both API calls failed. Falling back to predefined offline responses.")
            matched_offline = False
            # Use the *actual* user message content from DB object for matching
            user_msg_lower = user_msg_db.content.lower().strip() # Use content from DB message
            # Refine offline matching - use regex for better matching
            for key, response_text in offline_responses.items():
                cleaned_key = key.lower().strip()
                 # Use regex to find the key as a whole word, case-insensitive
                 # \b matches a word boundary
                 pattern = r'\b' + re.escape(cleaned_key) + r'\b'
                 if re.search(pattern, user_msg_lower):
                     ai_reply_content = response_text
                     matched_offline = True
                     logger.info(f"Matched offline response for key: '{key}'")
                     break
            if not matched_offline:
                ai_reply_content = default_offline_response
                logger.info("Using default offline response.")

        # --- Save AI reply to DB and Commit ---
        if ai_reply_content:
            logger.debug(f"Adding assistant reply (from {api_source}) to DB for conversation {db_conversation.id}")
            assistant_msg_db = Message( # Create new message object for AI reply
                 conversation_id=db_conversation.id,
                 role='assistant',
                 content=ai_reply_content,
                 created_at=datetime.now(timezone.utc) # Use server time
            )
            db.session.add(assistant_msg_db) # Add to session

            try:
                db.session.commit() # Commit all changes (new conversation if applicable, user message, assistant message)
                logger.info(f"Successfully committed messages for conversation {db_conversation.id}")

                # Return the response including message IDs
                return jsonify({
                    "id": str(db_conversation.id), # Return conversation ID
                    "content": ai_reply_content, # Return AI content
                    "user_message_id": user_msg_db.id, # Return DB ID of user message
                    "assistant_message_id": assistant_msg_db.id, # Return DB ID of assistant message
                    "used_backup": used_backup,
                    # Check if the conversation_id sent by the frontend was null or different from the new one
                    "new_conversation_id": str(conversation_id) if data.get('conversation_id') is None else None # Indicate if it was a new conversation
                })
            except SQLAlchemyError as e:
                 logger.error(f"Database commit error after getting AI reply: {e}", exc_info=True)
                 db.session.rollback()
                 # Return AI reply and error, but indicate DB save failed
                 return jsonify({
                     "content": ai_reply_content, # Still return the reply
                     "user_message_id": user_msg_db.id, # Return user message ID (was flushed)
                     "assistant_message_id": None, # Couldn't save assistant message, no ID
                     "used_backup": used_backup,
                     "new_conversation_id": None,
                     "error": f"تم توليد الرد ولكن حدث خطأ أثناء حفظه في قاعدة البيانات: {e}"
                     }), 500 # Indicate a partial failure

        else:
            # This branch should ideally not be reached due to offline fallback,
            # but handle it as a general failure.
            logger.error("Failed to generate any response (AI or offline).")
            db.session.rollback() # Rollback adding the user message if no reply was generated/saved
            return jsonify({"error": error_message or "فشل توليد استجابة"}), 500

    except Exception as e:
        logger.error(f"Critical error in /api/chat endpoint: {e}", exc_info=True)
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
        # logger.info("Fetching conversation list...") # Too noisy
        # Select only necessary fields for list view, ordered by last updated
        stmt = select(Conversation.id, Conversation.title, Conversation.updated_at).order_by(desc(Conversation.updated_at))
        conversations = db.session.execute(stmt).all() # Fetch rows

        conversations_list = [
            {
                "id": str(conv.id),
                "title": conv.title,
                "updated_at": conv.updated_at.isoformat()
            }
            for conv in conversations
        ]
        # logger.info(f"Retrieved {len(conversations_list)} conversations.") # Too noisy
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
    try:
        logger.info(f"Fetching conversation details for ID: {conversation_id}")
        # Use joinedload to fetch messages efficiently, ordered by created_at (as defined in relationship)
        stmt = select(Conversation).filter_by(id=conversation_id).options(db.joinedload(Conversation.messages))
        conversation = db.session.execute(stmt).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Conversation not found for ID: {conversation_id}")
            return jsonify({"error": "المحادثة المطلوبة غير موجودة"}), 404

        logger.info(f"Conversation found: '{conversation.title}', returning details.")
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
        # Use select to find the conversation first
        stmt = select(Conversation).filter_by(id=conversation_id)
        conversation = db.session.execute(stmt).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Attempted to delete non-existent conversation: {conversation_id}")
            return jsonify({"error": "المحادثة المطلوب حذفها غير موجودة"}), 404

        # Delete the conversation (messages and votes will be cascade deleted)
        db.session.delete(conversation)
        db.session.commit()
        logger.info(f"Successfully deleted conversation: {conversation_id}")
        return jsonify({"success": True, "message": "تم حذف المحادثة وجميع رسائلها بنجاح"})

    except SQLAlchemyError as e:
        logger.error(f"Database error deleting conversation {conversation_id}: {e}", exc_info=True)
        db.session.rollback()
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

        if not new_title:
            logger.warning(f"Empty title received for conversation {conversation_id}")
            return jsonify({"error": "عنوان المحادثة مطلوب"}), 400
        if len(new_title) > 100:
            logger.warning(f"Title too long for conversation {conversation_id}: '{new_title}'")
            return jsonify({"error": "عنوان المحادثة يجب ألا يتجاوز 100 حرف"}), 400

        logger.info(f"Attempting to update title for conversation {conversation_id} to '{new_title}'")
        # Use update statement
        stmt = update(Conversation)\
               .where(Conversation.id == conversation_id)\
               .values(title=new_title, updated_at=datetime.now(timezone.utc))\
               .returning(Conversation.id) # Return ID to confirm update occurred

        result = db.session.execute(stmt)
        updated_id = result.scalar_one_or_none()

        if updated_id:
            db.session.commit()
            logger.info(f"Successfully updated title for conversation: {conversation_id}")
            return jsonify({"success": True, "message": "تم تحديث عنوان المحادثة بنجاح"})
        else:
            # Check if conversation exists to return 404 if not found
            exists_stmt = select(Conversation.id).filter_by(id=conversation_id)
            exists = db.session.execute(exists_stmt).scalar_one_or_none()
            if not exists:
                 logger.warning(f"Attempted to update title for non-existent conversation: {conversation_id}")
                 return jsonify({"error": "المحادثة المطلوب تحديثها غير موجودة"}), 404
            else:
                 logger.error(f"Failed to update title for conversation {conversation_id}, but it exists. No rows updated.")
                 db.session.rollback() # Rollback in case of unexpected state
                 return jsonify({"error": "فشل تحديث العنوان لسبب غير معروف."}), 500 # Should not happen

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

        # --- Get Conversation and Messages ---
        # Load conversation and messages, we need the history *before* the last AI message
        # Use joinedload to fetch messages efficiently, ordered by created_at (as defined in relationship)
        stmt = select(Conversation).filter_by(id=conversation_id).options(db.joinedload(Conversation.messages))
        conversation = db.session.execute(stmt).scalar_one_or_none()

        if not conversation:
            logger.warning(f"Conversation not found for regeneration: {conversation_id}")
            return jsonify({"error": "المحادثة المطلوبة لإعادة التوليد غير موجودة"}), 404

        # Get messages, ordered by created_at (already defined in relationship)
        messages = list(conversation.messages) # Make a list copy

        if not messages:
            logger.warning(f"No messages found for regeneration in conversation {conversation_id}.")
            return jsonify({"error": "لا توجد رسائل في المحادثة لإعادة التوليد"}), 400

        # --- Find and prepare history excluding the last AI message ---
        last_message = messages[-1]
        if last_message.role != 'assistant':
            logger.warning(f"Last message in conv {conversation_id} (ID: {last_message.id}) is not from assistant ({last_message.role}). Cannot regenerate.")
            return jsonify({"error": "آخر رسالة ليست من المساعد، لا يمكن إعادة التوليد."}), 400

        # The history for the API call should exclude the last AI message
        # Convert message objects to the required dict format {role, content}
        api_history = [{"role": msg.role, "content": msg.content} for msg in messages[:-1]] # Exclude the last message

        # Ensure there's at least one message left and the last one is user
        if not api_history or api_history[-1]['role'] != 'user':
            logger.warning(f"No suitable history left after removing assistant message in conv {conversation_id}. Cannot regenerate.")
             # Rollback deletion of the last message if we had already started a transaction
             # (though in this structure, deletion happens after successful API call)
            return jsonify({"error": "لا توجد رسائل متبقية لإرسالها بعد حذف رد المساعد (آخر رسالة للمستخدم غير موجودة)."}), 400


        # --- Call APIs ---
        ai_reply_content = None
        error_message = None
        used_backup = False
        api_source = "N/A"

        # 1. Attempt OpenRouter
        if OPENROUTER_API_KEY:
            api_source = "OpenRouter (Regen)"
            try:
                logger.debug(f"Regen: Calling OpenRouter with model: {model}, history size: {len(api_history)}")
                openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
                headers = { "Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": APP_URL, "X-Title": APP_TITLE }
                payload = { "model": model, "messages": api_history, "temperature": temperature, "max_tokens": max_tokens }
                response = requests.post(url=openrouter_url, headers=headers, json=payload, timeout=60)
                response.raise_for_status()
                api_response = response.json()
                if api_response.get('choices') and api_response['choices'][0].get('message'):
                    ai_reply_content = api_response['choices'][0]['message'].get('content', '').strip()
                    if ai_reply_content: logger.info(f"Regen: Received reply from OpenRouter ({model}).")
                    if 'usage' in api_response: logger.info(f"Regen: OpenRouter usage: {api_response['usage']}")
                else:
                     logger.error(f"Regen: OpenRouter response structure invalid: {api_response}")
                     error_message = "استجابة غير متوقعة من OpenRouter أثناء إعادة التوليد"
            except requests.exceptions.Timeout:
                logger.error("Regen: OpenRouter API request timed out.")
                error_message = "مهلة OpenRouter أثناء إعادة التوليد"
            except requests.exceptions.HTTPError as e:
                error_body = e.response.text
                logger.error(f"Regen: OpenRouter API HTTP error ({e.response.status_code}): {error_body}")
                try: error_json = e.response.json(); error_details = error_json.get("error", {}).get("message", error_body)
                except json.JSONDecodeError: error_details = error_body[:200]
                error_message = f"خطأ HTTP من OpenRouter أثناء إعادة التوليد: {error_details}"
            except requests.exceptions.RequestException as e:
                logger.error(f"Regen: Error calling OpenRouter: {e}", exc_info=True)
                error_message = f"خطأ في الاتصال بـ OpenRouter أثناء إعادة التوليد: {e}"
            except Exception as e:
                logger.error(f"Regen: Unexpected error processing OpenRouter response: {e}", exc_info=True)
                error_message = f"خطأ غير متوقع في معالجة استجابة OpenRouter أثناء إعادة التوليد: {e}"


        # 2. Attempt Gemini as backup
        if not ai_reply_content and GEMINI_API_KEY:
            api_source = "Gemini (Backup Regen)"
            logger.info("Regen: OpenRouter failed. Trying Gemini backup...")
            # Pass the prepared history list to Gemini
            ai_reply_content, backup_error = call_gemini_api(api_history, temperature, max_tokens)
            if ai_reply_content:
                used_backup = True
                error_message = None # Clear previous error
                logger.info("Regen: Received reply from Gemini (backup).")
            else:
                 logger.error(f"Regen: Gemini backup also failed: {backup_error}")
                 error_message = error_message or f"فشل إعادة التوليد بالنموذج الاحتياطي: {backup_error}"

        # 3. If both failed, use offline fallback (less likely for regen, but possible)
        if not ai_reply_content:
            api_source = "Offline Fallback (Regen)"
            logger.warning("Regen: Both APIs failed. Falling back to offline responses.")
            # For regeneration, matching a predefined response might not make sense based on the *last user message* in the history.
            # A better offline fallback for regen might be a generic "Regeneration failed" message.
            ai_reply_content = None # Ensure no content from offline logic
            error_message = error_message or "فشل إعادة توليد الرد من جميع المصادر."


        # --- Save the new reply or rollback ---
        if ai_reply_content:
            logger.debug(f"Regen: Deleting old assistant message (ID: {last_message.id}) and adding new one (from {api_source}) for conv {conversation_id}")
            # Start a transaction
            try:
                # Delete the old message first
                db.session.delete(last_message)
                db.session.flush() # Ensure delete is staged

                # Add the new message
                new_assistant_msg = Message( # Create new message object
                     conversation_id=conversation.id, # Use conversation object
                     role='assistant',
                     content=ai_reply_content,
                     created_at=datetime.now(timezone.utc) # Use server time
                )
                db.session.add(new_assistant_msg) # add to session
                db.session.flush() # Get the ID of the new message

                # Update conversation's updated_at timestamp
                conversation.updated_at = datetime.now(timezone.utc)

                db.session.commit() # Commit the transaction
                logger.info(f"Regen: Successfully committed regenerated message (ID: {new_assistant_msg.id}) for conv {conversation_id}")

                return jsonify({
                    "content": ai_reply_content,
                    "new_message_id": new_assistant_msg.id, # Return the new message ID
                    "used_backup": used_backup,
                    "id": str(conversation.id) # Return conversation ID
                })
            except SQLAlchemyError as e:
                 logger.error(f"Regen: Database commit error during delete/add: {e}", exc_info=True)
                 db.session.rollback() # Rollback the entire transaction (delete and add)
                 return jsonify({"error": f"حدث خطأ أثناء حفظ الرد المُعاد توليده في قاعدة البيانات: {e}"}), 500
        else:
            # Regeneration failed before database commit
            logger.warning(f"Regen: Failed to generate new reply for conv {conversation_id}. No DB changes made.")
            # No rollback needed here as the delete/add transaction was not started/failed
            return jsonify({"error": error_message or "فشل إعادة توليد الاستجابة"}), 500

    except Exception as e:
        logger.error(f"Critical error in /api/regenerate endpoint: {e}", exc_info=True)
        try:
            db.session.rollback() # Ensure rollback for any open transaction
        except Exception as rollback_err:
             logger.error(f"Error during rollback after critical regenerate error: {rollback_err}", exc_info=True)
        return jsonify({"error": f"خطأ داخلي خطير أثناء إعادة التوليد: {e}"}), 500

# --- New API endpoint for voting ---
@app.route('/api/vote', methods=['POST'])
def receive_vote():
    """API route to receive user votes (like/dislike) for messages."""
    try:
        data = request.json
        if not data:
            logger.warning("Received empty JSON payload for /api/vote")
            return jsonify({"error": "الطلب غير صالح (بيانات فارغة)"}), 400

        message_id = data.get('message_id')
        vote_type = data.get('vote_type') # Expected: 'like' or 'dislike'

        if message_id is None or not isinstance(message_id, int): # Check if message_id is an integer
            logger.warning(f"Invalid message_id received for /api/vote: {message_id}")
            return jsonify({"error": "معرف الرسالة غير صالح"}), 400

        if vote_type not in ['like', 'dislike']:
            logger.warning(f"Invalid vote_type received for /api/vote: {vote_type}. Expected 'like' or 'dislike'.")
            return jsonify({"error": "نوع التصويت غير صالح"}), 400

        logger.info(f"Received vote '{vote_type}' for message ID: {message_id}")

        # Verify the message_id exists and get its conversation_id
        stmt_msg = select(Message.id, Message.conversation_id).filter_by(id=message_id).limit(1)
        message_info = db.session.execute(stmt_msg).fetchone() # Fetch just one row as a tuple

        if not message_info:
            logger.warning(f"Vote received for non-existent message ID: {message_id}")
            return jsonify({"error": "الرسالة غير موجودة"}), 404

        # In a real app, you'd check if this user has already voted on this message.
        # Since user sessions/auth aren't implemented, we'll allow multiple votes for now,
        # but ideally, you'd add a user_id column to MessageVote and a UniqueConstraint.

        # Create a new vote record
        new_vote = MessageVote(
            message_id=message_id,
            conversation_id=message_info.conversation_id, # Link vote to conversation too
            vote_type=vote_type,
            created_at=datetime.now(timezone.utc) # Use server time
        )

        db.session.add(new_vote)

        try:
            db.session.commit()
            logger.info(f"Vote '{vote_type}' recorded for message ID {message_id}.")
            return jsonify({"success": True, "message": "تم تسجيل التصويت بنجاح"})
        except SQLAlchemyError as e:
            logger.error(f"Database error saving vote for message {message_id}: {e}", exc_info=True)
            db.session.rollback()
            # Check if it's a constraint error (if a unique constraint based on user_id was added)
            # if "UniqueViolation" in str(e): # Example check if user_id constraint exists
            #      return jsonify({"error": "لقد قمت بالتصويت على هذه الرسالة من قبل."}), 409 # Conflict
            # else:
            return jsonify({"error": f"خطأ قاعدة بيانات أثناء تسجيل التصويت: {e}"}), 500

    except Exception as e:
        logger.error(f"Critical error in /api/vote endpoint: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception as rollback_err:
             logger.error(f"Error during rollback after critical vote error: {rollback_err}", exc_info=True)
        return jsonify({"error": f"حدث خطأ داخلي خطير في الخادم أثناء تسجيل التصويت: {e}"}), 500


# --- معالجات الأخطاء العامة ---
@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        logger.warning(f"404 Not Found for API route: {request.path} from {request.remote_addr}")
        return jsonify({"error": "نقطة النهاية المطلوبة غير موجودة."}), 404
    logger.warning(f"404 Not Found for page: {request.path} من {request.remote_addr}") # Added Arabic translation
    # Ensure you have an error.html template
    try:
        # Assuming you have a basic error.html template
        return render_template('error.html', error_code=404, error_message="الصفحة غير موجودة"), 404
    except Exception:
         # Fallback if error.html template doesn't exist
         return "404 Not Found", 404


@app.errorhandler(500)
def internal_error(error):
    # Get the original exception if available
    original_exception = getattr(error, 'original_exception', error)
    logger.error(f"500 Internal Server Error for {request.path} from {request.remote_addr}: {original_exception}", exc_info=True)

    # Attempt rollback for any open database sessions associated with this request
    # In Flask-SQLAlchemy, db.session is often request-scoped.
    try:
        db.session.rollback()
        logger.info("Database session rolled back after 500 error.")
    except Exception as e:
         logger.error(f"Error during rollback after 500 error: {e}", exc_info=True)

    if request.path.startswith('/api/'):
        # Avoid exposing detailed internal errors in production API responses
        return jsonify({"error": "حدث خطأ داخلي غير متوقع في الخادم."}), 500
    # Ensure you have an error.html template
    try:
        # Assuming you have a basic error.html template
        return render_template('error.html', error_code=500, error_message="حدث خطأ داخلي في الخادم"), 500
    except Exception:
        return "500 Internal Server Error", 500


@app.errorhandler(Exception)
def handle_exception(e):
     # Log the unhandled exception
     logger.error(f"Unhandled Exception for {request.path} from {request.remote_addr}: {e}", exc_info=True) # Added remote_addr

     # Attempt rollback
     try:
         db.session.rollback()
     except Exception as rollback_err:
         logger.error(f"Error during rollback after unhandled exception: {rollback_err}", exc_info=True)

     # Return appropriate response based on request type
     if request.path.startswith('/api/'):
         # Avoid exposing detailed internal errors in production API responses
         return jsonify({"error": "حدث خطأ غير متوقع في الخادم."}), 500 # Generic message
     else:
         # Ensure you have an error.html template
         try:
             # Assuming you have a basic error.html template
             return render_template('error.html', error_code=500, error_message="حدث خطأ غير متوقع."), 500
         except Exception:
             return "An unexpected error occurred", 500


# --- Database Initialization ---
# This should create tables if they don't exist
def initialize_database():
    with app.app_context():
        logger.info("Application context acquired. Attempting to create database tables...")
        try:
            # Ensure all models are imported so SQLAlchemy knows about them
            # (Conversation, Message, MessageVote)
            db.create_all()
            logger.info("Database tables checked/created successfully.")
        except SQLAlchemyError as e:
            db_uri_safe = str(app.config.get("SQLALCHEMY_DATABASE_URI", "Unknown DB")).split("@")[-1] # Get part after @
            logger.error(f"FATAL: SQLAlchemyError occurred during db.create_all() for DB: ...@{db_uri_safe}. Error: {e}", exc_info=False)
            # Optionally, exit the application if DB initialization fails
            # import sys
            # sys.exit(f"Database initialization failed: {e}")
        except Exception as e:
            logger.error(f"FATAL: An unexpected error occurred during db.create_all(): {e}", exc_info=True)
            # import sys
            # sys.exit(f"Unexpected database initialization error: {e}")

# Call the initialization function
initialize_database()
logger.info("Database initialization routine finished.")

# --- Request teardown to ensure session is closed ---
@app.teardown_request
def teardown_request(exception):
    # In Flask-SQLAlchemy, db.session is typically scoped such that it's automatically
    # removed at the end of the request (or after a cli command/app context pop).
    # While an explicit rollback in error handlers is good practice,
    # relying on F-SQLAlchemy's default remove is usually sufficient for basic apps.
    pass


# --- Entry point for Gunicorn/WSGI Server ---
if __name__ != '__main__':
    # Configure app logging to use Gunicorn's logger
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    logger.info("Application started via WSGI server (like Gunicorn). Logging handlers configured.")
else:
     # This block is for local development using `python app.py`
     logger.info("Starting Flask development server (use Gunicorn/WSGI for production)...")
     port = int(os.environ.get("PORT", 5001))
     app.run(host='0.0.0.0', port=port, debug=True) # Use debug=False for production

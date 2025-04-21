import os
import logging
import requests
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from translation_service import TranslationService

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- Base Class for SQLAlchemy models ---
class Base(DeclarativeBase):
    pass

# --- Initialize Flask and SQLAlchemy ---
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "yasmin-gpt-secret-key")

# Configure the SQLAlchemy database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize SQLAlchemy with app
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# --- Get API keys from environment variables ---
# Primary API: OpenRouter
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
# Backup API: Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Other app configurations
APP_URL = os.environ.get("APP_URL", "http://localhost:5000")
APP_TITLE = "Yasmin GPT Chat"  # App name for OpenRouter

# --- Yasmin's offline responses (Backend Fallback) ---
# Note: Frontend now handles immediate offline messages if navigator.onLine is false.
# This backend fallback is for cases where an API call is attempted but fails mid-request.
offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا ياسمين. للأسف، لا يوجد اتصال بالإنترنت حاليًا.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا ياسمين. أعتذر، خدمة الإنترنت غير متوفرة حاليًا.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت."
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت."


# Function to call Gemini API as a backup
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
             role = "user" if msg["role"] == "user" else "model" # Gemini uses 'user'/'model'
             gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

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


# --- Initialize translation service ---
translation_service = TranslationService()

# --- Route for main page ---
@app.route('/')
def index():
    # Pass app_title to the template
    return render_template('index.html', app_title=APP_TITLE)
    
# --- Route for translation page ---
@app.route('/translation')
def translation_page():
    return render_template('translation.html', app_title=f"{APP_TITLE} | خدمة الترجمة")

# --- API route for chat ---
@app.route('/api/chat', methods=['POST'])
def chat():
    # Import models inside the function to avoid circular imports
    from models import Conversation, Message

    try:
        data = request.json
        # Frontend sends the full current history array including the user's latest message
        messages_for_api = data.get('history', [])
        user_message = messages_for_api[-1]['content'] if messages_for_api else ""

        model = data.get('model', 'mistralai/mistral-7b-instruct')
        conversation_id = data.get('conversation_id') # This is null for a brand new chat
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', 512)

        if not user_message:
             logger.warning("Received empty user message in /api/chat history.")
             return jsonify({"error": "الرسالة فارغة"}), 400

        # Get or create conversation in database
        db_conversation = None
        if conversation_id:
             db_conversation = db.session.execute(db.select(Conversation).filter_by(id=conversation_id)).scalar_one_or_none()

        if not db_conversation:
            # Create new conversation
            conversation_id = str(uuid.uuid4())
            # Set initial title from the first user message
            initial_title = user_message.split('\n')[0][:50]
            db_conversation = Conversation(id=conversation_id, title=initial_title or "محادثة جديدة")
            db.session.add(db_conversation)
            # Don't commit yet

        # Add user message to database if it's the last one in the history and not already there
        # This handles the case where frontend sends history including the new message
        last_db_message = db.session.execute(
             db.select(Message)
             .filter_by(conversation_id=db_conversation.id)
             .order_by(Message.created_at.desc())
             .limit(1)
        ).scalar_one_or_none()

        # Basic check to avoid duplicating the *same* last user message on retries
        if not last_db_message or not (last_db_message.role == 'user' and last_db_message.content == user_message and (datetime.utcnow() - last_db_message.created_at).total_seconds() < 5): # Add a time check
             logger.debug(f"Adding user message to DB for conversation {db_conversation.id}")
             db_conversation.add_message('user', user_message)
             # db.session.commit() # Commit after adding assistant message


        ai_reply = None
        error_message = None
        used_backup = False

        # First try OpenRouter API
        if OPENROUTER_API_KEY:
            try:
                logger.debug(f"Sending request to OpenRouter with model: {model}, history size: {len(messages_for_api)}")
                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "HTTP-Referer": APP_URL,  # Required by OpenRouter
                        "X-Title": APP_TITLE,     # Optional but recommended
                    },
                    json={
                        "model": model,
                        "messages": messages_for_api, # Use the full history including the last user message
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                     timeout=45 # Increased timeout slightly
                )

                response.raise_for_status()

                api_response = response.json()

                if 'choices' in api_response and len(api_response['choices']) > 0 and 'message' in api_response['choices'][0]:
                     ai_reply = api_response['choices'][0]['message']['content']
                     # Log costs if available (OpenRouter specific)
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


        # If OpenRouter failed or not available, try Gemini API as backup
        if not ai_reply and GEMINI_API_KEY:
            logger.info("Trying Gemini API as backup")
            ai_reply, backup_error = call_gemini_api(messages_for_api, temperature, max_tokens)
            if ai_reply:
                used_backup = True
                error_message = None # Clear previous OpenRouter error if backup succeeds
            else:
                error_message = error_message or f"فشل محاولة استخدام النموذج الاحتياطي: {backup_error}" # Keep OpenRouter error if no backup error

        # If still no reply after both APIs, use backend offline responses
        if not ai_reply:
             logger.warning("API calls failed, falling back to backend offline responses.")
             # This backend fallback is mostly for cases where an API call started but failed later.
             # Frontend handles immediate offline based on navigator.onLine
             matched_offline = False
             user_msg_lower = user_message.lower()
             for key in offline_responses:
                 if key.lower() in user_msg_lower: # Simple 'in' check
                     ai_reply = offline_responses[key]
                     matched_offline = True
                     break

             if not matched_offline:
                 ai_reply = default_offline_response

        # Add the AI response to the database
        if ai_reply:
            db_conversation.add_message('assistant', ai_reply)
            db.session.commit()

            # Return new conversation_id for brand new conversations
            return jsonify({
                "id": conversation_id,
                "content": ai_reply,
                "used_backup": used_backup
            })
        else:
            # Return error if no response was generated
            return jsonify({
                "error": error_message or "فشل توليد استجابة"
            }), 500

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        return jsonify({"error": f"خطأ غير متوقع: {str(e)}"}), 500

# --- API route for conversation history ---
@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    # Import models inside the function to avoid circular imports
    from models import Conversation

    try:
        # Get all conversations ordered by most recently updated
        conversations = db.session.execute(
            db.select(Conversation).order_by(Conversation.updated_at.desc())
        ).scalars().all()

        # Convert to list of dicts (simplified, without messages)
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
        return jsonify({"error": f"خطأ في استرجاع المحادثات: {str(e)}"}), 500

# --- API route for a specific conversation ---
@app.route('/api/conversations/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    # Import models inside the function to avoid circular imports
    from models import Conversation

    try:
        # Get the conversation
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        # Convert to dict with messages
        return jsonify(conversation.to_dict())
    except Exception as e:
        logger.error(f"Error getting conversation {conversation_id}: {e}", exc_info=True)
        return jsonify({"error": f"خطأ في استرجاع المحادثة: {str(e)}"}), 500

# --- API route to delete a conversation ---
@app.route('/api/conversations/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    # Import models inside the function to avoid circular imports
    from models import Conversation

    try:
        # Find the conversation
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        # Delete the conversation (this should cascade to messages)
        db.session.delete(conversation)
        db.session.commit()

        return jsonify({"success": True, "message": "تم حذف المحادثة بنجاح"})
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {e}", exc_info=True)
        return jsonify({"error": f"خطأ في حذف المحادثة: {str(e)}"}), 500

# --- API route to update a conversation's title ---
@app.route('/api/conversations/<conversation_id>/title', methods=['PUT'])
def update_conversation_title(conversation_id):
    # Import models inside the function to avoid circular imports
    from models import Conversation

    try:
        data = request.json
        new_title = data.get('title')

        if not new_title:
            return jsonify({"error": "عنوان المحادثة مطلوب"}), 400

        # Find the conversation
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        # Update the title
        conversation.title = new_title
        db.session.commit()

        return jsonify({"success": True, "message": "تم تحديث عنوان المحادثة"})
    except Exception as e:
        logger.error(f"Error updating conversation title {conversation_id}: {e}", exc_info=True)
        return jsonify({"error": f"خطأ في تحديث عنوان المحادثة: {str(e)}"}), 500

# --- API routes for translation service ---
@app.route('/api/translation/languages', methods=['GET'])
def get_translation_languages():
    """الحصول على قائمة اللغات المدعومة للترجمة"""
    try:
        languages = translation_service.get_supported_languages()
        return jsonify(languages)
    except Exception as e:
        logger.error(f"Error getting supported languages: {e}", exc_info=True)
        return jsonify({"error": f"خطأ في استرجاع اللغات المدعومة: {str(e)}"}), 500

@app.route('/api/translation/translate', methods=['POST'])
def translate_text():
    """ترجمة النص المقدم إلى اللغة المطلوبة"""
    try:
        data = request.json
        text = data.get('text', '')
        source_lang = data.get('source_lang', 'auto')
        target_lang = data.get('target_lang', 'ar')
        
        if not text:
            return jsonify({"error": "النص مطلوب للترجمة"}), 400
            
        result = translation_service.translate_text(text, source_lang, target_lang)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error translating text: {e}", exc_info=True)
        return jsonify({"error": f"خطأ في ترجمة النص: {str(e)}"}), 500

@app.route('/api/translation/detect', methods=['POST'])
def detect_language():
    """الكشف عن لغة النص المقدم"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "النص مطلوب للكشف عن اللغة"}), 400
            
        detected_lang = translation_service.detect_language(text)
        return jsonify({"detected_language": detected_lang})
    except Exception as e:
        logger.error(f"Error detecting language: {e}", exc_info=True)
        return jsonify({"error": f"خطأ في الكشف عن اللغة: {str(e)}"}), 500

# --- API route for regenerating the last AI response ---
@app.route('/api/regenerate', methods=['POST'])
def regenerate_response():
    # Import models inside the function to avoid circular imports
    from models import Conversation, Message

    try:
        data = request.json
        conversation_id = data.get('conversation_id')
        model = data.get('model', 'mistralai/mistral-7b-instruct')
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', 512)

        if not conversation_id:
            return jsonify({"error": "معرف المحادثة مطلوب"}), 400

        # Get conversation from database
        conversation = db.session.execute(
            db.select(Conversation).filter_by(id=conversation_id)
        ).scalar_one_or_none()

        if not conversation:
            return jsonify({"error": "المحادثة غير موجودة"}), 404

        # Get messages ordered by created_at
        messages = db.session.execute(
            db.select(Message)
            .filter_by(conversation_id=conversation_id)
            .order_by(Message.created_at)
        ).scalars().all()

        if not messages:
            return jsonify({"error": "لا توجد رسائل في المحادثة"}), 400

        # Format messages for the API
        messages_for_api = [{"role": msg.role, "content": msg.content} for msg in messages]

        # Find the last AI message and remove it from the messages list
        # We'll only regenerate the last AI message if it exists
        if messages[-1].role == 'assistant':
            # Remove the last message from the database
            db.session.delete(messages[-1])
            # Also remove it from our API message list
            messages_for_api = messages_for_api[:-1]
        
        # If messages list is now empty, return error
        if not messages_for_api:
            db.session.rollback() # Undo deletion
            return jsonify({"error": "لا توجد رسائل مستخدم لإعادة التوليد"}), 400

        # Now make a new API call to regenerate the response
        ai_reply = None
        error_message = None
        used_backup = False

        # Try OpenRouter API first, same as in chat endpoint
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
                else:
                    logger.error(f"OpenRouter regeneration response missing choices/message: {api_response}")
                    error_message = "استجابة غير متوقعة من OpenRouter أثناء إعادة التوليد"

            except Exception as e:
                logger.error(f"Error regenerating response with OpenRouter: {e}", exc_info=True)
                error_message = f"خطأ أثناء إعادة التوليد: {str(e)}"

        # Try Gemini API as backup if OpenRouter failed
        if not ai_reply and GEMINI_API_KEY:
            logger.info("Trying Gemini API as backup for regeneration")
            ai_reply, backup_error = call_gemini_api(messages_for_api, temperature, max_tokens)
            if ai_reply:
                used_backup = True
                error_message = None # Clear previous error
            else:
                error_message = error_message or f"فشل محاولة استخدام النموذج الاحتياطي: {backup_error}"

        # If still no reply after both APIs, use backend offline responses
        if not ai_reply:
            logger.warning("API calls failed during regeneration, falling back to offline responses.")
            user_msg_lower = messages_for_api[-1]['content'].lower() if messages_for_api else ""
            
            matched_offline = False
            for key in offline_responses:
                if key.lower() in user_msg_lower:
                    ai_reply = offline_responses[key]
                    matched_offline = True
                    break

            if not matched_offline:
                ai_reply = default_offline_response

        # Add regenerated AI response to database
        if ai_reply:
            conversation.add_message('assistant', ai_reply)
            db.session.commit()

            return jsonify({
                "content": ai_reply,
                "used_backup": used_backup
            })
        else:
            # Something went wrong, rollback the deletion of the last message
            db.session.rollback() 
            return jsonify({
                "error": error_message or "فشل إعادة توليد الاستجابة"
            }), 500

    except Exception as e:
        logger.error(f"Error in regenerate endpoint: {e}", exc_info=True)
        # Make sure to rollback any failed operations
        db.session.rollback()
        return jsonify({"error": f"خطأ غير متوقع أثناء إعادة التوليد: {str(e)}"}), 500

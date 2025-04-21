import os
import logging
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    jsonify,
    session,
    request # Keep request if needed for other parts, but GET usually doesn't need its body
)
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session # For server-side sessions
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv() # Load environment variables from .env file

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Security & Session Configuration ---
# IMPORTANT: Keep SECRET_KEY truly secret in production! Load from env.
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'default-insecure-secret-key')
# Configure server-side sessions (avoids large cookies, more secure)
app.config['SESSION_TYPE'] = 'filesystem' # Or 'redis', 'sqlalchemy', etc.
app.config['SESSION_PERMANENT'] = True # Make sessions persistent
app.config['SESSION_USE_SIGNER'] = True # Encrypt session cookie
# Consider setting SESSION_COOKIE_SECURE=True if using HTTPS
# app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
# app.config['SESSION_COOKIE_HTTPONLY'] = True
# app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' # Or 'Strict'

Session(app)

# --- Database Configuration ---
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    logger.error("DATABASE_URL environment variable not set.")
    # Handle this more gracefully depending on requirements (e.g., exit, use sqlite fallback)
    # For demonstration, we'll let it raise an error later if needed.
else:
    # Handle 'postgres://' prefix if Heroku/Render provides it for SQLAlchemy < 1.4
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Disable modification tracking overhead
app.config['SQLALCHEMY_ECHO'] = False # Set to True for debugging DB queries

db = SQLAlchemy(app)

# --- Database Models ---
class Message(db.Model):
    __tablename__ = 'messages' # Explicit table name is good practice
    id = db.Column(db.Integer, primary_key=True)
    # Use session_id for anonymous tracking or user_id if you have user accounts
    session_id = db.Column(db.String(80), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False) # 'user', 'assistant', 'system'
    content = db.Column(db.Text, nullable=False)
    model_used = db.Column(db.String(100), nullable=True) # Track which model responded
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<Message {self.id} by {self.role} in session {self.session_id}>'

    def to_dict(self):
        """Serializes the Message object to a dictionary."""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'role': self.role,
            'content': self.content,
            'model_used': self.model_used,
            # Format timestamp for consistency (ISO 8601 is common)
            'timestamp': self.timestamp.isoformat() + 'Z' # Indicate UTC
        }

# --- Available Models (Example - could be loaded from config file) ---
# Ensure these match the IDs used by OpenRouter
AVAILABLE_MODELS = [
    {"id": "mistralai/mistral-7b-instruct-v0.2", "name": "Mistral 7B Instruct v0.2"},
    {"id": "google/gemma-7b-it", "name": "Google Gemma 7B"},
    {"id": "anthropic/claude-3-haiku-20240307", "name": "Claude 3 Haiku"},
    {"id": "meta-llama/llama-3-8b-instruct", "name": "LLaMA 3 8B Instruct"},
    {"id": "openai/gpt-3.5-turbo", "name": "GPT-3.5 Turbo"},
    # Add other models supported by your setup
]
# You might want to fetch this dynamically from OpenRouter if the list changes often,
# but caching it is generally a good idea.

# --- Helper Functions / Decorators ---
def ensure_session(f):
    """Decorator to ensure a session exists before proceeding."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'session_id' not in session:
            # Create a unique session ID if none exists
            # Using os.urandom is cryptographically secure
            session['session_id'] = os.urandom(24).hex()
            logger.info(f"New session created: {session['session_id']}")
        return f(*args, **kwargs)
    return decorated_function

# --- Routes (Focusing on GET) ---

@app.route('/')
@ensure_session # Ensure session exists when loading the main page
def index():
    """Serves the main chat interface HTML."""
    logger.info(f"Serving index.html for session: {session.get('session_id')}")
    # Pass initial data if needed, e.g., available models, user settings
    return render_template('index.html',
                           available_models=AVAILABLE_MODELS,
                           initial_dark_mode=session.get('dark_mode', False), # Example setting
                           initial_tts_enabled=session.get('tts_enabled', True)) # Example

@app.route('/api/history', methods=['GET'])
@ensure_session # Need session to retrieve history
def get_history():
    """Fetches the chat history for the current session."""
    session_id = session['session_id']
    logger.info(f"Fetching history for session: {session_id}")
    try:
        messages = db.session.execute(
            db.select(Message)
            .filter_by(session_id=session_id)
            .order_by(Message.timestamp.asc()) # Fetch in chronological order
        ).scalars().all()

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
    """Returns the list of available AI models."""
    logger.info("Fetching available models list.")
    return jsonify(AVAILABLE_MODELS)

@app.route('/api/settings', methods=['GET'])
@ensure_session
def get_settings():
    """Gets user-specific settings stored in the session."""
    session_id = session['session_id']
    logger.info(f"Fetching settings for session: {session_id}")
    settings = {
        'darkMode': session.get('dark_mode', False), # Default to False if not set
        'ttsEnabled': session.get('tts_enabled', True), # Default to True
        # Add other settings as needed
    }
    return jsonify(settings)

# --- POST Routes (Placeholders - Need actual implementation) ---
@app.route('/api/chat', methods=['POST'])
@ensure_session
def handle_chat():
    """Handles incoming user messages and gets response from AI."""
    # 1. Get user message and selected model from request JSON
    # 2. Validate input
    # 3. Save user message to DB
    # 4. Call OpenRouter (or Gemini fallback) using API keys from os.environ
    #    - Remember to include APP_URL in headers if required by OpenRouter ('HTTP-Referer')
    # 5. Handle API errors (rate limits, invalid key, model not found)
    # 6. Save AI response to DB
    # 7. Return AI response as JSON
    logger.warning("POST /api/chat endpoint not fully implemented.")
    # Replace with actual implementation
    return jsonify({"error": "Chat endpoint not implemented"}), 501

@app.route('/api/regenerate', methods=['POST'])
@ensure_session
def handle_regenerate():
    """Handles request to regenerate the last AI response."""
    # 1. Get context (previous messages) from DB for the session
    # 2. Remove the last AI message from the context (or mark it for replacement)
    # 3. Call OpenRouter/Gemini again with the context
    # 4. Handle API errors
    # 5. Update the last AI message in the DB (or add a new one)
    # 7. Return the new AI response as JSON
    logger.warning("POST /api/regenerate endpoint not fully implemented.")
    # Replace with actual implementation
    return jsonify({"error": "Regenerate endpoint not implemented"}), 501

@app.route('/api/settings', methods=['POST'])
@ensure_session
def update_settings():
    """Updates user-specific settings in the session."""
    session_id = session['session_id']
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    logger.info(f"Updating settings for session {session_id}: {data}")
    if 'darkMode' in data and isinstance(data['darkMode'], bool):
        session['dark_mode'] = data['darkMode']
    if 'ttsEnabled' in data and isinstance(data['ttsEnabled'], bool):
        session['tts_enabled'] = data['ttsEnabled']
    # Add other settings updates

    # Persist session changes immediately
    session.modified = True

    return jsonify({"success": True, "settings": get_settings().get_json()})


@app.route('/api/history', methods=['DELETE'])
@ensure_session
def delete_history():
    """Deletes all chat messages for the current session."""
    session_id = session['session_id']
    logger.info(f"Attempting to delete history for session: {session_id}")
    try:
        num_deleted = db.session.query(Message).filter_by(session_id=session_id).delete()
        db.session.commit()
        logger.info(f"Deleted {num_deleted} messages for session {session_id}")
        return jsonify({"success": True, "message": f"Deleted {num_deleted} messages."}), 200
    except SQLAlchemyError as e:
        db.session.rollback() # Rollback in case of error
        logger.error(f"Database error deleting history for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "Database error clearing chat history."}), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error deleting history for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred."}), 500


# --- Error Handlers ---
@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 Not Found: {request.path}")
    # API routes should return JSON
    if request.path.startswith('/api/'):
        return jsonify({"error": "Not Found"}), 404
    # Other routes can return a custom HTML page
    return render_template('404.html'), 404 # You'd need to create 404.html

@app.errorhandler(500)
def internal_error(error):
    # Log the actual error stack trace
    logger.error(f"500 Internal Server Error: {error}", exc_info=True)
    # Ensure database session is rolled back in case the error originated there
    try:
        db.session.rollback()
    except Exception as e:
        logger.error(f"Error during rollback after 500 error: {e}", exc_info=True)

    if request.path.startswith('/api/'):
        return jsonify({"error": "An internal server error occurred."}), 500
    return render_template('500.html'), 500 # You'd need to create 500.html

# --- Database Initialization ---
# Use Flask CLI or run once manually in production setup
# For development/Replit, this can run on startup
with app.app_context():
    logger.info("Application context pushed. Checking database...")
    if db_url: # Only attempt if DB URL is configured
        try:
            # This tries to connect and create tables if they don't exist
            db.create_all()
            logger.info("Database tables ensured.")
        except SQLAlchemyError as e:
             logger.error(f"Failed to connect to database or create tables: {e}", exc_info=True)
             # Decide how to handle this - maybe exit or disable DB features
        except Exception as e:
             logger.error(f"An unexpected error occurred during DB initialization: {e}", exc_info=True)
    else:
        logger.warning("Database URL not configured. Database features will be disabled.")

# --- Main Execution ---
if __name__ == '__main__':
    # Use environment variable for port, default to 5000
    port = int(os.environ.get("PORT", 5000))
    # Debug mode should be False in production! Load from env var.
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    logger.info(f"Starting Flask app on port {port} with debug mode: {debug_mode}")
    # Use host='0.0.0.0' to be accessible externally (like in Replit/Docker)
    # The development server is not recommended for production. Use Gunicorn/Waitress.
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

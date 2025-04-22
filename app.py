import os
import uuid
import logging
import requests
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import create_engine, select, update, delete, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from sqlalchemy.dialects.postgresql import UUID, TEXT
from flask import Flask, jsonify, request, Response
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
}
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
APP_URL = os.getenv("APP_URL", "http://localhost:5000")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Models
db = SQLAlchemy(app)

class Base(DeclarativeBase):
    pass

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(TEXT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    messages: Mapped[list["Message"]] = relationship(
        cascade="all, delete-orphan", order_by="Message.created_at"
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [msg.to_dict() for msg in self.messages],
        }

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(TEXT, nullable=False)
    content: Mapped[str] = mapped_column(TEXT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }

# Offline Responses
offline_responses = [
    "عذرًا، يبدو أنني غير متصل بالإنترنت. جرب مرة أخرى لاحقًا!",
    "الاتصال ضعيف، لكنني هنا! حاول مرة أخرى بعد قليل.",
    "أوه، انقطع الاتصال! سأعود قريبًا، تحقق من الاتصال وجرب مجددًا."
]

def generate_suggestions(messages):
    if not OPENROUTER_API_KEY:
        return []
    prompt = "Based on the following conversation, suggest 3 short follow-up questions or prompts in Arabic:\n" + \
             "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages[-3:]]) + \
             "\nProvide the suggestions as a JSON list."
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": "mistralai/mistral-7b-instruct", "messages": [{"role": "user", "content": prompt}]}
        )
        response.raise_for_status()
        suggestions = response.json()['choices'][0]['message']['content']
        return suggestions if isinstance(suggestions, list) else []
    except Exception as e:
        logger.error(f"Error generating suggestions: {e}")
        return []

@app.route("/api/conversations", methods=["GET"])
def get_conversations():
    try:
        conversations = db.session.execute(
            select(Conversation).order_by(Conversation.updated_at.desc())
        ).scalars().all()
        return jsonify([conv.to_dict() for conv in conversations])
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        return jsonify({"error": "فشل جلب المحادثات"}), 500

@app.route("/api/conversations", methods=["POST"])
def create_conversation():
    try:
        data = request.json
        title = data.get("title", "محادثة جديدة").strip()
        if not title:
            return jsonify({"error": "العنوان مطلوب"}), 400
        conversation = Conversation(title=title)
        db.session.add(conversation)
        db.session.commit()
        return jsonify(conversation.to_dict())
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        return jsonify({"error": "فشل إنشاء المحادثة"}), 500

@app.route("/api/conversations/<uuid:conversation_id>", methods=["PUT"])
def update_conversation(conversation_id):
    try:
        data = request.json
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"error": "العنوان مطلوب"}), 400
        stmt = update(Conversation).where(Conversation.id == conversation_id).values(title=title)
        result = db.session.execute(stmt)
        if result.rowcount == 0:
            return jsonify({"error": "المحادثة غير موجودة"}), 404
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error updating conversation: {e}")
        return jsonify({"error": "فشل تحديث المحادثة"}), 500

@app.route("/api/conversations/<uuid:conversation_id>", methods=["DELETE"])
def delete_conversation(conversation_id):
    try:
        stmt = delete(Conversation).where(Conversation.id == conversation_id)
        result = db.session.execute(stmt)
        if result.rowcount == 0:
            return jsonify({"error": "المحادثة غير موجودة"}), 404
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        return jsonify({"error": "فشل حذف المحادثة"}), 500

@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        conversation_id_str = data.get("conversation_id")
        conversation_id = uuid.UUID(conversation_id_str) if conversation_id_str else None
        history = data.get("history", [])
        if not history or not isinstance(history, list):
            return jsonify({"error": "السجل مطلوب ويجب أن يكون قائمة"}), 400

        # Validate or create conversation
        if conversation_id:
            db_conversation = db.session.get(Conversation, conversation_id)
            if not db_conversation:
                return jsonify({"error": "المحادثة غير موجودة"}), 404
        else:
            db_conversation = Conversation(title="محادثة جديدة")
            db.session.add(db_conversation)

        # Save user message
        user_message = history[-1]["content"].strip()
        if not user_message:
            return jsonify({"error": "الرسالة فارغة"}), 400
        db_message = Message(
            conversation_id=db_conversation.id, role="user", content=user_message
        )
        db.session.add(db_message)

        # Prepare messages for API
        messages_for_api = [
            {"role": msg["role"], "content": msg["content"]} for msg in history
        ]

        # Call OpenRouter API
        used_backup = False
        if not OPENROUTER_API_KEY:
            ai_reply = offline_responses[0]
            used_backup = True
        else:
            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                    json={"model": data.get("model", "mistralai/mixtral-8x7b-instruct"), "messages": messages_for_api}
                )
                response.raise_for_status()
                ai_reply = response.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"OpenRouter API error: {e}")
                ai_reply = offline_responses[0]
                used_backup = True

        # Save AI response
        ai_message = Message(
            conversation_id=db_conversation.id, role="assistant", content=ai_reply
        )
        db.session.add(ai_message)

        # Update conversation title if new
        if not conversation_id_str and len(history) == 1:
            prompt = f"قم بإنشاء عنوان قصير (بحد أقصى 50 حرفًا) باللغة العربية لهذه المحادثة بناءً على الرسالة: {user_message}"
            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "mistralai/mistral-7b-instruct", "messages": [{"role": "user", "content": prompt}]}
                )
                response.raise_for_status()
                new_title = response.json()["choices"][0]["message"]["content"][:50]
                db_conversation.title = new_title
            except Exception as e:
                logger.error(f"Error generating title: {e}")

        db.session.commit()

        return jsonify({
            "id": str(db_conversation.id),
            "content": ai_reply,
            "used_backup": used_backup,
            "new_conversation_id": str(db_conversation.id) if not conversation_id_str else None,
            "suggestions": generate_suggestions(messages_for_api)
        })
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({"error": "فشل معالجة الرسالة"}), 500

@app.route("/api/conversations/analytics", methods=["GET"])
def conversation_analytics():
    try:
        total_conversations = db.session.query(Conversation).count()
        total_messages = db.session.query(Message).count()
        messages_per_conversation = db.session.query(
            Conversation.id,
            func.count(Message.id).label('message_count')
        ).outerjoin(Message).group_by(Conversation.id).all()
        avg_messages = sum(count for _, count in messages_per_conversation) / max(total_conversations, 1)
        common_words = db.session.query(
            func.unnest(func.string_to_array(Conversation.title, ' ')).label('word')
        ).group_by('word').order_by(func.count().desc()).limit(5).all()
        return jsonify({
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "avg_messages_per_conversation": round(avg_messages, 2),
            "common_topics": [word[0] for word in common_words]
        })
    except Exception as e:
        logger.error(f"Error generating analytics: {e}")
        return jsonify({"error": "فشل تحليل البيانات"}), 500

if __name__ == "__main__":
    with app.app_context():
        Base.metadata.create_all(db.engine)
    app.run(debug=True, host="0.0.0.0", port=5000)

from app import db
from datetime import datetime


# Database models for conversations
class Conversation(db.Model):
    id = db.Column(db.String(36), primary_key=True)  # UUID format
    title = db.Column(db.String(100), nullable=False, default="محادثة جديدة")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime,
                           default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    # One-to-many relationship with Message
    # cascade="all, delete-orphan" ensures messages are deleted when conversation is deleted
    messages = db.relationship(
        'Message',
        backref='conversation',
        lazy='dynamic',
        cascade="all, delete-orphan"
    )  # Use lazy='dynamic' for better filtering/ordering queries

    def to_dict(self):
        return {
            "id":
            self.id,
            "title":
            self.title,
            "created_at":
            self.created_at.isoformat() if self.created_at else None,
            "updated_at":
            self.updated_at.isoformat() if self.updated_at else None,
            # Order messages by created_at when converting to dict
            # Using .all() with order_by() on the dynamic relationship
            "messages": [
                msg.to_dict()
                for msg in self.messages.order_by(Message.created_at).all()
            ]
        }

    def add_message(self, role, content):
        """Helper method to add a message to this conversation"""
        message = Message(role=role, content=content, conversation_id=self.id)
        db.session.add(message)
        self.updated_at = datetime.utcnow()  # Update conversation timestamp
        return message


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    conversation_id = db.Column(db.String(36),
                                db.ForeignKey('conversation.id'),
                                nullable=False)

    # Indexing conversation_id can improve query performance
    __table_args__ = (db.Index('idx_message_conversation_id_created_at',
                               'conversation_id', 'created_at'), )

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
            "created_at":
            self.created_at.isoformat() if self.created_at else None
        }

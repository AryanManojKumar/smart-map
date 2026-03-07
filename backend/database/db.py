from sqlalchemy import create_engine, Column, String, JSON, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from backend.config import DATABASE_URL
import os

Base = declarative_base()

class ChatHistory(Base):
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(255), unique=True, index=True)
    user_id = Column(String(255), index=True)
    messages = Column(JSON)
    route_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    archived_at = Column(DateTime)

# Create engine only if DATABASE_URL is set
engine = None
SessionLocal = None

if DATABASE_URL:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    print("⚠️  DATABASE_URL not set - database features disabled")

def init_db():
    """Initialize database tables."""
    if engine:
        Base.metadata.create_all(bind=engine)
        print("✓ Database initialized")
    else:
        print("⚠️  Skipping database initialization - DATABASE_URL not set")

def get_db():
    """Get database session."""
    if not SessionLocal:
        raise Exception("Database not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from datetime import datetime

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.api.v1.routes import router as api_router
from app.db.base import Base
from app.db.session import engine


def ensure_database_schema():
    """
    Ensure required database columns exist (for MySQL).
    This is a migration helper to add missing columns.
    """
    try:
        with engine.connect() as conn:
            # Check if is_approved column exists in users table
            result = conn.execute(text("SHOW COLUMNS FROM users LIKE 'is_approved'"))
            rows = result.fetchall()
            if not rows:
                print("Adding missing 'is_approved' column to users table...")
                conn.execute(text("ALTER TABLE users ADD COLUMN is_approved TINYINT(1) DEFAULT 0 AFTER is_active"))
                conn.commit()
                print("✓ Column 'is_approved' added successfully")
            else:
                print("✓ Column 'is_approved' already exists")
            
            # Check if organization column exists in hr_contacts table
            result = conn.execute(text("SHOW COLUMNS FROM hr_contacts LIKE 'organization'"))
            rows = result.fetchall()
            if not rows:
                print("Adding missing 'organization' column to hr_contacts table...")
                conn.execute(text("ALTER TABLE hr_contacts ADD COLUMN organization VARCHAR(255) NULL"))
                conn.commit()
                print("✓ Column 'organization' added to hr_contacts")
            
            # Check if organization column exists in students table
            result = conn.execute(text("SHOW COLUMNS FROM students LIKE 'organization'"))
            rows = result.fetchall()
            if not rows:
                print("Adding missing 'organization' column to students table...")
                conn.execute(text("ALTER TABLE students ADD COLUMN organization VARCHAR(255) NULL"))
                conn.commit()
                print("✓ Column 'organization' added to students")
            
            # Check if message_id column exists in email_conversations
            result = conn.execute(text("SHOW COLUMNS FROM email_conversations LIKE 'message_id'"))
            rows = result.fetchall()
            if not rows:
                print("Adding missing 'message_id' column to email_conversations table...")
                conn.execute(text("ALTER TABLE email_conversations ADD COLUMN message_id VARCHAR(500) NULL AFTER direction"))
                # Add index for message_id for faster lookups
                conn.execute(text("CREATE INDEX ix_email_conversations_message_id ON email_conversations(message_id)"))
                conn.commit()
                print("✓ Column 'message_id' added to email_conversations")
    except Exception as e:
        print(f"Warning: Could not verify/update database schema: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events for the FastAPI app.
    """
    # Startup
    print("Starting HireBot backend...")
    ensure_database_schema()
    yield
    # Shutdown (if needed)
    print("Shutting down HireBot backend...")


def create_app() -> FastAPI:
    """
    Application factory for the HireBot backend.
    """
    configure_logging()

    # Create database tables
    # Import all models so they're registered with Base
    from app.models.user_model import User
    from app.models.hr_contact_model import HRContact
    from app.models.student_model import Student
    from app.models.placement_requirement_model import PlacementRequirement
    from app.models.email_models import EmailConversation, EmailTemplate
    from app.models.reminder_model import Reminder
    Base.metadata.create_all(bind=engine)

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="HireBot – AI-Assisted Placement Email Automation & Student Shortlisting System",
        lifespan=lifespan,
    )

    # CORS configuration (optimized for development)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "https://accounts.google.com"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=3600,
        expose_headers=["*"]
    )

    # Include versioned API router
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    return app


app = create_app()
from typing import List
import re
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.hr_contact_model import HRContact
from app.models.email_models import EmailConversation
from app.models.placement_requirement_model import PlacementRequirement
from app.schemas.hr_schema import (
    EmailRequirementParseRequest,
    HRContactCreate,
    HRContactResponse,
    ParsedRequirement,
)
from app.services.email_service import EmailService
from app.services.ai_service import AIService
from app.services.reminder_service import ReminderService
from app.schemas.reminder_schema import ReminderCreate
from app.core.config import settings

class HRService:
    """Business logic for HR contacts, email understanding, and requirements."""

    @staticmethod
    def list_contacts(db: Session) -> List[HRContactResponse]:
        contacts = db.query(HRContact).order_by(HRContact.id.asc()).all()
        return [HRContactResponse.model_validate(c) for c in contacts]

    @staticmethod
    def create_contact(db: Session, data: HRContactCreate) -> HRContactResponse:
        contact = HRContact(
            name=data.name,
            company=data.company,
            email=data.email,
            email_status=data.email_status,
            draft_status=data.draft_status,
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
        return HRContactResponse.model_validate(contact)

    @staticmethod
    def reset_all_statuses(db: Session) -> dict:
        """Reset all HR contact statuses to 'Not Started'"""
        try:
            db.query(HRContact).update({
                HRContact.email_status: "Not Started",
                HRContact.draft_status: "Not Started"
            })
            db.commit()
            return {"message": "All HR contact statuses reset successfully"}
        except Exception as e:
            db.rollback()
            return {"error": str(e)}

    @staticmethod
    def get_conversation_history(db: Session, contact_id: int) -> dict:
        contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
        if not contact:
            return {"error": "Contact not found"}
        
        # Strict Date Filtering: Only show emails from Jan 12, 2026 onwards
        # Also filter out test emails as requested by user
        project_cutoff = datetime(2026, 1, 12)
        conversations = db.query(EmailConversation).filter(
            EmailConversation.hr_contact_id == contact_id,
            EmailConversation.sent_at >= project_cutoff,
            EmailConversation.subject != "Test DB Persistence"
        ).order_by(EmailConversation.sent_at.asc()).all()
        
        print(f"[DEBUG] get_conversation_history: Found {len(conversations)} items in DB for contact {contact_id}")

        
        # Format conversations for frontend
        conversation_list = []
        for conv in conversations:
            # Convert timestamp to milliseconds for frontend
            # Ensure we treat stored sent_at as UTC if it's naive
            dt = conv.sent_at
            if dt and dt.tzinfo is None:
                # Assume UTC
                from datetime import timezone
                dt = dt.replace(tzinfo=timezone.utc)
            
            timestamp_ms = int(dt.timestamp() * 1000) if dt else int(datetime.now().timestamp() * 1000)
            
            if conv.direction == "sent":
                sender = "Placement Team"
                recipient = "HR Team"
            else:
                sender = "HR Team"
                recipient = "Placement Team"
            
            # Add Z to indicate UTC if using isoformat
            iso_str = dt.isoformat().replace('+00:00', 'Z') if dt else datetime.utcnow().isoformat() + 'Z'
            if not iso_str.endswith('Z') and '+00:00' not in iso_str:
                 iso_str += 'Z'

            conversation_item = {
                "id": conv.id,
                "subject": conv.subject,
                "content": conv.content,
                "direction": conv.direction,
                "sender": sender,
                "recipient": recipient,
                "timestamp": timestamp_ms,
                "date_display": dt.strftime("%b %d, %I:%M %p") if dt else "", 
                "sent_at": iso_str
            }
            conversation_list.append(conversation_item)
        
        return {
            "contact": {
                "name": contact.name,
                "company": contact.company,
                "email": contact.email
            },
            "conversations": conversation_list
        }

    @staticmethod
    def sync_contact_emails(db: Session, contact_id: int) -> dict:
        contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
        if not contact:
             return {"error": "Contact not found"}
        
        try:
            print(f"[SYNC] Fetching fresh emails for {contact.email}...")
            # Use the optimized fetch with target_email filter
            replies = EmailService.fetch_replies([contact.email], target_email=contact.email)
            
            stored_count = 0
            merged_count = 0
            processed_ids = set()
            
            latest_received_content = None
            
            for reply in replies:
                direction = reply.get("direction", "received")
                subject = reply.get("subject", "")
                content = reply.get("body", "")
                message_id = reply.get("message_id")
                
                if not content or not content.strip(): continue
                if message_id and message_id in processed_ids: continue
                
                # 1. Deduplicate by ID
                existing = None
                if message_id:
                    existing = db.query(EmailConversation).filter(
                        EmailConversation.hr_contact_id == contact_id,
                        EmailConversation.message_id == message_id
                    ).first()
                
                # 2. Duplicate by Content (Merge)
                if not existing:
                    candidates = db.query(EmailConversation).filter(
                        EmailConversation.hr_contact_id == contact_id,
                        EmailConversation.direction == direction
                    ).order_by(EmailConversation.sent_at.desc()).all()
                    
                    for cand in candidates:
                        c_subj = (cand.subject or "").lower().strip()
                        c_body = (cand.content or "").lower().strip().replace('\r','').replace('\n','').replace(' ','')
                        inc_subj = subject.lower().strip()
                        inc_body = content.lower().strip().replace('\r','').replace('\n','').replace(' ','')
                        
                        if c_subj == inc_subj and c_body == inc_body:
                            existing = cand
                            if message_id: cand.message_id = message_id
                            # Sync timestamp
                            pts = reply.get("parsed_timestamp")
                            if pts: cand.sent_at = pts
                            db.commit()
                            merged_count += 1
                            break
                
                if existing:
                    if message_id: processed_ids.add(message_id)
                    continue

                # 3. Insert New
                pts = reply.get("parsed_timestamp")
                if not pts:
                    print(f"[WARN] Skipping email with bad date: {subject}")
                    continue
                
                conversation = EmailConversation(
                    hr_contact_id=contact_id,
                    subject=subject,
                    content=content,
                    direction=direction,
                    sent_at=pts,
                    message_id=message_id 
                )
                db.add(conversation)
                stored_count += 1
                if message_id: processed_ids.add(message_id)
                
                if direction == "received":
                    contact.email_status = "Replied"
                    contact.draft_status = "Completed"
                    # Process intent immediately for each received email
                    HRService._process_intent_for_email(db, contact, content)
                    latest_received_content = content
            
            db.commit()
            return {"message": f"Sync complete. New: {stored_count}, Merged: {merged_count}", "new": stored_count}
        except Exception as e:
            import traceback
            print(f"[ERROR] Sync failed for contact {contact_id}: {str(e)}")
            print(traceback.format_exc())
            db.rollback()
            return {"error": str(e)}

    @staticmethod
    def send_email(db: Session, contact_id: int, email_data: dict) -> dict:
        contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
        if not contact:
            return {"error": "Contact not found"}
        
        try:
            # Send email using EmailService
            success = EmailService.send_email(
                to_email=contact.email,
                subject=email_data.get('subject', 'Placement Communication'),
                body=email_data.get('content', '')
            )
            
            if success:
                # Store conversation
                # Use UTC for storage
                now_utc = datetime.utcnow()
                
                # Generate a hash ID so this email has a unique identifier immediately
                # This matches the logic in EmailService to prevent duplicates during sync
                import hashlib
                from app.core.config import settings
                
                sender = settings.EMAIL_USER.lower().strip()
                subject_norm = email_data.get('subject', 'Placement Communication').lower().strip()
                
                # We use a rough timestamp match or just rely on the fact that sync checks existing content
                # But providing an ID is safer.
                # Let's use the exact isoformat string we are storing as the key
                date_str = now_utc.isoformat()
                
                raw_str = f"{sender}|{subject_norm}|{date_str}" 
                generated_id = hashlib.md5(raw_str.encode('utf-8', errors='ignore')).hexdigest()

                conversation = EmailConversation(
                    hr_contact_id=contact_id,
                    subject=email_data.get('subject', 'Placement Communication'),
                    content=email_data.get('content', ''),
                    direction="sent",
                    sent_at=now_utc,
                    message_id=generated_id
                )
                db.add(conversation)
                
                # Update contact status
                contact.email_status = "Awaiting Response"
                contact.draft_status = "Completed"
                
                db.commit()
                print(f"[DEBUG] Manual email sent and saved with ID: {generated_id}")
                
                return {
                    "message": f"Email sent successfully to {contact.email}",
                    "status": "sent",
                    "error": None
                }
            else:
                return {
                    "error": "Failed to send email",
                    "message": f"Failed to send email to {contact.email}",
                    "status": "failed"
                }
        except Exception as e:
            return {
                "error": str(e),
                "message": f"Failed to send email to {contact.email}. {str(e)}",
                "status": "failed"
            }

    @staticmethod
    def parse_requirement_from_email(db: Session, data: EmailRequirementParseRequest) -> ParsedRequirement:
        """Parse job requirements from email content"""
        # TODO: Implement email parsing logic
        return ParsedRequirement(
            position="Software Developer",
            skills=["Python", "JavaScript"],
            experience="0-2 years",
            location="Remote",
            salary_range="Not specified",
            company_name=data.company_name if hasattr(data, 'company_name') else "Unknown"
        )
    
    @staticmethod
    def fetch_and_store_received_emails(db: Session) -> dict:
        """Fetch new emails from IMAP and store them for all contacts"""
        try:
            contacts = db.query(HRContact).all()
            total_stored = 0
            
            for contact in contacts:
                replies = EmailService.fetch_replies([contact.email], target_email=contact.email)
                stored_count = 0
                processed_ids = set()
                latest_received_content = None
                
                for reply in replies:
                    direction = reply.get("direction", "received")
                    subject = reply.get("subject", "")
                    content = reply.get("body", "")
                    message_id = reply.get("message_id")
                    
                    if not content or not content.strip():
                        continue
                    
                    if message_id and message_id in processed_ids:
                        continue

                    # Check for duplicates via ID
                    if message_id:
                        existing = db.query(EmailConversation).filter(
                            EmailConversation.hr_contact_id == contact.id,
                            EmailConversation.message_id == message_id
                        ).first()
                        if existing:
                            processed_ids.add(message_id)
                            continue
                    
                    # Store the email
                    pts = reply.get("parsed_timestamp") or datetime.utcnow()
                    
                    conversation = EmailConversation(
                        hr_contact_id=contact.id,
                        subject=subject,
                        content=content,
                        direction=direction,
                        sent_at=pts,
                        message_id=message_id
                    )
                    db.add(conversation)
                    if direction == "received":
                         latest_received_content = content
                         # Process intent immediately for received emails
                         HRService._process_intent_for_email(db, contact, content)
                    stored_count += 1
                    if message_id:
                        processed_ids.add(message_id)
                
                total_stored += stored_count
                if stored_count > 0:
                     # Update status if new emails were found
                     contact.email_status = "Replied"
                     contact.draft_status = "Completed"
            
            if total_stored > 0:
                db.commit()
        
            return {"message": f"Fetched and stored {total_stored} new emails", "count": total_stored}
        except Exception as e:
            db.rollback()
            return {"error": str(e), "count": 0}
    @staticmethod
    def _process_intent_for_email(db: Session, contact: HRContact, content: str):
        """Auto-extract intent and create reminder if visit detected, or cancel reminders if cancellation detected"""
        try:
            if not content or len(content) < 20: return
            
            # Check for cancellation first
            cancellation_info = AIService.detect_cancellation(content)
            if cancellation_info['is_cancelled']:
                print(f"[CANCELLATION] Detected cancellation from {contact.company}: {cancellation_info['reason']}")
                cancelled_count = ReminderService.handle_cancellation(db, contact.id, cancellation_info)
                if cancelled_count > 0:
                    print(f"[CANCELLATION] Cancelled {cancelled_count} reminders for {contact.company}")
                return
            
            # Check for rescheduling
            reschedule_info = AIService.detect_rescheduling(content)
            if reschedule_info['is_rescheduled'] and reschedule_info['new_date']:
                print(f"[RESCHEDULE] Detected rescheduling from {contact.company} to {reschedule_info['new_date']}")
                
                # Cancel old visit reminders
                cancelled_count = ReminderService.handle_cancellation(db, contact.id, {'is_cancelled': True})
                
                # Create new reminder with new date
                ReminderService.create_reminder(db, ReminderCreate(
                    contact_id=contact.id,
                    description=f"Campus Visit: Rescheduled",
                    due_date=reschedule_info['new_date'],
                    priority="high"
                ))
                print(f"[RESCHEDULE] Created new reminder for {contact.company} on {reschedule_info['new_date']}")
                return
            
            # Using AIService to extract intent
            intent = AIService.extract_intent(content, contact.company)
            
            visit_date = intent.get("visit_date")
            deadline = intent.get("deadline")
            
            trigger_date = visit_date or deadline
            
            if trigger_date:
                print(f"[AUTO] Follow-up detected for {contact.company}: {trigger_date}")
                
                # Smarter role fallback: Use role if exists, otherwise first skill, then 'Placement Drive'
                role = intent.get('role')
                if not role or role.lower() == 'none':
                    skills = intent.get('skills', [])
                    role = skills[0].title() if skills else 'Placement Drive'
                
                # Always use 'Campus Visit' prefix to ensure it appears in the premium UI section
                # even if detected as a deadline (e.g. "get back by Feb 10th")
                prefix = "Campus Visit"
                
                ReminderService.create_reminder(db, ReminderCreate(
                    contact_id=contact.id,
                    description=f"{prefix}: {role}",
                    due_date=trigger_date,
                    priority="high"
                ))
        except Exception as e:
            print(f"[AUTO] Intent extraction failed: {str(e)}")

    @staticmethod
    def generate_template_draft(db: Session, contact_id: int, template_type: str) -> dict:
        contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
        if not contact:
            return {"error": "Contact not found"}

        templates = {
            "final_year_students": {
                "subject": f"Placement Opportunity - Final Year Students | {contact.company}",
                "content": f"""Dear {contact.name or 'Hiring Team'},
 
 Greetings from the Placement Cell!
 
 We are pleased to introduce our final year students for placement opportunities at {contact.company}. Our students demonstrate exceptional academic performance and technical proficiency.
 
 We would appreciate receiving your detailed job requirements to ensure precise candidate matching. This will enable us to shortlist the most suitable candidates for your consideration.
 
 Next Steps:
 1. Share job description and requirements
 2. We provide student profiles within 48 hours
 3. Coordinate interview schedules as per your convenience
 
 Looking forward to a successful collaboration.
 
 Best regards,
 Placement Officer
 University Placement Cell"""
            },
            "follow_up": {
                "subject": f"Follow-up: Placement Requirements | {contact.company}",
                "content": f"""Dear {contact.name or 'Team'},
 
 I hope this email finds you well.
 
 This is a follow-up regarding our previous communication about placement opportunities at {contact.company}. We remain committed to providing you with qualified candidates.
 
 To proceed effectively, we kindly request:
 • Detailed job description
 • Required skills and qualifications
 • Number of positions available
 
 Once we receive these details, we will promptly share relevant student profiles for your review.
 
 Thank you for your time and consideration.
 
 Best regards,
 Placement Officer"""
            }
        }
        
        template = templates.get(template_type, templates["final_year_students"])
        
        return {
            "subject": template["subject"],
            "to": contact.email,
            "from": "placement-cell@university.edu",
            "content": template["content"],
            "recipient_email": contact.email
        }
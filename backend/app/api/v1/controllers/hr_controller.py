from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.models.email_models import EmailTemplate
from app.models.hr_contact_model import HRContact
from app.schemas.hr_schema import (
    EmailDraftRequest,
    EmailRequirementParseRequest,
    EmailSendRequest,
    HRContactCreate,
    HRContactResponse,
    ParsedRequirement,
)
from app.schemas.intent_schema import (
    IntentExtractionRequest,
    DraftReplyRequest,
    MessageAnalysisRequest,
    ExtractedIntent,
    MessageClassification,
    DraftEmailResponse,
)
from app.services.csv_service import CSVService
from app.services.hr_service import HRService
from app.services.ranking_service import RankingService
from app.services.ai_service import AIService
from app.schemas.template_schema import TemplateCreate, TemplateResponse


router = APIRouter(prefix="/hr", tags=["HR Contacts"])


@router.get("/contacts", response_model=list[HRContactResponse])
def list_contacts(db: Session = Depends(get_db)):
    return HRService.list_contacts(db)


@router.post("/contacts", response_model=HRContactResponse)
def create_contact(data: HRContactCreate, db: Session = Depends(get_db)):
    return HRService.create_contact(db, data)


@router.post("/upload-csv", response_model=list[HRContactResponse])
async def upload_hr_csv(
    file: UploadFile = File(...),
    replace_mode: bool = Form(True),
    append_mode: bool = Form(False),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV and Excel files (.csv, .xlsx, .xls) are supported."
        )

    try:
        file_bytes = await file.read()
        contacts = CSVService.import_hr_contacts_from_file(
            db, file_bytes, file.filename, replace_mode=replace_mode, append_mode=append_mode
        )
        if not contacts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid contacts found in file. Please check the file format and ensure it contains name, company, and email columns."
            )
        return [HRContactResponse.model_validate(c) for c in contacts]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process file: {str(e)}"
        )


@router.put("/contacts/{contact_id}", response_model=HRContactResponse)
def update_contact(contact_id: int, data: HRContactCreate, db: Session = Depends(get_db)):
    contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HR Contact not found"
        )
    
    # Update fields
    contact.name = data.name
    contact.company = data.company
    contact.email = data.email
    contact.email_status = data.email_status
    contact.draft_status = data.draft_status
    
    db.commit()
    db.refresh(contact)
    return HRContactResponse.model_validate(contact)


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HR Contact not found"
        )
    
    db.delete(contact)
    db.commit()
    return {"message": "HR Contact deleted successfully"}


@router.post("/parse-email", response_model=ParsedRequirement)
def parse_email_requirement(data: EmailRequirementParseRequest, db: Session = Depends(get_db)):
    return HRService.parse_requirement_from_email(db, data)


@router.post("/rank-students", response_model=list)
def rank_students_for_requirement(
    data: EmailRequirementParseRequest, db: Session = Depends(get_db)
):
    # First parse requirement, then rank students based on it
    requirement = HRService.parse_requirement_from_email(db, data)
    ranked = RankingService.rank_students_for_requirement(db, requirement)
    refined = RankingService.refine_ranking_with_llm(ranked)

    return [
        {
            "student_id": student.id,
            "name": student.name,
            "roll_no": student.roll_no,
            "domain": student.domain,
            "cgpa": student.cgpa,
            "ps_level": student.ps_level,
            "score": score,
        }
        for student, score in refined
    ]
    
@router.post("/generate-draft/{contact_id}")
def generate_draft_for_contact(
    contact_id: int, 
    request: EmailDraftRequest,
    db: Session = Depends(get_db)
):
    result = HRService.generate_template_draft(db, contact_id, request.template_type)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("error"))
    return result


@router.get("/conversation/{contact_id}")
def get_conversation_history(contact_id: int, db: Session = Depends(get_db)):
    result = HRService.get_conversation_history(db, contact_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("error"))
    return result


@router.get("/{contact_id}/sync")
def sync_contact_emails(contact_id: int, db: Session = Depends(get_db)):
    """Manually sync emails for a specific contact"""
    result = HRService.sync_contact_emails(db, contact_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.post("/reset-all-statuses")
def reset_all_statuses(db: Session = Depends(get_db)):
    """Reset all HR contact statuses to 'Not Started'"""
    return HRService.reset_all_statuses(db)


@router.post("/send-email/{contact_id}")
def send_email_to_contact(
    contact_id: int,
    request: EmailSendRequest,
    db: Session = Depends(get_db)
):
    email_data = {"subject": request.subject, "content": request.content}
    result = HRService.send_email(db, contact_id, email_data)
    
    if result.get("error") == "Contact not found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    
    # Return the result object (with error/status) so frontend can handle it properly
    # Don't raise exception here - let frontend handle the error response
    return result


@router.get("/export-excel")
def export_hr_contacts_excel(db: Session = Depends(get_db)):
    """Export all HR contacts to Excel file."""
    try:
        excel_bytes = CSVService.export_hr_contacts_to_excel(db)
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=hr_contacts.xlsx"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export HR contacts: {str(e)}"
        )


@router.get("/export-csv")
def export_hr_contacts_csv(db: Session = Depends(get_db)):
    """Export all HR contacts to CSV file."""
    try:
        csv_bytes = CSVService.export_hr_contacts_to_csv(db)
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=hr_contacts.csv"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export HR contacts: {str(e)}"
        )



@router.get("/debug-conversations/{contact_id}")
def debug_conversations(contact_id: int, db: Session = Depends(get_db)):
    """Debug endpoint to see raw conversation data"""
    from app.models.email_models import EmailConversation
    conversations = db.query(EmailConversation).filter(
        EmailConversation.hr_contact_id == contact_id
    ).all()
    
    result = []
    for conv in conversations:
        result.append({
            "id": conv.id,
            "direction": conv.direction,
            "subject": conv.subject,
            "content_length": len(conv.content) if conv.content else 0,
            "content_preview": conv.content[:100] if conv.content else "No content",
            "sent_at": conv.sent_at.isoformat() if conv.sent_at else None
        })
    
    return {"contact_id": contact_id, "conversations": result}


@router.post("/fetch-emails/{contact_id}")
def fetch_emails_for_contact(contact_id: int, db: Session = Depends(get_db)):
    """Fetch emails for a specific contact"""
    contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    try:
        # Fetch emails only for this specific contact
        from app.services.email_service import EmailService
        from app.models.email_models import EmailConversation
        replies = EmailService.fetch_replies([contact.email], target_email=contact.email)
        
        stored_count = 0
        for reply in replies:
            direction = reply.get("direction", "received")
            subject = reply.get("subject", "")
            content = reply.get("body", "")
            
            # Check for duplicate
            existing = db.query(EmailConversation).filter(
                EmailConversation.hr_contact_id == contact_id,
                EmailConversation.subject == subject,
                EmailConversation.content == content,
                EmailConversation.direction == direction
            ).first()
            
            if not existing:
                conversation = EmailConversation(
                    hr_contact_id=contact_id,
                    subject=subject,
                    content=content,
                    direction=direction,
                    sent_at=datetime.utcnow()
                )
                db.add(conversation)
                stored_count += 1
        
        db.commit()
        return {"message": f"Fetched {stored_count} new emails", "count": stored_count}
    except Exception as e:
        return {"message": f"Error: {str(e)}", "count": 0}


@router.post("/fetch-emails")
def fetch_received_emails(db: Session = Depends(get_db)):
    """Fetch new emails from IMAP and store them"""
    result = HRService.fetch_and_store_received_emails(db)
    return result

@router.delete("/clear-conversations")
def clear_all_conversations(db: Session = Depends(get_db)):
    """Clear all conversations from database"""
    try:
        from app.models.email_models import EmailConversation
        count = db.query(EmailConversation).count()
        db.query(EmailConversation).delete()
        db.commit()
        return {"message": f"Cleared {count} conversations", "count": count}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}

@router.post("/send-followup/{contact_id}")
def send_followup_email(
    contact_id: int,
    db: Session = Depends(get_db)
):
    # TODO: Implement FollowUpService
    return {"message": "Follow-up service not implemented yet"}


# Simple in-memory storage for templates
TEMPLATES_STORAGE = []

@router.post("/templates")
def create_template(request: dict):
    """Create a new email template"""
    template = {
        "id": len(TEMPLATES_STORAGE) + 1,
        "name": request["name"],
        "subject": request["subject"],
        "body": request["body"]
    }
    TEMPLATES_STORAGE.append(template)
    return template

@router.get("/templates")
def get_templates():
    """Get all email templates"""
    return TEMPLATES_STORAGE

@router.delete("/templates/{template_id}")
def delete_template(template_id: int):
    """Delete an email template"""
    global TEMPLATES_STORAGE
    TEMPLATES_STORAGE = [t for t in TEMPLATES_STORAGE if t["id"] != template_id]
    return {"message": "Template deleted successfully"}

@router.post("/create-manual-reminder")
def create_manual_reminder(request: dict, db: Session = Depends(get_db)):
    """Create a manual reminder from message content"""
    from app.services.ai_service import AIService
    from app.services.reminder_service import ReminderService
    from app.schemas.reminder_schema import ReminderCreate
    
    contact_id = request.get("contact_id")
    message = request.get("message")
    
    if not contact_id or not message:
        raise HTTPException(status_code=400, detail="contact_id and message are required")
    
    contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    # Extract intent from message
    intent = AIService.extract_intent(message, contact.company)
    visit_date = intent.get("visit_date")
    
    if visit_date:
        # Cancel old visit reminders for this contact
        cancelled_count = ReminderService.handle_cancellation(db, contact_id, {'is_cancelled': True})
        
        # Create new reminder
        new_reminder = ReminderService.create_reminder(db, ReminderCreate(
            contact_id=contact_id,
            description=f"Campus Visit: {contact.company}",
            due_date=visit_date,
            priority="high"
        ))
        
        return {
            "message": f"Manual reminder created successfully",
            "visit_date": visit_date,
            "cancelled_old_reminders": cancelled_count,
            "new_reminder_id": new_reminder.id,
            "company": contact.company
        }
    else:
        return {
            "message": "No visit date detected in message",
            "intent": intent
        }

@router.get("/debug-contact/{contact_id}")
def debug_contact(contact_id: int, db: Session = Depends(get_db)):
    """Debug endpoint to check contact existence"""
    contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
    if not contact:
        return {"error": "Contact not found", "contact_id": contact_id}
    return {
        "contact_found": True,
        "id": contact.id,
        "name": contact.name,
        "email": contact.email,
        "company": contact.company
    }

@router.post("/generate-ai-draft")
def generate_ai_draft(request: dict, db: Session = Depends(get_db)):
    """Generate AI draft with student data (legacy endpoint)"""
    try:
        contact_id = request.get("contact_id")
        hr_reply = request.get("hr_reply")
        students_data = request.get("students_data", [])
        
        contact = db.query(HRContact).filter(HRContact.id == contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        
        draft = AIService.generate_draft_with_students(hr_reply, students_data, contact.company)
        
        return {"subject": f"Re: Student Profiles - {contact.company}", "content": draft}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"AI Draft Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error generating draft: {str(e)}")


# ============================================================================
# NEW AI-POWERED ENDPOINTS USING PHI-3-MINI-4K-INSTRUCT
# ============================================================================

@router.post("/extract-intent", response_model=ExtractedIntent)
def extract_intent_from_message(request: IntentExtractionRequest):
    """
    Extract structured intent from HR message using Phi-3-Mini-4K-Instruct
    
    Returns:
    - role: Job position mentioned
    - skills: Required skills list
    - positions_count: Number of positions needed
    - deadline: Application deadline
    - visit_date: Campus visit date
    - commitments: HR commitments
    - action_items: Required actions
    - urgency: Message urgency level
    """
    try:
        intent_data = AIService.extract_intent(request.message, request.company)
        return ExtractedIntent(**intent_data)
    except Exception as e:
        import traceback
        print(f"Intent extraction error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error extracting intent: {str(e)}")


@router.post("/draft-reply", response_model=DraftEmailResponse)
def generate_draft_reply(request: DraftReplyRequest, db: Session = Depends(get_db)):
    """
    Generate AI-powered draft email reply using Phi-3-Mini-4K-Instruct
    
    Always includes [DRAFT EMAIL — REQUIRES CONFIRMATION] header
    
    Returns:
    - subject: Email subject
    - body: Email body with confirmation header
    - requires_confirmation: Always True
    - extracted_intent: Extracted requirements
    - suggested_students: Recommended students (if applicable)
    - follow_up_actions: Recommended follow-ups
    """
    try:
        # Get contact
        contact = db.query(HRContact).filter(HRContact.id == request.contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        
        # First, do a preliminary draft generation to extract requirements
        from app.utils.student_requirements import extract_student_requirements
        student_reqs = extract_student_requirements(request.hr_message)
        
        print(f"\n[CONTROLLER] Extracted student requirements: {student_reqs}")
        
        # Get students if requested - with intelligent filtering
        students_data = None
        if request.include_students:
            from app.models.student_model import Student
            from sqlalchemy import func, case
            
            query = db.query(Student)
            
            # Filter by domain if specified
            if student_reqs.get('domain'):
                domain = student_reqs['domain']
                print(f"[CONTROLLER] Filtering by domain: {domain}")
                query = query.filter(Student.domain.ilike(f"%{domain}%"))
            
            # Filter by skills if specified
            if student_reqs.get('skills'):
                skills = student_reqs['skills']
                print(f"[CONTROLLER] Filtering by skills: {skills}")
                
                # Create skill-based scoring
                # For each skill, check if it appears in skills_text and boost PS level
                skill_conditions = []
                for skill in skills:
                    skill_conditions.append(
                        case(
                            (func.lower(Student.skills_text).like(f"%{skill.lower()}%"), Student.ps_level),
                            else_=0
                        )
                    )
                
                if skill_conditions:
                    # Sum all skill matches and order by that score
                    skill_score = sum(skill_conditions)
                    query = query.order_by(skill_score.desc(), Student.ps_level.desc(), Student.cgpa.desc())
                else:
                    query = query.order_by(Student.ps_level.desc(), Student.cgpa.desc())
            else:
                # No specific skills - order by PS level and CGPA
                query = query.order_by(Student.ps_level.desc(), Student.cgpa.desc())
            
            # Limit by count if specified, otherwise default to 20
            limit = student_reqs.get('count') or 20
            print(f"[CONTROLLER] Limiting to {limit} students")
            
            students = query.limit(limit).all()
            
            print(f"[CONTROLLER] Found {len(students)} matching students")
            
            students_data = [
                {
                    "id": s.id,
                    "name": s.name,
                    "roll_no": s.roll_no,
                    "department": s.department,
                    "cgpa": float(s.cgpa) if s.cgpa else 0.0,
                    "domain": s.domain,
                    "skills_text": s.skills_text,
                    "ps_level": s.ps_level
                }
                for s in students
            ]
        
        # Generate draft
        draft_result = AIService.generate_draft_reply(
            request.hr_message,
            contact.company,
            contact.name,  # Pass contact name for personalization
            students_data
        )
        
        return DraftEmailResponse(**draft_result)
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Draft reply error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating draft reply: {str(e)}")


@router.post("/analyze-message", response_model=MessageClassification)
def analyze_hr_message(request: MessageAnalysisRequest):
    """
    Analyze and classify HR message using Phi-3-Mini-4K-Instruct
    
    Returns:
    - category: Message type (positive, need_info, not_interested, neutral)
    - sentiment: Overall sentiment
    - urgency: Urgency level
    - confidence: Classification confidence score
    - requesting_students: Whether HR is requesting student profiles
    """
    try:
        classification_data = AIService.classify_message(request.message)
        return MessageClassification(**classification_data)
    except Exception as e:
        import traceback
        print(f"Message analysis error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error analyzing message: {str(e)}")
"""
AI Service for HR reply processing and student matching using Phi-3-Mini-4K-Instruct
"""
import os
import re
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
OLLAMA_MODEL = settings.OLLAMA_MODEL


class AIService:
    """Service for AI-powered HR reply processing using microsoft/phi-3-mini-4k-instruct"""
    
    SYSTEM_PROMPT = """You are HireBot, an AI assistant for college placement officers.
You help draft professional HR emails and extract recruitment requirements.

Rules:
- Use formal, HR-safe, grammatically correct language
- Keep responses concise (2-3 paragraphs maximum)
- Never send emails directly - always require human confirmation
- Extract dates and commitments accurately
- Maintain college privacy - no external data transmission
- Be polite, professional, and helpful"""

    @staticmethod
    def extract_intent(hr_message: str, company: Optional[str] = None) -> Dict:
        """
        Extract structured intent from HR message using Phi-3
        Returns: role, skills, positions, dates, commitments, actions
        """
        print(f"\n{'='*60}")
        print(f"INTENT EXTRACTION STARTED")
        print(f"Company: {company}")
        print(f"Message: {hr_message[:150]}...")
        print(f"{'='*60}\n")
        
        if OLLAMA_AVAILABLE:
            try:
                prompt = f"""{AIService.SYSTEM_PROMPT}

Extract structured information from this HR message and return ONLY a valid JSON object.

HR Message:
\"\"\"
{hr_message}
\"\"\"

Company: {company or 'Unknown'}

Extract and return JSON with these fields:
{{
  "role": "job title or null",
  "skills": ["skill1", "skill2"] or [],
  "positions_count": number or null,
  "deadline": "date string or null",
  "visit_date": "date string or null",
  "commitments": ["commitment1"] or [],
  "action_items": ["action1"] or [],
  "urgency": "low" or "medium" or "high"
}}

Return ONLY the JSON object, no other text."""

                print(f"Calling Ollama {OLLAMA_MODEL} for intent extraction...")
                response = ollama.chat(
                    model=OLLAMA_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    options={
                        "temperature": 0.1,  # Very low for structured extraction
                        "num_predict": 300
                    }
                )
                
                result_text = response['message']['content'].strip()
                print(f"Raw AI response: {result_text[:200]}...")
                
                # Extract JSON from response
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if json_match:
                    try:
                        json_str = AIService._clean_json_text(json_match.group())
                        intent_data = json.loads(json_str)
                        print(f"[SUCCESS] Extracted intent: {intent_data}")
                        return intent_data
                    except json.JSONDecodeError as je:
                        print(f"[WARNING] JSON decode error: {je}. Raw: {json_match.group()}")
                else:
                    print("[WARNING] No JSON found in response, using fallback")
                    
            except Exception as e:
                print(f"[ERROR] Intent extraction failed: {type(e).__name__}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Fallback: Rule-based extraction
        return AIService._fallback_intent_extraction(hr_message)

    @staticmethod
    def _clean_json_text(text: str) -> str:
        """Clean JSON text from common LLM errors"""
        # Replace single quotes with double quotes
        # This is a bit risky if text contains ' inside strings, but often needed for weak LLMs
        # Better approach: use a regex to replace keys 'key': with "key":
        text = re.sub(r"'([^']*)'\s*:", r'"\1":', text)
        
        # Remove trailing commas before } or ]
        text = re.sub(r',(\s*[}\]])', r'\1', text)
        
        return text
        

    
    @staticmethod
    def _fallback_intent_extraction(hr_message: str) -> Dict:
        """Fallback rule-based intent extraction"""
        print("[INFO] Using fallback intent extraction")
        
        hr_lower = hr_message.lower()
        
        # Extract skills
        skills_keywords = ['python', 'java', 'javascript', 'react', 'node', 'ai', 'ml', 
                          'machine learning', 'data science', 'web', 'mobile', 'android', 
                          'ios', 'cloud', 'aws', 'azure', 'devops', 'testing', 'qa', 'full stack']
        
        # Use regex word boundaries to avoid matching substrings like 'ai' in 'email'
        skills_mapping = {
            'python': 'PYTHON',
            'java': 'JAVA',
            'javascript': 'JAVASCRIPT',
            'react': 'REACT.JS',
            'node': 'NODE.JS',
            'ai': 'ARTIFICIAL INTELLIGENCE',
            'ml': 'MACHINE LEARNING',
            'machine learning': 'MACHINE LEARNING',
            'data science': 'DATA SCIENCE',
            'ds': 'DATA SCIENCE',
            'web': 'WEB DEVELOPMENT',
            'mobile': 'MOBILE APP DEVELOPMENT',
            'android': 'ANDROID DEVELOPMENT',
            'ios': 'IOS DEVELOPMENT',
            'cloud': 'CLOUD COMPUTING',
            'aws': 'AMAZON WEB SERVICES (AWS)',
            'azure': 'MICROSOFT AZURE',
            'devops': 'DEVOPS',
            'testing': 'SOFTWARE TESTING',
            'qa': 'QUALITY ASSURANCE',
            'full stack': 'FULL STACK DEVELOPMENT',
            'cyber': 'CYBER SECURITY',
            'ui/ux': 'UI/UX DESIGN'
        }
        
        skills = []
        for keyword, display_name in skills_mapping.items():
            if re.search(r'\b' + re.escape(keyword) + r'\b', hr_lower):
                if display_name not in skills:
                    skills.append(display_name)
        
        # Extract count - support digits and words
        word_to_num = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }
        
        # Check for digits first
        count_match = re.search(r'(?:hire|need|requirement)\s*(?:about|around)?\s*(\d+)', hr_message, re.IGNORECASE)
        if not count_match:
            count_match = re.search(r'(\d+)\s*(?:students?|candidates?|profiles?|members?)', hr_message, re.IGNORECASE)
        positions_count = int(count_match.group(1)) if count_match else None
        
        # If no digits, check for words
        if not positions_count:
            for word, num in word_to_num.items():
                # Allow up to 30 characters (approx 4-5 words) between number and 'students'
                # e.g., "three top performing students", "five good candidates"
                if re.search(r'\b' + word + r'\b.{1,30}?(?:students?|candidates?|profiles?)', hr_lower):
                    positions_count = num
                    break
        
        # Extract dates
        visit_date = AIService._extract_date(hr_message)
        
        # Detect urgency
        urgency = "high" if any(word in hr_lower for word in ['urgent', 'asap', 'immediately']) else "medium"
        
        # Detect commitments
        commitments = []
        if 'will visit' in hr_lower or 'planning to visit' in hr_lower or 'visiting' in hr_lower:
            commitments.append("Campus visit planned")
        if 'will schedule' in hr_lower or 'will arrange' in hr_lower or 'reach out' in hr_lower:
            commitments.append("Follow-up communication")
        
        return {
            "role": None,
            "skills": skills,
            "positions_count": positions_count,
            "deadline": None,
            "visit_date": visit_date,
            "commitments": commitments,
            "action_items": [],
            "urgency": urgency
        }
    
    @staticmethod
    def _extract_date(text: str) -> Optional[str]:
        """Extract date from text"""
        current_year = datetime.now().year
        
        date_patterns = [
            # DD/MM/YYYY or DD-MM-YYYY
            r'(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})',
            # DD Month YYYY (22 January 2026)
            r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})',
            # DD Month (22 January) - assume current year
            r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*',
            # Fuzzy: "first week of February" -> returns "First Week of February 2026"
            r'(first|second|third|fourth|last|next)\s+week\s+of\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*',
        ]
        
        for i, pattern in enumerate(date_patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    
                    # Handle fuzzy date (pattern index 3)
                    if i == 3:
                        week_desc = groups[0].capitalize()
                        month_name = groups[1].capitalize()
                        # Return "First Week of February 2026"
                        return f"{week_desc} Week of {month_name} {current_year}"
                    
                    day = groups[0].zfill(2)
                    
                    # Determine month
                    if groups[1].isdigit():
                         month = groups[1].zfill(2)
                    else:
                        months = {'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 
                                 'may': '05', 'jun': '06', 'jul': '07', 'aug': '08', 
                                 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'}
                        month = months.get(groups[1][:3].lower(), '01')
                    
                    # Determine year
                    year = groups[2] if len(groups) > 2 else str(current_year)
                    
                    return f"{day}.{month}.{year}"
                except:
                    pass
        
        # Check for relative dates
        if any(phrase in text.lower() for phrase in ['tomorrow', 'next week', 'next month']):
            return "Upcoming"
        
        return None
    
    @staticmethod
    def classify_message(hr_message: str) -> Dict:
        """
        Classify HR message type and sentiment
        Returns: category, sentiment, urgency, confidence, requesting_students
        """
        hr_lower = hr_message.lower()
        
        # Quick rule-based check for student requests
        # Avoid false positives for acknowledgments like "will connect" or "thanks"
        acknowledgment_phrases = ['will connect', 'get back', 'touch base', 'thank you', 'thanks', 'appreciate']
        is_acknowledgment = any(phrase in hr_lower for phrase in acknowledgment_phrases)
        
        print(f"\n[CLASSIFY] HR Message: {hr_message[:100]}...")
        print(f"[CLASSIFY] Is acknowledgment: {is_acknowledgment}")
        
        # Remove early return for acknowledgments - always check for student requests
        # if not is_acknowledgment:
        
        checks = {
            'student+keywords': 'student' in hr_lower and any(word in hr_lower for word in ['need', 'require', 'send', 'share', 'provide', 'list', 'namelist']),
            'profile+keywords': 'profile' in hr_lower and any(word in hr_lower for word in ['send', 'share', 'provide', 'need', 'require']),
            'candidate+keywords': 'candidate' in hr_lower and any(word in hr_lower for word in ['need', 'require', 'send', 'share', 'list']),
            'resume+keywords': 'resume' in hr_lower and any(word in hr_lower for word in ['send', 'share', 'provide', 'need', 'require']),
            'namelist': 'namelist' in hr_lower,
            'name list': 'name list' in hr_lower,
            'number pattern': bool(re.search(r'\d+\s*(?:students?|candidates?|profiles?|members?)', hr_message, re.IGNORECASE))
        }
        
        requesting_students = any(checks.values())
        
        print(f"[CLASSIFY] Detection checks:")
        for check_name, result in checks.items():
            if result:
                print(f"  + {check_name}: TRUE")
        
        print(f"[CLASSIFY] Final requesting_students: {requesting_students}")
        
        if OLLAMA_AVAILABLE:
            try:
                prompt = f"""{AIService.SYSTEM_PROMPT}

Classify this HR email into ONE category and return ONLY a JSON object.

HR Message:
\"\"\"
{hr_message}
\"\"\"

Categories:
- positive: Interested, wants to schedule, asking for resumes
- need_info: Asking questions about college/students/process
- not_interested: Declining, no openings
- neutral: Auto-reply, acknowledgment

Return ONLY this JSON:
{{
  "category": "positive|need_info|not_interested|neutral",
  "sentiment": "positive|neutral|negative",
  "urgency": "low|medium|high",
  "confidence": 0.0-1.0
}}"""

                response = ollama.chat(
                    model=OLLAMA_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1, "num_predict": 100}
                )
                
                result_text = response['message']['content'].strip()
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                
                if json_match:
                    classification = json.loads(json_match.group())
                    classification['requesting_students'] = requesting_students
                    return classification
                    
            except Exception as e:
                print(f"[ERROR] Classification failed: {str(e)}")
        
        # Fallback classification
        if 'not interested' in hr_lower or 'no opening' in hr_lower:
            category = "not_interested"
            sentiment = "negative"
        elif any(word in hr_lower for word in ['interested', 'schedule', 'resume', 'profile']):
            category = "positive"
            sentiment = "positive"
        elif '?' in hr_message or 'question' in hr_lower:
            category = "need_info"
            sentiment = "neutral"
        else:
            category = "neutral"
            sentiment = "neutral"
        
        return {
            "category": category,
            "sentiment": sentiment,
            "urgency": "medium",
            "confidence": 0.7,
            "requesting_students": requesting_students
        }
    
    @staticmethod
    def _extract_latest_message(email_content: str) -> str:
        """
        Extract only the latest message from an email thread.
        Removes quoted replies (lines starting with >, or content after 'On ... wrote:')
        """
        # Split by common email thread markers
        thread_markers = [
            '\nOn ',  # "On Mon, Jan 19, 2026 at 2:52 PM"
            '\n\nOn ',
            '\n> ',  # Quoted text
            '\nFrom:',  # Email headers
            '\n-----Original Message-----',
        ]
        
        # Find the earliest thread marker
        earliest_pos = len(email_content)
        for marker in thread_markers:
            pos = email_content.find(marker)
            if pos != -1 and pos < earliest_pos:
                earliest_pos = pos
        
        # Extract only the content before the thread marker
        latest_message = email_content[:earliest_pos].strip()
        
        # Also remove lines that start with '>'
        lines = latest_message.split('\n')
        clean_lines = [line for line in lines if not line.strip().startswith('>')]
        latest_message = '\n'.join(clean_lines).strip()
        
        return latest_message
    
    @staticmethod
    def generate_draft_reply(hr_message: str, company: str, contact_name: Optional[str] = None, students_data: Optional[List[Dict]] = None) -> Dict:
        """
        Generate AI-powered draft email reply
        Returns: subject, body, extracted_intent, suggested_students, follow_up_actions
        """
        # Extract only the latest message from the thread
        clean_message = AIService._extract_latest_message(hr_message)
        
        # Extract student requirements from the message
        from app.utils.student_requirements import extract_student_requirements
        student_requirements = extract_student_requirements(clean_message)
        
        print(f"\n{'='*60}")
        print(f"DRAFT GENERATION STARTED")
        print(f"Company: {company}")
        print(f"Original message length: {len(hr_message)} chars")
        print(f"Cleaned message length: {len(clean_message)} chars")
        print(f"Cleaned message: {clean_message[:150]}...")
        print(f"Student requirements extracted: {student_requirements}")
        print(f"{'='*60}\n")
        
        # Extract intent first - use cleaned message
        intent = AIService.extract_intent(clean_message, company)
        classification = AIService.classify_message(clean_message)
        
        requesting_students = classification.get('requesting_students', False)
        
        print(f"\n[DRAFT] Classification result: {classification}")
        print(f"[DRAFT] Requesting students: {requesting_students}")
        print(f"[DRAFT] Students data provided: {len(students_data) if students_data else 0} students\n")
        
        # Generate draft
        draft_body = ""
        
        # Intelligently decide whether to include students based on HR message content
        # Only include students if HR is actually requesting them AND we have student data
        should_include_students = requesting_students and students_data and len(students_data) > 0
        
        if OLLAMA_AVAILABLE:
            try:
                if should_include_students:
                    # Generate intro for student list
                    req_count = student_requirements.get('count')
                    actual_count = len(students_data)
                    domain = student_requirements.get('domain', 'requested')
                    
                    # 1. Prepare context for Intro
                    shortfall_context = ""
                    if req_count and actual_count < req_count:
                        shortfall_context = f"""
IMPORTANT: The HR requested {req_count} students, but we only have {actual_count} suitable candidates.
You MUST explicitly state this in the intro.
REQUIRED PHRASING: "Thank you for your interest in our students. Currently, we have {actual_count} students matching your requirements for the {domain} domain. The details are shared below:"
"""
                    else:
                        shortfall_context = f"""
Standard Intro: "Thank you for your interest in our students. Based on your requirements, here are {actual_count} suitable candidates:"
"""

                    prompt = f"""{AIService.SYSTEM_PROMPT}

Write a brief professional email introduction (1 short paragraph) responding to this HR request.

HR Message:
\"\"\"
{clean_message}
\"\"\"

Company: {company}
Contact Name: {contact_name or 'Hiring Team'}

{shortfall_context}

Write ONLY the intro paragraph.
Greeting Logic:
- If Contact Name is provided, start with "Dear {contact_name},"
- Otherwise, start with "Dear {company} Team,"

End with the sentence introducing the list (e.g., "The details are shared below:").
Do NOT include a signature.
"""

                    response = ollama.chat(
                        model=OLLAMA_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        options={
                            "temperature": settings.OLLAMA_TEMPERATURE,
                            "num_predict": settings.OLLAMA_MAX_TOKENS
                        }
                    )
                    
                    intro = response['message']['content'].strip()
                    
                    # Build student list
                    student_list = []
                    for s in students_data[:20]:
                        skills = s.get('skills_text', 'N/A')
                        if skills and len(skills) > 50:
                            skills = skills[:50] + '...'
                        student_list.append(
                            f"• {s.get('name', 'N/A')} - {s.get('department', 'N/A')} (Roll: {s.get('roll_no', 'N/A')})\n"
                            f"  CGPA: {s.get('cgpa', 'N/A')} | Skills: {skills}"
                        )
                    
                    student_section = "\n\n".join(student_list)
                    
                    # 2. Select Closing Text based on count match
                    visit_acknowledgment = ""
                    if 'visit' in clean_message.lower() or 'campus' in clean_message.lower():
                        visit_acknowledgment = "We look forward to your campus visit and will ensure all necessary arrangements are made for a productive interaction with our students. "
                    
                    if req_count and actual_count < req_count:
                        closing_text = f"""{visit_acknowledgment}Currently, we have {actual_count} students matching your requirements for the {domain} domain. We will continue to identify additional suitable candidates and share their profiles as they become available.

Please let us know your preferred next steps.

Best regards,
Placement Team"""
                    else:
                        closing_text = f"""{visit_acknowledgment}These students have demonstrated strong academic performance and relevant skills in your required domain.

Please let us know your preferred next steps.

Best regards,
Placement Team"""
                    
                    draft_body = f"""{intro}

{student_section}

{closing_text}"""
                    
                else:
                    # Generate full response for non-student requests
                    prompt = f"""{AIService.SYSTEM_PROMPT}

Write a brief professional email response to this HR message.

HR Message:
\"\"\"
{clean_message}
\"\"\"

Company: {company}
Contact Name: {contact_name or 'Hiring Team'}

Guidelines:
- If they say "will connect" or "thanks", write a SHORT acknowledgment (2-3 sentences)
- If they mention a visit date, acknowledge it warmly
- Be natural and professional
- Keep it concise

Greeting Logic:
- If Contact Name is provided, start with "Dear {contact_name},"
- Otherwise, start with "Dear {company} Team,"

End with:
Best regards,
Placement Team"""

                    response = ollama.chat(
                        model=OLLAMA_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        options={
                            "temperature": settings.OLLAMA_TEMPERATURE,
                            "num_predict": settings.OLLAMA_MAX_TOKENS
                        }
                    )
                    
                    draft_body = response['message']['content'].strip()
                
                print(f"[SUCCESS] AI generated draft ({len(draft_body)} chars)")
                
            except Exception as e:
                print(f"[ERROR] Draft generation failed: {str(e)}")
                import traceback
                traceback.print_exc()
                draft_body = AIService._fallback_draft(clean_message, company, should_include_students, students_data, contact_name)
        else:
            draft_body = AIService._fallback_draft(clean_message, company, should_include_students, students_data, contact_name)
        
        # Add confirmation header - REMOVED AS REQUESTED
        # draft_with_header = f"""[DRAFT EMAIL — REQUIRES CONFIRMATION]\n\n{draft_body}"""
        
        draft_with_header = draft_body
        
        # Generate follow-up actions
        follow_up_actions = []
        if intent.get('visit_date'):
            follow_up_actions.append({
                "action_type": "reminder",
                "due_date": intent['visit_date'],
                "description": f"Campus visit scheduled for {intent['visit_date']}",
                "priority": "high"
            })
        
        return {
            "subject": f"Re: Student Profiles - {company}",
            "content": draft_with_header,
            "requires_confirmation": True,
            "extracted_intent": intent,
            "suggested_students": students_data[:10] if students_data else [],
            "follow_up_actions": follow_up_actions,
            "student_requirements": student_requirements  # Add requirements for controller
        }
    
    @staticmethod
    def _fallback_draft(hr_message: str, company: str, requesting_students: bool, students_data: Optional[List[Dict]], contact_name: Optional[str] = None) -> str:
        """Fallback draft generation"""
        print("[INFO] Using fallback draft generation")
        
        greeting = f"Dear {contact_name}," if contact_name else f"Dear {company} Team,"
        
        hr_lower = hr_message.lower()
        
        if requesting_students and students_data:
            student_list = []
            for s in students_data[:20]:
                skills = s.get('skills_text', 'N/A')
                if skills and len(skills) > 50:
                    skills = skills[:50] + '...'
                student_list.append(
                    f"• {s.get('name', 'N/A')} - {s.get('department', 'N/A')} (Roll: {s.get('roll_no', 'N/A')})\n"
                    f"  CGPA: {s.get('cgpa', 'N/A')} | Skills: {skills}"
                )
            
            student_section = "\n\n".join(student_list)
            
            student_section = "\n\n".join(student_list)
            
            # Check for campus visit mention
            visit_acknowledgment = ""
            if 'visit' in hr_message.lower() or 'campus' in hr_message.lower():
                visit_acknowledgment = "We look forward to your campus visit and will ensure all necessary arrangements are made for a productive interaction with our students. "
            
            return f"""{greeting}
 
 Thank you for your interest in our students. Currently, we have {len(students_data)} students matching your requirements. The details are shared below:
 
 {student_section}
 
 {visit_acknowledgment}These students have demonstrated strong academic performance and relevant skills in your required domain.
 
 Please let us know your preferred next steps.
 
 Best regards,
 Placement Team"""
        
        elif 'connect' in hr_lower or 'touch' in hr_lower:
            return f"""{greeting}
 
 Thank you for your response. We look forward to connecting with you soon.
 
 Please feel free to reach out whenever you're ready to discuss placement opportunities or if you need any information from our end.
 
 Best regards,
 Placement Team"""
        
        elif 'thank' in hr_lower:
            return f"""{greeting}
 
 You're welcome! We're always happy to assist with your recruitment needs.
 
 Please don't hesitate to reach out if you need any further information or support.
 
 Best regards,
 Placement Team"""
        
        else:
            return f"""{greeting}
 
 Thank you for your response. We appreciate your interest in our students.
 
 Please let us know if you need any specific information or if we can assist you in any way.
 
 Best regards,
 Placement Team"""
    
    @staticmethod
    def generate_draft_with_students(hr_reply: str, students_data: List[Dict], company: str) -> str:
        """
        Legacy method for backward compatibility
        Calls the new generate_draft_reply method
        """
        # Pass None for contact_name as this is a legacy/batch method
        result = AIService.generate_draft_reply(hr_reply, company, None, students_data)
        return result['content']
    
    @staticmethod
    def detect_cancellation(hr_message: str) -> Dict:
        """
        Detect if HR message indicates cancellation or rescheduling
        Returns: is_cancelled, reason, reschedule_mentioned
        """
        hr_lower = hr_message.lower()
        
        # Cancellation keywords
        cancellation_keywords = [
            'cancelled', 'canceled', 'cancel', 'postpone', 'postponed', 
            'reschedule', 'rescheduled', 'delay', 'delayed', 'unable to',
            'not able to', 'cannot', 'can\'t', 'won\'t be able', 'will not be able'
        ]
        
        # Visit/event keywords
        event_keywords = ['visit', 'meeting', 'interview', 'session', 'appointment']
        
        # Check for cancellation patterns
        is_cancelled = False
        reason = None
        reschedule_mentioned = False
        
        # Direct cancellation detection
        for cancel_word in cancellation_keywords:
            if cancel_word in hr_lower:
                is_cancelled = True
                break
        
        # Check if it's related to a visit/event
        if is_cancelled:
            has_event_context = any(event_word in hr_lower for event_word in event_keywords)
            if not has_event_context:
                # If no event context, it might not be a cancellation we care about
                is_cancelled = False
        
        # Extract reason if mentioned
        reason_patterns = [
            r'due to ([^.]+)',
            r'because of ([^.]+)',
            r'owing to ([^.]+)',
            r'on account of ([^.]+)'
        ]
        
        for pattern in reason_patterns:
            match = re.search(pattern, hr_lower)
            if match:
                reason = match.group(1).strip()
                break
        
        # Check for rescheduling mention
        reschedule_phrases = [
            'reschedule', 'rescheduled', 'later date', 'another time', 
            'new date', 'different date', 'postpone'
        ]
        reschedule_mentioned = any(phrase in hr_lower for phrase in reschedule_phrases)
        
        return {
            'is_cancelled': is_cancelled,
            'reason': reason or 'No specific reason provided',
            'reschedule_mentioned': reschedule_mentioned
        }
        
    @staticmethod
    def detect_rescheduling(hr_message: str) -> Dict:
        """
        Detect if HR message indicates rescheduling with new date
        Returns: is_rescheduled, new_date, reason
        """
        if not hr_message:
            return {'is_rescheduled': False, 'new_date': None, 'reason': None}
            
        hr_lower = hr_message.lower()
        
        # Rescheduling keywords
        reschedule_keywords = [
            'postponed', 'postpone', 'rescheduled', 'reschedule', 
            'moved to', 'changed to', 'shifted to', 'new date'
        ]
        
        # Visit/event keywords
        event_keywords = ['visit', 'meeting', 'interview', 'session', 'appointment']
        
        # Check for rescheduling patterns
        is_rescheduled = False
        new_date = None
        reason = None
        
        # Direct rescheduling detection
        for reschedule_word in reschedule_keywords:
            if reschedule_word in hr_lower:
                is_rescheduled = True
                break
        
        # Check if it's related to a visit/event
        if is_rescheduled:
            has_event_context = any(event_word in hr_lower for event_word in event_keywords)
            if not has_event_context:
                is_rescheduled = False
        
        # Extract new date if rescheduled
        if is_rescheduled:
            new_date = AIService._extract_date(hr_message)
        
        return {
            'is_rescheduled': is_rescheduled,
            'new_date': new_date,
            'reason': reason
        }
        
    @staticmethod
    def analyze_sentiment(email_body: str) -> str:
        """
        Analyze HR reply sentiment using Phi-3
        Returns one of: 'Positive', 'Need Info', 'Not Interested', 'Neutral'
        """
        classification = AIService.classify_message(email_body)
        
        category_map = {
            "positive": "Positive",
            "need_info": "Need Info",
            "not_interested": "Not Interested",
            "neutral": "Neutral"
        }
        
        return category_map.get(classification.get('category', 'neutral'), 'Neutral')
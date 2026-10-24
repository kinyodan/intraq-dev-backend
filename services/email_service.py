import resend
from typing import List, Dict, Optional
from pydantic import BaseModel, EmailStr
import logging
import asyncio
import hashlib
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import text
from models import Inbox


# Configure logging
logger = logging.getLogger(__name__)

class EmailContact(BaseModel):
    email: EmailStr
    name: str
    company: Optional[str] = None
    requirements: Optional[Dict] = None

class EmailTemplate(BaseModel):
    subject: str
    html_content: str
    text_content: Optional[str] = None

class EmailResult(BaseModel):
    success: bool
    email: str
    message_id: Optional[str] = None
    error: Optional[str] = None

# ======================
# EMAIL MODELS
# ======================
class EmailTemplateV2(BaseModel):
    subject: str
    html_content: str
    text_content: Optional[str] = None

# Assuming Inbox model is imported
# from app.models import Inbox 

class EmailInboxService:
    def __init__(self, client_id: str, dbSession):
        self.client_id = client_id
        self.dbSession = dbSession

    async def create_inbox(self, inboxes: list[str] | str):
        db = self.dbSession 

        if not inboxes:
            return {"status": False, "message": "missing inboxes."}

        raw_inboxes = [inboxes] if isinstance(inboxes, str) else inboxes

        try:
            inboxes_created = {}
            duplicates_skipped = []

            for raw_inbox in raw_inboxes:
                clean_inbox = raw_inbox.strip().lower()
                # 1. Generate the unique 64-character SHA256 identifier string
                inbox_hash = hashlib.sha256(clean_inbox.encode('utf-8')).hexdigest()

                # 2. Check if this specific hashed inbox already exists in DB
                existing = db.query(Inbox).filter(Inbox.inbox == inbox_hash).first()
                if existing:
                    duplicates_skipped.append(clean_inbox)
                    continue

                new_inbox = Inbox(
                    client_id=self.client_id,
                    inbox=inbox_hash, 
                    inbox_name=raw_inbox,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )

                db.add(new_inbox)
                
                # Keep tracking map (using the string hash as key so JSON formatting behaves)
                inboxes_created[inbox_hash] = clean_inbox

            # 5. Commit everything collectively in one fast transaction block
            if inboxes_created:
                db.commit()
            
            return {
                "status": True, 
                "message": f"Successfully processed {len(inboxes_created)} inboxes.", 
                "data": {
                    "created": inboxes_created,
                    "skipped_duplicates": duplicates_skipped
                }
            }

        except IntegrityError as ie:
            db.rollback()
            print(f"❌ Database Integrity Error: {ie}")
            return {"status": False, "message": "Database constraint violation occurred during processing."}
            
        except Exception as e:
            db.rollback()
            print(f"❌ Failed to create inbox: {e}")
            raise HTTPException(status_code=500, detail=f"Internal server error creating inbox: {e}")


    async def get_inboxes(self):
        db = self.dbSession 

        try:

            query = text("SELECT id, client_id, inbox, inbox_name, created_at FROM inboxes WHERE client_id = :client_id")
            result = db.execute(query, {"client_id": self.client_id}).mappings().all()

            # 3. Convert records directly into a clean list for the response wrapper
            # This step executes at near-C speeds via the underlying database driver
            serialized_inboxes = [
                {
                    "id": row["id"],
                    "client_id": row["client_id"],
                    "inbox": row["inbox"],
                    "email": row["inbox_name"],
                    "icon": "lucide:mail",
                    "label": row["inbox_name"].split("@")[0],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                }
                for row in result
            ]

            return {
                "status": True, 
                "message": f"Successfully retrieved {len(serialized_inboxes)} inboxes.", 
                "data": serialized_inboxes,
            }

            # inboxes = db.query(Inbox).filter(Inbox.client_id == self.client_id).all()

            return {
                "status": True, 
                "message": f"Successfully retrieved {len(serialized_inboxes)} inboxes.", 
                "data": serialized_inboxes,
            }

        except Exception as e:
            print(f"❌ Failed to get inboxes: {e}")
            raise HTTPException(status_code=400, detail=f"Error getting inboxes for client_id: {self.client_id}: {e}")


class EmailService:
    def __init__(self, api_key: str, from_email: str, from_name: str = "Intraq"):
        resend.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.default_from = f"{from_name} <{from_email}>"

    async def send_single_email(
        self, 
        to_contact: EmailContact, 
        template: EmailTemplate,
        reply_to: Optional[str] = None
    ) -> EmailResult:
        """Send a single email to one contact"""
        try:
            params = {
                "from": self.default_from,
                "to": [to_contact.email],
                "subject": template.subject,
                "html": self._personalize_template(template.html_content, to_contact),
                "text": self._personalize_template(template.text_content, to_contact) if template.text_content else None,
                "reply_to": reply_to
            }

            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}

            response = resend.Emails.send(params)
            
            logger.info(f"Email sent successfully to {to_contact.email}: {response['id']}")
            return EmailResult(
                success=True,
                email=to_contact.email,
                message_id=response['id']
            )
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_contact.email}: {str(e)}")
            return EmailResult(
                success=False,
                email=to_contact.email,
                error=str(e)
            )

    async def send_reply_email(original_email, reply_html, reply_text=None):

        params = {
            "from": EMAIL_DEFAULT_FROM,
            "to": [original_email["from"]],
            "subject": f"Re: {original_email['subject']}",
            "html": reply_html,
            "headers": {
                "In-Reply-To": original_email["message_id"],
                "References": original_email["message_id"]
            }
        }

        if reply_text:
            params["text"] = reply_text

        response = await resend.Emails.send(params)

        return response

    async def send_bulk_emails(
        self,
        contacts: List[EmailContact],
        template: EmailTemplate,
        batch_size: int = 50,
        delay_between_batches: float = 1.0
    ) -> List[EmailResult]:
        """Send emails to multiple contacts with rate limiting"""
        results = []
        
        for i in range(0, len(contacts), batch_size):
            batch = contacts[i:i + batch_size]
            batch_tasks = []
            
            for contact in batch:
                task = self.send_single_email(contact, template)
                batch_tasks.append(task)
            
            # Process current batch
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)
            
            # Rate limiting between batches
            if i + batch_size < len(contacts):
                await asyncio.sleep(delay_between_batches)
                
            logger.info(f"Processed batch {i//batch_size + 1}/{(len(contacts)-1)//batch_size + 1}")
        
        return results

    def _personalize_template(self, content: str, contact: EmailContact) -> str:
        """Personalize email template with contact information"""
        if not content:
            return content
            
        replacements = {
            "{{name}}": contact.name,
            "{{first_name}}": contact.name.split()[0] if contact.name else "there",
            "{{company}}": contact.company or "your company",
            "{{email}}": contact.email
        }
        
        personalized = content
        for placeholder, value in replacements.items():
            personalized = personalized.replace(placeholder, value)
            
        return personalized

# Email templates for Intraq
class IntraqTemplates:

    def get_introduction_template(requirements: Optional[Dict] = None) -> EmailTemplate:
        base_subject = "Transform Your Data Strategy with Intraq - Reliable Data Solutions for Africa"
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
                .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }
                .cta-button { background: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0; }
                .footer { text-align: center; margin-top: 30px; color: #666; font-size: 14px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Intraq</h1>
                    <p>Reliable Data Solutions for Africa's Leading Organizations</p>
                </div>
                <div class="content">
                    <h2>Hello {{first_name}},</h2>
                    
                    <p>I hope this message finds you well. I'm reaching out from <strong>Intraq</strong>, where we specialize in providing enterprise-grade data solutions tailored for African markets.</p>
                    
                    <p>We understand that {{company}} faces unique data challenges, and we're here to help you:</p>
                    
                    <ul>
                        <li>📊 Implement robust data infrastructure and pipelines</li>
                        <li>🔍 Gain actionable insights from your data assets</li>
                        <li>🌍 Navigate Africa-specific data regulations and markets</li>
                        <li>🚀 Scale your data capabilities as you grow</li>
                    </ul>

                    <p>Our solutions have helped organizations across the continent transform their data strategy and drive measurable business outcomes.</p>
                    
                    <p>Would you be open to a brief 15-minute call next week to discuss how Intraq could support {{company}}'s data initiatives?</p>
                    
                    <div style="text-align: center;">
                        <a href="https://calendly.com/intraq-demo/introduction" class="cta-button">Schedule a Discovery Call</a>
                    </div>
                    
                    <p>Alternatively, you can reply to this email directly - I'd be happy to answer any questions you might have.</p>
                    
                    <p>Looking forward to the possibility of working together!</p>
                    
                    <p>Best regards,<br>
                    <strong>The Intraq Team</strong></p>
                </div>
                <div class="footer">
                    <p>Intraq - Reliable Data Solutions for Africa<br>
                    <a href="https://intraq.simokai.com">Visit our website</a> | <a href="mailto:contact@intraq.com">Contact us</a></p>
                    <p><small>If you'd prefer not to receive these emails, please <a href="#">unsubscribe here</a>.</small></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return EmailTemplate(
            subject=base_subject,
            html_content=html_content
        )

    def get_follow_up_template() -> EmailTemplate:
        return EmailTemplate(
            subject="Following up: Data Solutions for {{company}}",
            html_content="""
            <!DOCTYPE html>
            <html>
            <body>
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2>Hi {{first_name}},</h2>
                    
                    <p>I wanted to follow up on my previous email about how Intraq could help {{company}} with data solutions.</p>
                    
                    <p>I understand you're busy, but I truly believe we could add significant value to your data initiatives.</p>
                    
                    <p>Would any of these be helpful?</p>
                    <ul>
                        <li>A quick 10-minute chat about your current data challenges</li>
                        <li>Specific case studies relevant to your industry</li>
                        <li>Information about our implementation process</li>
                    </ul>
                    
                    <p>No pressure at all - just let me know what would be most useful!</p>
                    
                    <p>Best,<br>
                    The Intraq Team</p>
                </div>
            </body>
            </html>
            """
        )

    def get_introduction_template_v2(
        first_name: str = "",
        company: str = "your organization",
        sender_full_name:  str = "Daniel Kinyo",
        sender_title: str = "Founder, Intraq",
        sender_phone: str = "+254791199816",
        recipient_name: str = None
    ):
        """Introduction email template with dynamic parameters"""
        
        # Use recipient_name if provided, otherwise fallback to first_name
        name_to_use = recipient_name or first_name

        base_subject = f"Data Partnership with Intraq - {company or 'Your Organization'}"

        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Intraq</title>
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    font-family: 'Inter', system-ui, -apple-system, sans-serif;
                    background-color: #0f172a;
                    color: #e2e8f0;
                    line-height: 1.7;
                }}
                .container {{
                    max-width: 620px;
                    margin: 24px auto;
                    background-color: #1e2937;
                    border-radius: 16px;
                    overflow: hidden;
                    box-shadow: 0 15px 35px rgba(0, 0, 0, 0.4);
                }}
                .header {{
                    background: linear-gradient(135deg, #1e2937 0%, #334155 100%);
                    padding: 45px 40px 35px;
                    text-align: center;
                    border-bottom: 3px solid #f97316;
                }}
                .header .intro-heading {{
                    color: #cbd5e1;
                }}
                .logo {{
                    font-size: 34px;
                    font-weight: 800;
                    letter-spacing: -1.5px;
                    color: #ffffff;
                    margin-bottom: 8px;
                }}
                .logo span {{
                    color: #f97316;
                }}
                .content {{
                    padding: 45px 40px;
                }}
                .content h2 {{
                    color: #f1f5f9;
                    font-size: 24px;
                    margin-top: 0;
                }}
                .content p {{
                    font-size: 16.5px;
                    color: #cbd5e1;
                    margin-bottom: 20px;
                }}
                .signature a {{
                    color: #f97316;
                    text-decoration: none;
                }}
                .cta-button {{
                    display: inline-block;
                    background: #f97316;
                    color: #ffffff;
                    padding: 16px 36px;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 16.5px;
                    margin: 30px 0;
                    box-shadow: 0 6px 20px rgba(249, 115, 22, 0.4);
                }}
                .footer {{
                    background-color: #0f172a;
                    padding: 35px 40px;
                    text-align: center;
                    font-size: 14px;
                    color: #94a3b8;
                    border-top: 1px solid #334155;
                }}
                .footer a {{
                    color: #f97316;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">intra<span>q</span></div>
                    <h1 class="intro-heading">Data Operations for Impact</h1>
                </div>

                <div class="content">
                    <p>Hi {name_to_use},</p>
                    
                    <p>I hope you're doing well.</p>
                    
                    <p>I've been following {company}’s work and I'm really impressed with the impact you're making.</p>
                    
                    <p>I'm the founder of <strong>Intraq</strong>, a data operations company. We specialize in high-volume data entry, cleaning, and management for development and humanitarian programmes.</p>
                    
                    <p>I'd like to connect and explore whether we could support the data needs of your current projects.</p>
                    
                    <p>Thank you for the great work you're doing.</p>
                    
                    <p>Best regards,<br>
                    <strong>{sender_full_name}</strong><br>
                    <strong>{sender_phone}</strong><br>
                    {sender_title}<br>
                    <span class="signature"><a href="https://intraq.pro">intraq.pro</a></span>; </br>
                    Nairobi, Kenya</p>
                </div>

                <div class="footer">
                    <p><strong>Intraq</strong> — Reliable Data Operations for Development & Humanitarian Programmes</p>
                    <p>
                        <a href="https://intraq.pro">intraq.pro</a> 
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return {
            "subject": base_subject,
            "html_content": html_content
        }       


    def get_introduction_template_custom_v2(
        first_name: str = "",
        company: str = "your organization",
        sender_full_name:  str = "Daniel Kinyo",
        sender_title: str = "Founder, Intraq",
        sender_phone: str = "+254791199816",
        recipient_name: str = None,
        content: str = None,
    ):
        """Introduction email template with dynamic parameters"""
        
        # Use recipient_name if provided, otherwise fallback to first_name
        name_to_use = recipient_name or first_name

        base_subject = f"Data Partnership with Intraq - {company or 'Your Organization'}"

        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Intraq</title>
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    font-family: 'Inter', system-ui, -apple-system, sans-serif;
                    background-color: #0f172a;
                    color: #e2e8f0;
                    line-height: 1.7;
                }}
                .container {{
                    max-width: 620px;
                    margin: 24px auto;
                    background-color: #1e2937;
                    border-radius: 16px;
                    overflow: hidden;
                    box-shadow: 0 15px 35px rgba(0, 0, 0, 0.4);
                }}
                .header {{
                    background: linear-gradient(135deg, #1e2937 0%, #334155 100%);
                    padding: 45px 40px 35px;
                    text-align: center;
                    border-bottom: 3px solid #f97316;
                }}
                .header .intro-heading {{
                    color: #cbd5e1;
                }}
                .logo {{
                    font-size: 34px;
                    font-weight: 800;
                    letter-spacing: -1.5px;
                    color: #ffffff;
                    margin-bottom: 8px;
                }}
                .logo span {{
                    color: #f97316;
                }}
                .content {{
                    padding: 45px 40px;
                }}
                .content h2 {{
                    color: #f1f5f9;
                    font-size: 24px;
                    margin-top: 0;
                }}
                .content p {{
                    font-size: 16.5px;
                    color: #cbd5e1;
                    margin-bottom: 20px;
                }}
                .signature a {{
                    color: #f97316;
                    text-decoration: none;
                }}
                .cta-button {{
                    display: inline-block;
                    background: #f97316;
                    color: #ffffff;
                    padding: 16px 36px;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 16.5px;
                    margin: 30px 0;
                    box-shadow: 0 6px 20px rgba(249, 115, 22, 0.4);
                }}
                .footer {{
                    background-color: #0f172a;
                    padding: 35px 40px;
                    text-align: center;
                    font-size: 14px;
                    color: #94a3b8;
                    border-top: 1px solid #334155;
                }}
                .footer a {{
                    color: #f97316;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">intra<span>q</span></div>
                    <h1 class="intro-heading">Data Operations for Impact</h1>
                </div>

                <div class="content">
                    <p>Hi {name_to_use},</p>

                    {content}

                    <table border="0" cellpadding="0" cellspacing="0" style="max-width: 380px; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; border-collapse: collapse;">
                      <tr>
                        <td style="padding: 0 0 15px 0;">
                          <table border="0" cellpadding="0" cellspacing="0">
                            <tr>
                              <!-- Logo -->
                              <td style="padding-right: 18px; vertical-align: top;">
                                <div style="font-size: 28px; font-weight: 800; letter-spacing: -1.5px; color: #0f172a;">
                                  intra<span style="color: #f97316;">q</span>
                                </div>
                              </td>
                              <!-- Content -->
                              <td style="vertical-align: top; padding-top: 4px;">
                                <div style="font-size: 15px; font-weight: 600; color: #0f172a; margin-bottom: 2px;">
                                  Daniel Kinyo
                                </div>
                                <div style="font-size: 13px; color: #64748b; margin-bottom: 8px;">
                                  Founder & Director
                                </div>
                                <div style="font-size: 13px; color: #334155; line-height: 1.5;">
                                  Intraq Data Operations<br>
                                  Nairobi, Kenya
                                </div>
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                      
                      <tr>
                        <td style="padding: 12px 0; border-top: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0;">
                          <table border="0" cellpadding="0" cellspacing="0" style="font-size: 13px;">
                            <tr>
                              <td style="padding-right: 20px;">
                                <a href="tel:+254791199816" style="color: #64748b; text-decoration: none;">📞 +254 791 199 816</a>
                              </td>
                              <td style="padding-right: 20px;">
                                <a href="mailto:danielkinyo@intraq.pro" style="color: #64748b; text-decoration: none;">✉️ danielkinyo@intraq.pro</a>
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                      
                      <tr>
                        <td style="padding-top: 12px;">
                          <a href="https://intraq.pro" style="color: #f97316; text-decoration: none; font-weight: 500; font-size: 13px;">
                            www.intraq.pro
                          </a>
                          <span style="color: #cbd5e1; margin: 0 8px;">•</span>
                          <span style="color: #64748b; font-size: 12.5px;">
                            Professional Data Operations
                          </span>
                        </td>
                      </tr>
                    </table>
                 </div>

                <div class="footer">
                    <p><strong>Intraq</strong> — Reliable Data Operations for Development & Humanitarian Programmes</p>
                    <p>
                        <a href="https://intraq.pro">intraq.pro</a> 
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return {
            "subject": base_subject,
            "html_content": html_content
        }


    def get_reply_template_custom_v2(
        sender_full_name: str = "Daniel Kinyo",
        sender_title: str = "Founder, Intraq",
        sender_email: str = "Danielkinyo@intraq.pro",
        sender_phone: str = "+254 791 199 816",
        content: str = None,
        original_subject: str = "RE: "
    ):
        
        base_subject = {original_subject} 

        html_content = f"""
        <html>
            <head></head>
            <body>
            {content}
              <table border="0" cellpadding="0" cellspacing="0" style="max-width: 380px; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; border-collapse: collapse; margin-bottom: 25px;">
                <tr>
                  <td style="padding: 0 0 15px 0;">
                    <table border="0" cellpadding="0" cellspacing="0">
                      <tr>
                        <td style="padding-right: 18px; vertical-align: top;">
                          <div style="font-size: 28px; font-weight: 800; letter-spacing: -1.5px; color: #0f172a;">
                            intra<span style="color: #ffffff;">q</span>
                          </div>
                        </td>
                        <td style="vertical-align: top; padding-top: 4px;">
                          <div style="font-size: 15px; font-weight: 600; color: #0f172a; margin-bottom: 2px;">
                            {sender_full_name}
                          </div>
                          <div style="font-size: 13px; color: #64748b; margin-bottom: 8px;">
                            {sender_title}
                          </div>
                          <div style="font-size: 13px; color: #334155; line-height: 1.5;">
                            Intraq Data Solutions<br>
                            Nairobi, Kenya
                          </div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
               
                <tr>
                  <td style="padding: 12px 0; border-top: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0;">
                    <table border="0" cellpadding="0" cellspacing="0" style="font-size: 13px;">
                      <tr>
                        <td style="padding-right: 20px;">
                          <a href="tel:+254791199816" style="color: #64748b; text-decoration: none;">📞 {sender_phone}</a>
                        </td>
                        <td style="padding-right: 20px;">
                          <a href="mailto:{sender_email}" style="color: #64748b; text-decoration: none;">✉️ {sender_email}</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
               
                <tr>
                  <td style="padding-top: 12px;">
                    <a href="https://intraq.pro" style="color: #f97316; text-decoration: none; font-weight: 500; font-size: 13px;">
                      www.intraq.pro
                    </a>
                    <span style="color: #cbd5e1; margin: 0 8px;">•</span>
                    <span style="color: #64748b; font-size: 12.5px;">
                      Professional Data Operations
                    </span>
                  </td>
                </tr>
              </table>

              <!-- Full Width Divider -->
              <div style="margin: 25px 0 30px 0; width: 100%;">
                <div style="display: flex; align-items: center; width: 100%;">
                  <div style="flex: 1; height: 1px; background: #f59e0b33;"></div>
                  <div style="padding: 0 18px; text-align: center; white-space: nowrap;">
                    <div style="font-size:12px; letter-spacing:3px; color:#f59e0b; font-weight:700;">
                      INTRAQ
                    </div>
                    <div style="font-size:10px; letter-spacing:1px; color:#999; margin-top:3px;">
                      Data Solutions (DataOps) | FinOps Solutions
                    </div>
                  </div>
                  <div style="flex: 1; height: 1px; background: #f59e0b33;"></div>
                </div>
              </div>

              <div dir="ltr" style="margin-top: 20px;">
                <div dir="ltr">test&nbsp;</div><br>
              </div>
            </body>
        </html>
        """

        return {
            "subject": base_subject,
            "html_content": html_content
        }  









# class EmailService:
#     def __init__(self, from_email: str, from_name: str = "Intraq"):
#         self.from_email = from_email
#         self.from_name = from_name
#         self.default_from = f"{from_name} <{from_email}>"

#     async def send_single_email(
#         self, 
#         to_contact: EmailContact, 
#         template: EmailTemplate,
#         reply_to: Optional[str] = None
#     ) -> EmailResult:
#         """Send a single email to one contact"""
#         try:
#             params = {
#                 "from": self.default_from,
#                 "to": [to_contact.email],
#                 "subject": template.subject,
#                 "html": self._personalize_template(template.html_content, to_contact),
#                 "text": self._personalize_template(template.text_content, to_contact) if template.text_content else None,
#                 "reply_to": reply_to
#             }

#             # Remove None values
#             params = {k: v for k, v in params.items() if v is not None}

#             response = resend.Emails.send(params)
            
#             print(f"Email sent successfully to {to_contact.email}: {response['id']}")
#             return EmailResult(
#                 success=True,
#                 email=to_contact.email,
#                 message_id=response['id']
#             )
            
#         except Exception as e:
#             print(f"Failed to send email to {to_contact.email}: {str(e)}")
#             return EmailResult(
#                 success=False,
#                 email=to_contact.email,
#                 error=str(e)
#             )

#     async def send_bulk_emails(
#         self,
#         contacts: List[EmailContact],
#         template: EmailTemplate,
#         batch_size: int = 50,
#         delay_between_batches: float = 1.0
#     ) -> List[EmailResult]:
#         """Send emails to multiple contacts with rate limiting"""
#         results = []
        
#         for i in range(0, len(contacts), batch_size):
#             batch = contacts[i:i + batch_size]
#             batch_tasks = []
            
#             for contact in batch:
#                 task = self.send_single_email(contact, template)
#                 batch_tasks.append(task)
            
#             # Process current batch
#             batch_results = await asyncio.gather(*batch_tasks)
#             results.extend(batch_results)
            
#             # Rate limiting between batches
#             if i + batch_size < len(contacts):
#                 await asyncio.sleep(delay_between_batches)
                
#             print(f"Processed batch {i//batch_size + 1}/{(len(contacts)-1)//batch_size + 1}")
        
#         return results

#     def _personalize_template(self, content: str, contact: EmailContact) -> str:
#         """Personalize email template with contact information"""
#         if not content:
#             return content
            
#         replacements = {
#             "{{name}}": contact.name,
#             "{{first_name}}": contact.name.split()[0] if contact.name else "there",
#             "{{company}}": contact.company or "your company",
#             "{{email}}": contact.email
#         }
        
#         personalized = content
#         for placeholder, value in replacements.items():
#             personalized = personalized.replace(placeholder, value)
            
#         return personalized


# Initialize email service
# email_service = EmailService(
#     from_email=os.getenv("FROM_EMAIL", "onboarding@resend.dev"),
#     from_name="Intraq"
# )

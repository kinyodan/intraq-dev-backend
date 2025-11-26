import resend
from typing import List, Dict, Optional
from pydantic import BaseModel, EmailStr
import logging
from datetime import datetime
import asyncio

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
    @staticmethod
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

    @staticmethod
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
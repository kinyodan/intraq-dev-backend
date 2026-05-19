import resend
import os

resend.api_key = os.getenv("RESEND_API_KEY")

async def get_full_email(email_id: str):
    try:
        email = resend.Emails.get_received(email_id)   # or resend.emails.receiving.get()
        
        print("From:", email['from'])
        print("Subject:", email['subject'])
        print("Text Body:", email.get('text'))
        print("HTML Body:", email.get('html'))
        
        return email
    except Exception as e:
        print("Error fetching email:", e)
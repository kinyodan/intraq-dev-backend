import resend
import os

resend.api_key = os.getenv("RESEND_API_KEY")

async def get_full_email(email_id: str):
    try:
        # ✅ Correct method
        email = resend.emails.receiving.get(email_id)
        
        print("✅ Full email fetched successfully!")
        print("From:", email.get('from'))
        print("Subject:", email.get('subject'))
        print("Text Body:", email.get('text'))
        print("HTML Body:", email.get('html'))
        
        return email
        
    except Exception as e:
        print(f"❌ Error fetching full email: {e}")
        return None
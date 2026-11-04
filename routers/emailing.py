from core.imports import *
from services.websocket import ConnectionManager
from fastapi import APIRouter

router = APIRouter()

ws_manager = ConnectionManager()

# Initialize Resend
resend.api_key = os.getenv("RESEND_API_KEY", "re_L7GET6YB_9SmX2f257av61Xon1f6jz4FS")
EMAIL_DEFAULT_FROM = "Danielkinyo@intraq.pro"


# ======================
# EMAIL MODELS & SERVICE
# ======================
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

class EmailResponse(BaseModel):
    success: bool
    message: str
    results: List[dict]
    total_sent: int
    total_failed: int

class BulkEmailRequest(BaseModel):
    contacts: List[EmailContact]
    template_type: str = "introduction"  # "introduction" or "follow_up"
    batch_size: int = 50

# ======================
# CREATE INBOXES 
# ======================
@router.post("/admin/create_inbox/{client_id}")
async def create_inbox(
    client_id: str,
    emails: dict,  # Expecting JSON body format like: {"emails": ["user1@ex.com", "user2@ex.com"]}
    current_user: dict = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    print(emails)

    try:
        inbox_data = emails.get("emails") or emails

        service = EmailInboxService(
            client_id=client_id, 
            dbSession=db
        )
        
        result = await service.create_inbox(inboxes=inbox_data)

        if not result.get("status"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=result.get("message", "Failed to process request")
            )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=result
        )

    except HTTPException:
        raise  # Re-raise explicit FastAPI HTTP exceptions cleanly
    except Exception as e:
        print(f"❌ Route level crash: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Error creating client inbox(s): {e}"
        )


# ======================
# GET INBOXES 
# ======================
@router.get("/admin/client_inboxes/{client_id}")
async def get_inboxes(
    client_id: str,
    current_user: dict = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    # try:
    service = EmailInboxService(
        client_id=client_id, 
        dbSession=db
    )
    
    result = await service.get_inboxes()

    return JSONResponse(
        status_code=200,
        content={
            "status": True, 
            "data": result, 
            "message": "Successfully retrieved inboxes."
        }
    )

    # except Exception as e:
    #     print(e)
    #     raise HTTPException(status_code=400, detail=f"Error fetching client inboxes {e}")


# ======================
# GET EMAILS ENDPOINTS
# ======================
@router.get("/client/emails/{target_inbox}")
async def get_client_emails(
    target_inbox: str,
    page: int = Query(1, ge=1),     
    size: int = Query(20, ge=1),  
    current_user: dict = Depends(get_admin_user)
):  
    try:
        email_lookup_key = target_inbox.strip().lower()
        email_key = f"client:{email_lookup_key}:emails"
        order_key = f"{email_key}:order"
        
        start = (page - 1) * size
        end = start + size - 1
        
        email_ids_for_page = REDIS_DB.zrevrange(order_key, start, end)
        total_items = REDIS_DB.zcard(order_key)
    
        total_pages = (total_items + size - 1) // size if total_items > 0 else 0
        
        # If no items exist, return an empty array early and cleanly
        if not email_ids_for_page:
            return JSONResponse(
                status_code=200,
                content={
                    "status": True, 
                    "data": [], 
                    "pagination": {
                        "total": 0,
                        "page": page,
                        "size": size,
                        "pages": 0
                    },
                    "message": "No emails found for this inbox."
                }
            )
    
        paginated_emails = await get_emails_by_ids(email_key, email_ids_for_page)

        return JSONResponse(
            status_code=200,
            content={
                "status": True, 
                "data": paginated_emails, 
                "pagination": {
                    "total": total_items,
                    "page": page,
                    "size": size,
                    "pages": total_pages # Now safely defined!
                },
                "message": "Successfully retrieved email data"
            }
        )

    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=f"Error fetching client emails {e}")

# ======================
# GET SINGLE EMAIL ENDPOINT
# ======================
@router.get("/client/email/{target_inbox}/{email_id}")
async def get_single_email(
    target_inbox: str,
    email_id: str,
    current_user: dict = Depends(get_admin_user)
):  
    try:
        # Added 'await' here
        email = await get_email(target_inbox, email_id)

        return JSONResponse(
            status_code=200,
            content={"status": True, "data": email, "message": "Successfully retrieved email data"}
        )

    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=f"Error fetching email {e}")
 

# ======================
# SEND EMAIL ENDPOINT
# ======================
@router.post("/api/emails/send")
async def send_email(
    to: str = Form(...),
    cc: Optional[List[str]] = Form(None),
    first_name: str = Form(...), 
    company: str = Form(...), 
    sender_full_name: str = Form(...), 
    sender_title: str = Form(...), 
    sender_phone: str = Form(...), 
    recipient_name: str = Form(...),
    content: str =  Form(...),
    reply_to: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Send a single email using Resend"""
    if not content:
        print(f"content is required  ")
        raise HTTPException(status_code=400, detail=f"content is required")        

    try:

        to_list = ast.literal_eval(to)

        print(to_list)
        print(type(to_list))

        template = IntraqTemplates.get_introduction_template_custom_v2(
            first_name,
            company,
            sender_full_name,
            sender_title,
            sender_phone,
            recipient_name,
            content
        )

        params = {
            "from": f"{sender_full_name} <{EMAIL_DEFAULT_FROM}>",
            "to": to_list,
            "subject": template["subject"],
            "html": template["html_content"],
        }

        if cc:
            params["cc"] = cc

        if reply_to: 
            params["reply_to"] = reply_to

        response = resend.Emails.send(params)
        
        return {
            "success": True,
            "message": "Email sent successfully",
            "message_id": response.get("id"),
            "to": to_list,
            "cc": cc
        }
        
    except Exception as e:
        print(f"Send email error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


# ======================
# REPLY EMAIL ENDPOINT
# ======================
@router.post("/api/emails/reply")
async def reply_email(
    to: str = Form(...),
    content: str = Form(...),
    original_message_id: str = Form(...),
    original_subject: str = Form(...),
    client_id: str = Form(...),
    cc: Optional[List[str]] = Form(None),
    reply_to: Optional[str] = Form(None),

    current_user: dict = Depends(get_current_user)
):
    """Send a single email using Resend"""
    if not content:
        print(f"content is required")
        raise HTTPException(status_code=400, detail=f"content is required")        

    try:

        to_list = ast.literal_eval(to)

        # template = IntraqTemplates.get_reply_template_custom_v2(
        #     original_subject,
        #     content
        # )

        from_email = f"{sender_full_name} <{EMAIL_DEFAULT_FROM}>"
        subject = f"Re: {original_subject}"

        email_data = {
            "email_id": original_message_id,
            "from": from_email,
            "to": to_list,
            "subject": subject,
            "received_at": datetime.utcnow().isoformat(),
            "summary": content,
            "created_at": datetime.utcnow().isoformat(),
            "full_email": content,
        }

        params = {
            "from": from_email,
            "to": to_list,
            "subject": subject,
            "html": content,
            "headers": {
                "In-Reply-To": original_message_id,
                "References": original_message_id
            }
        }

        if cc:
            params["cc"] = cc

        if reply_to:
            params["reply_to"] = reply_to

        response = resend.Emails.send(params)
        email_data["sending_response"] = response

        result_data = await save_reply_email_to_redis(client_id, email_data)

        return {
            "success": True,
            "message": "Reply sent successfully",
            "message_id": response.get("id"),
            "to": to_list,
            "cc": cc,
            "in_reply_to": original_message_id,
            "sending_response": response,
            "saving_status": result_data
        }

    except Exception as e:
        print(f"Reply email error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ======================
# WEBSOCKET ENDPOINT
# ======================
@router.websocket("/ws/inbound_email/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket endpoint for real-time inbound email notifications.
    
    Connect with: WS /ws/inbound_email/{client_id}
    Example: wss://intraq-backend.onrender.com/ws/inbound_email/CLG2WTPQ9X
    
    The client_id is used to route inbound email webhooks to the correct connection(s).
    """
    await ws_manager.connect(websocket, client_id)
    try:
        while True:
            try:
                await websocket.send_text("ping")
                await asyncio.sleep(30)
            except Exception:
                break

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, client_id)
        print(f"🔌 WebSocket disconnected: client_id={client_id}")


# ======================
# RECEIVE EMAIL WEBHOOK (Inbound)
# ======================
@router.post("/webhook/inbound")
async def resend_inbound_webhook(request: Request, client_id: str = Query(None)):
    """Resend Inbound Email Webhook - Receives replies and incoming emails
    
    Query params:
        - client_id: The client identifier to broadcast the email to (e.g., CLG2WTPQ9X)
    
    When client_id is provided, the email data will be broadcast via WebSocket
    to all connected clients listening on that client_id channel.
    """
    
    try:
        payload = await request.json()
        
        if payload.get("type") == "email.received":
            data = payload.get("data", {})
            
            full_email = await get_full_email(data.get("email_id"))
            print(f"📥 Webhook received, target_inbox={full_email}")

            email_data = {
                "email_id": data.get("email_id"),
                "from": data.get("from"),
                "to": data.get("to"),
                "subject": data.get("subject"),
                "text": data.get("text"),
                "html": data.get("html"),
                "full_email": full_email,
                "received_at": data.get("received_at"),
                "attachments": data.get("attachments", [])
            }
            
            print(f"📧 New inbound email received from {email_data['from']}")
            print(f"Subject: {email_data['subject']}")

            target_inbox = data.get("to", None)

            print(f"target_inbox: {target_inbox}")

            if not target_inbox:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": "Webhook received email but target_inbox missing"}
                ) 

            result_data = await save_email_to_redis(target_inbox, email_data)

            # Broadcast to WebSocket clients if client_id is provided
            if client_id:
                print(f"📡 Broadcasting to channel={client_id}")
                await ws_manager.send_message_to_client(client_id, {
                    "type": "inbound_emails",
                    "data": result_data
                })
            
            # Send telegram notification (non-blocking, ignore errors)
            try:
                await send_telegram_msg(email_data)
            except Exception as te:
                print(f"⚠️ Telegram notification skipped: {te}")
            # TODO: Process the email (save to DB, create ticket, auto-reply, etc.)
            # Example: await process_inbound_email(email_data)
            
            return {"status": "success", "message": "Email received"}
        
        return {"status": "ignored", "type": payload.get("type")}
        
    except Exception as e:
        print(f"Inbound webhook error: {e}")
        # Still return 200 so Resend doesn't retry
        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": "Webhook received but processing failed"}
        )



# ======================
# NEW EMAIL ENDPOINTS
# ======================
@router.post("/api/emails/send-bulk", response_model=EmailResponse)
async def send_bulk_emails(
    request: BulkEmailRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Send bulk emails to multiple contacts"""
    try:
        # Get appropriate template
        if request.template_type == "introduction":
            template = IntraqTemplates.get_introduction_template()
        elif request.template_type == "follow_up":
            template = IntraqTemplates.get_follow_up_template()
        else:
            raise HTTPException(status_code=400, detail="Invalid template type")

        # Send emails
        results = await email_service.send_bulk_emails(
            contacts=request.contacts,
            template=template,
            batch_size=request.batch_size
        )

        # Calculate stats
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        return EmailResponse(
            success=True,
            message=f"Email campaign completed. Sent: {len(successful)}, Failed: {len(failed)}",
            results=[r.dict() for r in results],
            total_sent=len(successful),
            total_failed=len(failed)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send emails: {str(e)}")

@router.post("/api/emails/send-test")
async def send_test_email():
    """Send a test email to verify configuration"""
    test_contact = EmailContact(
        email="kinyodaniel@outlook.com",
        name="Daniel Kinyo",
        company="Test Company"
    )
    
    template = IntraqTemplates.get_introduction_template()
    
    result = await email_service.send_single_email(test_contact, template)
    
    if result.success:
        return {"success": True, 
        "message": "Test email sent successfully", 
        "message_id": result.message_id}
    else:
        raise HTTPException(status_code=500, 
            detail=f"Failed to send test email: {result.error}")

@router.get("/api/emails/templates/{template_type}")
async def get_template_preview(template_type: str,   
    current_user: dict = Depends(get_current_user)
):
    """Preview email templates"""
    if template_type == "introduction":
        template = IntraqTemplates.get_introduction_template()
    elif template_type == "follow_up":
        template = IntraqTemplates.get_follow_up_template()
    else:
        raise HTTPException(status_code=400, detail="Invalid template type")
    
    return {
        "subject": template.subject,
        "html_content": template.html_content
    }


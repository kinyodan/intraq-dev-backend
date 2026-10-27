from fastapi import FastAPI, Request, Header, Form, HTTPException, Depends, BackgroundTasks, APIRouter, Query, UploadFile, File, WebSocket, WebSocketDisconnect
import json
from redis_db import init_redis_db
from datetime import datetime, timezone
from typing import Dict, Set
from services.text_extraction_service import extract_email_reply_snippet
from collections import defaultdict
import re 
import hashlib
import time

REDIS_DB = init_redis_db() if init_redis_db is not None else None


# ======================
# WEBSOCKET MANAGER
# ======================
class ConnectionManager:
    """Manages WebSocket connections grouped by client_id"""
    
    def __init__(self):
        # Dictionary mapping client_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Register a new WebSocket connection for a client_id"""
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = set()
        self.active_connections[client_id].add(websocket)
        print(f"✅ WebSocket connected: client_id={client_id}, total connections: {len(self.active_connections[client_id])}")
    
    def disconnect(self, websocket: WebSocket, client_id: str):
        """Remove a WebSocket connection"""
        if client_id in self.active_connections:
            self.active_connections[client_id].discard(websocket)
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]
            print(f"❌ WebSocket disconnected: client_id={client_id}")
    
    async def send_message_to_client(self, client_id: str, message: dict):
        """Broadcast a message to all connections for a specific client_id"""
        print(f"📡 Attempting broadcast to client_id={client_id}")
        print(f"📡 Active connections: {list(self.active_connections.keys())}")
        
        if client_id not in self.active_connections:
            print(f"⚠️ No active connections for client_id={client_id}")
            return
        
        print(f"📡 Sending to {len(self.active_connections[client_id])} connection(s) for {client_id}")
        
        disconnected = set()
        for connection in self.active_connections[client_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"⚠️ Failed to send to client {client_id}: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected connections
        for conn in disconnected:
            self.active_connections[client_id].discard(conn)

ws_manager = ConnectionManager()


async def save_reply_email_to_redis(client_id: str, email_data: dict):
    if not REDIS_DB:
        error_msg = "❌ Redis not connected"
        print(error_msg) 
        return {status: False, message: error_msg}

    if not client_id:
        error_msg = "❌ client_id missing!"
        print(error_msg) 
        return {status: False, message: error_msg}   

    if not email_data:
        error_msg = "❌ email_data missing!"
        print(error_msg)        
        return {status: False, message: error_msg}

    try:
        email_key = f"client:{client_id}:sent:emails"

        summary_email_data = {
            "email_id": email_data.get("email_id"),
            "from": email_data.get("from"),
            "to": email_data.get("to"),
            "subject": email_data.get("subject"),
            "received_at": email_data.get("received_at"),
            "summary": extract_email_reply_snippet(email_data.get("full_email")),
            "created_at": datetime.utcnow().isoformat(),
            "full_email": email_data,
        }

        # 1. store email
        REDIS_DB.hset(email_key, email_data["email_id"], json.dumps(summary_email_data))

        result = await get_emails_sync(email_key)

        print(f"✅ Saved email → {email_key}")

        return result

    except Exception as e:
        print(f"❌ Failed to save email to Redis: {e}")
        return {status: False, message: e}

async def save_email_to_redis(target_inbox: str, email_data: dict):
    
    if not REDIS_DB:
        error_msg = "❌ Redis not connected"
        print(error_msg)
        return {"status": False, "message": error_msg}

    if not target_inbox:
        error_msg = "❌ target_inbox missing!"
        print(error_msg) 
        return {"status": False, "message": error_msg}  
    
    timestamp_score = time.time() 

    # try:  

    thread_id = email_data.get("thread_id") or email_data["email_id"]
    email_id = email_data["email_id"]
    current_time_str = datetime.now(timezone.utc).isoformat()

    # PRE-FORMAT HERE: Shape the data perfectly for your frontend UI right now
    summary_email_data = {
        "id": email_id,
        "name": email_data.get("from").strip().lower(),
        "email": email_data.get("from").strip().lower(),
        "subject": email_data.get("subject"),
        "text": extract_email_reply_snippet(email_data.get("full_email")),
        "date": email_data.get("received_at") or current_time_str,
        "read": False,
        "full_email": email_data.get("full_email"),
        "labels": ["meeting", "work", "important"], # Default starting tags
        "thread_id": thread_id
    }

    result_data = {"inboxes": [], "summary_email_data": summary_email_data}
    inbox_list = [target_inbox] if isinstance(target_inbox, str) else target_inbox
    
    for inbox in inbox_list:

        clean_inbox = inbox.strip().lower()
        email_hash = hashlib.sha256(clean_inbox.encode('utf-8')).hexdigest()

        clean_inbox_hash = email_hash.strip().lower()
        email_key = f"client:{clean_inbox_hash}:emails"
        thread_key = f"client:{clean_inbox_hash}:threads"
        full_email_key = f"client:{clean_inbox_hash}:full_emails"
        order_key = f"{email_key}:order"

        # 1. Store email data structures natively
        REDIS_DB.hset(email_key, email_id, json.dumps(summary_email_data))
        REDIS_DB.hset(full_email_key, email_id, json.dumps(email_data))

        order_key = f"{email_key}:order"
        REDIS_DB.zadd(order_key, {email_data["email_id"]: timestamp_score})
        
        # 3. Attach email to thread index
        existing_thread = REDIS_DB.hget(thread_key, thread_id)

        if existing_thread:
            thread_data = json.loads(existing_thread)
            if email_id not in thread_data["email_ids"]: # Avoid duplicates on retry
                thread_data["email_ids"].append(email_id)
            thread_data["updated_at"] = current_time_str
        else:
            thread_data = {
                "thread_id": thread_id,
                "email_ids": [email_id],
                "subject": email_data.get("subject"),
                "updated_at": current_time_str
            }

        REDIS_DB.hset(thread_key, thread_id, json.dumps(thread_data))

        result_data["inboxes"].append(inbox)

        print(f"✅ Saved email → {email_key}")
        print(f"✅ Updated thread → {full_email_key}")
        print(f"✅ Updated index tracking → {order_key}")

    # Return the summary data payload directly without hitting Redis again
    return {"status": True, "data": result_data}

    # except Exception as e:
    #     print(f"❌ Failed to save email to Redis: {e}")
    #     return {"status": False, "message": str(e)}


async def get_emails_by_ids(key: str, email_ids: list):
    if not email_ids:
        return []
        
    # 1. HMGET fetches values out of the Hash
    raw_emails = REDIS_DB.hmget(key, *email_ids)
    
    # 🪲 DEBUG PRINT SECTION
    print("--- DEBUGGING UPSTASH HMGET OUTBOUND DATA ---")
    print(f"Requested Email IDs from sorted set: {email_ids} (Type: {type(email_ids[0])})")
    print(f"Raw response from Upstash HMGET: {raw_emails}")
    if raw_emails:
        print(f"First element type: {type(raw_emails[0])}")
    print("---------------------------------------------")


    if not raw_emails:
        return []
        
    emails_dict = {}
    
    # 2. SAFE PACKING: Use zip() to perfectly map IDs to their data 
    # This prevents any index out of range errors regardless of list lengths
    for email_id, email_data in zip(email_ids, raw_emails):
        if email_data is not None:
            # Ensure the key is a clean string identifier
            str_id = email_id.decode("utf-8") if isinstance(email_id, bytes) else str(email_id)
            emails_dict[str_id] = email_data
            
    if not emails_dict:
        return []
        
    return normalize_emails(emails_dict)


async def get_emails_sync(key: str):
    emails = REDIS_DB.hgetall(key)

    if not emails:
        return False

    result = normalize_emails(emails)
    return result 


async def get_email(inbox: str, email_id: str):
    if not email_id:
        raise ValueError("email_id is required")
    if not inbox:
        raise ValueError("inbox is required")

    key = f"client:{inbox}:emails"
    print(f"the get_mail key is {key}")

    # 1. Fetch from Redis first
    email = REDIS_DB.hget(key,email_id)

    # 2. Check if it exists
    if not email:
        print("NO emails retrieved")
        return []

    if isinstance(email, bytes):
        email = email.decode("utf-8")

    parsed_email = json.loads(email)
    return parsed_email



def normalize_emails(emails: dict):
    normalized_emails = []

    for email_id, email in emails.items():
        parsed_email = None

        # 1. Safely handle byte string types if present
        if isinstance(email, bytes):
            email = email.decode("utf-8")
            
        # 2. Parse text string formats cleanly
        if isinstance(email, str):
            try:
                parsed_email = json.loads(email)
            except Exception as e:
                print(f"⚠️ JSON parsing failed for email ID {email_id}: {e}")
                continue 
        # 3. Direct extraction catch hook point for pre-parsed Upstash responses
        elif isinstance(email, dict):
            parsed_email = email
        else:
            print(f"⚠️ Unknown email data format for key {email_id}: {type(email)}")
            continue

        if not parsed_email:
            continue

        # 4. Universal property extraction mapping schema
        # (Checks all legacy and modern naming patterns concurrently)
        normalized_emails.append({
            "id": parsed_email.get("id") or parsed_email.get("email_id") or email_id,
            "name": parsed_email.get("name") or parsed_email.get("from"),
            "email": parsed_email.get("email") or parsed_email.get("from"),
            "subject": parsed_email.get("subject"),
            "text": parsed_email.get("text") or parsed_email.get("summary"),
            "date": parsed_email.get("date") or parsed_email.get("created_at") or parsed_email.get("received_at"),
            "read": parsed_email.get("read", False),
            "full_email": parsed_email.get("full_email", {}), #.get("full_email") if isinstance(parsed_email.get("full_email"), dict) else parsed_email.get("full_email"),
            "labels": parsed_email.get("labels", ["meeting", "work", "important"]),
        })

    print(f"✨ Successfully normalized {len(normalized_emails)} email data profiles.")
    return normalized_emails


# def normalize_emails(emails):
#     grouped = defaultdict(list)

#     for key, email in emails.items():

#         if isinstance(email, bytes):
#             email = email.decode("utf-8")

#         parsed = json.loads(email)
#         thread_id = parsed.get("thread_id") or parsed.get("email_id")

#         grouped[thread_id].append({
#             "id": parsed.get("email_id"),
#             "name": parsed.get("from"),
#             "email": parsed.get("from"),
#             "subject": parsed.get("subject"),
#             "text": parsed.get("summary"),
#             "date": parsed.get("received_at"),
#             "read": False,
#             "labels": ["meeting", "work", "important"],
#             "thread_id": thread_id,
#         })

#     return [
#         {
#             "thread_id": tid,
#             "messages": msgs
#         }
#         for tid, msgs in grouped.items()
#     ]



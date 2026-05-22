from fastapi import FastAPI, Request, Header, Form, HTTPException, Depends, BackgroundTasks, APIRouter, Query, UploadFile, File, WebSocket, WebSocketDisconnect
import json
from redis_db import init_redis_db
from datetime import datetime
from typing import Dict, Set
from services.text_extraction_service import extract_email_reply_snippet
from collections import defaultdict

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


async def save_email_to_redis(client_id: str, email_data: dict):
    if not REDIS_DB:
        print("❌ Redis not connected")
        return False

    try:
        email_key = f"client:{client_id}:emails"
        thread_key = f"client:{client_id}:threads"

        thread_id = email_data.get("thread_id") or email_data["email_id"]

        summary_email_data = {
            "email_id": email_data.get("email_id"),
            "from": email_data.get("from"),
            "to": email_data.get("to"),
            "subject": email_data.get("subject"),
            "received_at": email_data.get("received_at"),
            "summary": extract_email_reply_snippet(email_data.get("full_email")),
            "created_at": datetime.utcnow().isoformat(),
            "thread_id": thread_id
        }

        clean_data = {
            k: (
                v.isoformat() if isinstance(v, datetime)
                else json.dumps(v) if isinstance(v, (dict, list))
                else str(v)
            )
            for k, v in email_data.items()
        }

        clean_data["created_at"] = datetime.utcnow().isoformat()

        # 1. store email
        REDIS_DB.hset(email_key, email_data["email_id"], json.dumps(summary_email_data))

        # 2. attach email to thread index (NOT duplicate email)
        existing_thread = REDIS_DB.hget(thread_key, thread_id)

        if existing_thread:
            thread_data = json.loads(existing_thread)
            thread_data["email_ids"].append(email_data["email_id"])
        else:
            thread_data = {
                "thread_id": thread_id,
                "email_ids": [email_data["email_id"]],
                "subject": email_data.get("subject"),
                "updated_at": datetime.utcnow().isoformat()
            }

        REDIS_DB.hset(thread_key, thread_id, json.dumps(thread_data))

        result = await get_emails_sync(email_key)

        print(f"✅ Saved email → {email_key}")
        print(f"✅ Updated thread → {thread_id}")

        return result

    except Exception as e:
        print(f"❌ Failed to save email to Redis: {e}")
        return False

async def get_emails_sync(key: str):
    emails = REDIS_DB.hgetall(key)

    if not emails:
        return {"data": False}

    result = normalize_emails(emails)
    return result 

def normalize_emails(emails):
    normalized_emails = []

    for key, email in emails.items():

        if isinstance(email, bytes):
            email = email.decode("utf-8")

        parsed_email = json.loads(email)

        normalized_emails.append({
            "id": parsed_email.get("email_id"),
            "name": parsed_email.get("from"),
            "email": parsed_email.get("from"),
            "subject": parsed_email.get("subject"),
            "text": parsed_email.get("summary"),
            "date": parsed_email.get("created_at"),
            "read": False,
            "full_data": emails,
            "labels": ["meeting", "work", "important"],
        })

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
from fastapi import FastAPI, Request, Header, Form, HTTPException, Depends, BackgroundTasks, APIRouter, Query, UploadFile, File, WebSocket, WebSocketDisconnect
import json
from redis_db import init_redis_db
from datetime import datetime
from typing import Dict, Set

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
        # email_key = f"client:{client_id}:emails:{email_data.get('from', 'unknown')}:{email_data["email_id"]}"
        #email_key = f"client:{client_id}:email:{email_data['email_id']}"
        email_key = f"client:{client_id}:emails"
        
        # Prepare clean data
        clean_data = {}
        for key, value in email_data.items():
            if isinstance(value, (dict, list)):
                clean_data[key] = json.dumps(value, default=str)
            elif isinstance(value, datetime):
                clean_data[key] = value.isoformat()
            else:
                clean_data[key] = str(value)

        clean_data["saved_at"] = datetime.utcnow().isoformat()

        # ✅ Correct syntax for older redis-py (v4 and below)
        for field, value in clean_data.items():
            REDIS_DB.hset(email_key, email_data["email_id"], json.dumps(clean_data))
            # REDIS_DB.hset(email_key, field, value)

        result = await get_emails_sync(f"client:{client_id}:email") 
        print(f"✅ Email saved successfully to Redis → {email_key}")
        return result

    except Exception as e:
        print(f"❌ Failed to save email to Redis: {e}")
        return False


async def get_emails_sync(key: str):
    emails = REDIS_DB.hgetall(key)
    print(len("get_emails_sync"))
    print(len(emails))

    if not emails:
        return {"data": False}
  
    return emails 


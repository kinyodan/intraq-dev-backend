# ======================
# WEBSOCKET MANAGER
from core.imports import *

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

# Global connection manager
ws_manager = ConnectionManager()

# app/services/message_service.py 內，或 app/core/websocket_manager.py

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)

# 連線管理器：維護 'room_id' -> List[Tuple[user_id, WebSocket]] 的映射
class ConnectionManager:
    """管理 WebSocket 連線：用於廣播訊息給特定 Room 的所有連線。"""
    
    def __init__(self):
        # 結構: {room_id: [(user_id, WebSocket)]}
        self.active_connections: Dict[str, List[Tuple[str, WebSocket]]] = {}

    async def connect(self, room_id: str, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append((user_id, websocket))
        logging.info(f"User {user_id} connected to Room {room_id}. Total connections: {len(self.active_connections[room_id])}")

    def disconnect(self, room_id: str, user_id: str, websocket: WebSocket):
        try:
            self.active_connections[room_id].remove((user_id, websocket))
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
            logging.info(f"User {user_id} disconnected from Room {room_id}. Remaining connections: {self.active_connections.get(room_id, '0')}")
        except ValueError:
            pass # 可能是重複斷開

    async def broadcast_message(self, room_id: str, message: str):
        """將訊息廣播給特定 Room 的所有連線。"""
        if room_id in self.active_connections:
            for _, connection in self.active_connections[room_id]:
                await connection.send_text(message)

# 實例化管理器
manager = ConnectionManager()
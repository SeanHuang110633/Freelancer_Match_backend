import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.message import Message

# --- (關鍵修正) 使用 Async 版本的 WebSocket Client ---
from httpx_ws import aconnect_ws 
from httpx_ws.transport import ASGIWebSocketTransport
from app.main import app 

@pytest.mark.asyncio
async def test_chat_room_and_websocket_flow(
    client: AsyncClient,
    employer_auth_headers: dict,
    freelancer_auth_headers: dict,
    db_session
):
    """
    【整合測試 P2】即時通訊與 WebSocket 流程
    
    流程：
    1. (Setup) 雇主刊登案件，獲取雙方 User ID
    2. [Employer]   主動開啟聊天室 (Create Room REST API)
    3. [Freelancer] 確認聊天室列表 (List Rooms REST API)
    4. [Freelancer] 透過 WebSocket 連線並發送訊息
    5. [Freelancer] 透過 WebSocket 收到自己發送的訊息回傳 (驗證 Redis Pub/Sub)
    6. [Employer]   透過 REST API 讀取歷史訊息 (驗證 DB Persistence)
    """

    # ==========================================
    # 1. Setup: 準備資料
    # ==========================================
    # 1-1. 建立案件
    resp_proj = await client.post(
        "/projects/",
        headers=employer_auth_headers,
        json={"title": "Chat Project", "description": "Let's chat", "budget_min": 1000}
    )
    project_id = resp_proj.json()["project_id"]

    # 1-2. 獲取 User ID (建立聊天室需要知道對方的 ID)
    resp_emp = await client.get("/users/me", headers=employer_auth_headers)
    employer_id = resp_emp.json()["user_id"]

    resp_free = await client.get("/users/me", headers=freelancer_auth_headers)
    freelancer_id = resp_free.json()["user_id"]

    # ==========================================
    # 2. 建立聊天室 (Create Room - REST)
    # ==========================================
    # 模擬：雇主在瀏覽工作者履歷後，點擊 "Say Hi"
    room_payload = {
        "project_id": project_id,
        "invited_user_id": freelancer_id
    }
    resp_room = await client.post(
        "/messages/rooms",
        headers=employer_auth_headers,
        json=room_payload
    )
    assert resp_room.status_code == 201
    room_data = resp_room.json()
    room_id = room_data["room_id"]
    
    # 驗證參與者是否正確
    participants = room_data["participants"]
    assert len(participants) == 2
    participant_ids = [p["user_id"] for p in participants]
    assert employer_id in participant_ids
    assert freelancer_id in participant_ids

    # ==========================================
    # 3. 獲取聊天室列表 (List Rooms - REST)
    # ==========================================
    # 驗證工作者也能看到這個新聊天室
    resp_list = await client.get("/messages/rooms", headers=freelancer_auth_headers)
    assert resp_list.status_code == 200
    rooms = resp_list.json()
    assert len(rooms) >= 1
    # 確保剛剛建立的房間在列表中
    assert any(r["room_id"] == room_id for r in rooms)

    # ==========================================
    # 4. WebSocket 通訊 (Send & Receive)
    # ==========================================
    
    freelancer_token = freelancer_auth_headers["Authorization"].split(" ")[1]
    
    # WebSocket URL
    ws_url = f"ws://test/messages/ws/{room_id}?token={freelancer_token}"

    # (修改) 建立一個專用的 WebSocket Client
    # 我們不能復用 fixture 的 'client'，因為它的 transport 是普通的 ASGITransport，不支援 WS
    # 我們需要一個使用 ASGIWebSocketTransport 的 client
    async with AsyncClient(transport=ASGIWebSocketTransport(app), base_url="ws://test") as ws_client:
        
        # (修改) 將 client 傳給 aconnect_ws
        async with aconnect_ws(ws_url, client=ws_client) as ws:
            
            # A. 發送訊息 (Send)
            msg_content = "Hello Employer! This is a WS test."
            await ws.send_json({"content": msg_content})
            
            # B. 接收回傳 (Receive)
            received_data = await ws.receive_json()
            
            # 驗證回傳格式
            assert received_data["content"] == msg_content
            assert received_data["sender_id"] == freelancer_id
            assert received_data["room_id"] == room_id
            assert "created_at" in received_data

    # ==========================================
    # 5. 驗證訊息入庫 (Check History - REST)
    # ==========================================
    # 雇主透過 API 查看歷史訊息
    resp_history = await client.get(
        f"/messages/{room_id}/messages", 
        headers=employer_auth_headers
    )
    assert resp_history.status_code == 200
    msgs = resp_history.json()
    
    # 應該要有一條訊息
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Hello Employer! This is a WS test."
    
    # 雙重驗證：直接查 DB
    stmt = select(Message).where(Message.room_id == room_id)
    result = await db_session.execute(stmt)
    db_msgs = result.scalars().all()
    assert len(db_msgs) == 1
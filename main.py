"""
CN2026 HW5 - Integrated Web Messenger Application
Run with: py -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os, json, asyncio, hashlib, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List

import aiofiles
import httpx
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException,
    UploadFile, File, Form, Request, status
)
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from jose import JWTError, jwt

import database as db

# ── Config ─────────────────────────────────────────────────────────────────
SECRET_KEY = "cn2026-hw5-secret-key-change-in-production"
ALGORITHM  = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24   # 1 day

UPLOAD_DIR  = Path("uploads")
VIDEO_PATH  = Path("static/sample.mp4")   # place your video here
OLLAMA_URL  = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="CN2026 HW5 Messenger")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static",  StaticFiles(directory="static"),  name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

UPLOAD_DIR.mkdir(exist_ok=True)

# ── Startup ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    db.init_db()

# ── Auth helpers ─────────────────────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return pwd_ctx.hash(pw)

def verify_pw(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_token(username: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None

def get_current_user(request: Request) -> str:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    return username

# ── WebSocket manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}   # username → ws

    async def connect(self, username: str, ws: WebSocket):
        await ws.accept()
        self.active[username] = ws
        db.set_online(username, True)
        await self.broadcast_user_list()

    def disconnect(self, username: str):
        self.active.pop(username, None)
        db.set_online(username, False)

    async def send_to(self, username: str, data: dict):
        ws = self.active.get(username)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                pass

    async def broadcast_user_list(self):
        users = db.get_all_users()
        payload = {"type": "user_list", "users": users}
        for ws in self.active.values():
            try:
                await ws.send_json(payload)
            except Exception:
                pass

manager = ConnectionManager()

# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("static/index.html")

# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post("/api/signup")
async def signup(username: str = Form(...), password: str = Form(...)):
    if db.get_user(username):
        raise HTTPException(400, "Username already exists")
    db.create_user(username, hash_pw(password))
    return {"message": "Account created"}

@app.post("/api/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = db.get_user(username)
    if not user or not verify_pw(password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(username)
    resp = JSONResponse({"message": "Login successful", "username": username})
    resp.set_cookie("access_token", token, httponly=True, max_age=86400)
    return resp

@app.post("/api/logout")
async def logout(username: str = Depends(get_current_user)):
    manager.disconnect(username)
    resp = JSONResponse({"message": "Logged out"})
    resp.delete_cookie("access_token")
    await manager.broadcast_user_list()
    return resp

@app.get("/api/me")
async def me(username: str = Depends(get_current_user)):
    return {"username": username}

# ── Users & Chat ──────────────────────────────────────────────────────────────
@app.get("/api/users")
async def users(username: str = Depends(get_current_user)):
    return db.get_all_users()

@app.get("/api/messages/{peer}")
async def get_messages(peer: str, username: str = Depends(get_current_user)):
    return db.get_messages(username, peer)

# ── File upload ───────────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    receiver: str = Form(...),
    username: str = Depends(get_current_user)
):
    safe_name = f"{int(time.time())}_{file.filename}"
    dest = UPLOAD_DIR / safe_name
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)

    msg = db.save_message(
        sender=username, receiver=receiver,
        content=f"[FILE]{safe_name}|{file.filename}",
        msg_type="file"
    )
    payload = {
        "type": "message",
        "id": msg["id"],
        "sender": username,
        "receiver": receiver,
        "content": msg["content"],
        "msg_type": "file",
        "timestamp": msg["timestamp"]
    }
    await manager.send_to(receiver, payload)
    await manager.send_to(username, payload)
    return {"message": "File uploaded", "filename": safe_name}

# ── Weather ───────────────────────────────────────────────────────────────────
@app.get("/api/weather")
async def weather(city: str = "Seoul"):
    # Use Open-Meteo (free, no API key needed)
    # First get lat/lon from geocoding, then fetch weather
    async with httpx.AsyncClient(timeout=10) as client:
        geo = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"}
        )
        geo_data = geo.json()
        if not geo_data.get("results"):
            raise HTTPException(404, f"City '{city}' not found")

        r = geo_data["results"][0]
        lat, lon = r["latitude"], r["longitude"]

        wx = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weathercode,windspeed_10m,relative_humidity_2m",
                "timezone": "auto"
            }
        )
        wx_data = wx.json()
        current = wx_data.get("current", {})

    code = current.get("weathercode", 0)
    desc = _wx_code(code)
    return {
        "city": r["name"],
        "temp": current.get("temperature_2m"),
        "unit": "°C",
        "description": desc,
        "wind": current.get("windspeed_10m"),
        "humidity": current.get("relative_humidity_2m"),
        "icon": _wx_icon(code)
    }

def _wx_code(code: int) -> str:
    if code == 0: return "Clear sky"
    if code <= 3: return "Partly cloudy"
    if code <= 9: return "Cloudy"
    if code <= 19: return "Foggy"
    if code <= 29: return "Drizzle"
    if code <= 39: return "Rain"
    if code <= 49: return "Snow"
    if code <= 59: return "Sleet"
    if code <= 69: return "Thunderstorm"
    return "Unknown"

def _wx_icon(code: int) -> str:
    if code == 0: return "☀️"
    if code <= 3: return "⛅"
    if code <= 9: return "☁️"
    if code <= 19: return "🌫️"
    if code <= 39: return "🌧️"
    if code <= 49: return "❄️"
    if code <= 59: return "🌨️"
    return "⛈️"

# ── Video streaming ───────────────────────────────────────────────────────────
@app.get("/api/video")
async def video(request: Request):
    """
    Range-request-aware video streaming.
    Place your MP4 at static/sample.mp4
    """
    if not VIDEO_PATH.exists():
        raise HTTPException(404, "Video file not found. Place sample.mp4 in the static/ folder.")
    return FileResponse(VIDEO_PATH, media_type="video/mp4",
                        headers={"Accept-Ranges": "bytes"})

# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/{username}")
async def websocket_endpoint(ws: WebSocket, username: str):
    # Validate token from cookie (ws doesn't support Depends easily)
    token = ws.cookies.get("access_token")
    if not token or decode_token(token) != username:
        await ws.close(code=4001)
        return

    await manager.connect(username, ws)
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                receiver = data["receiver"]
                content  = data["content"]

                # Ollama AI assistant
                if receiver == "Ollama":
                    msg = db.save_message(username, "Ollama", content, "text")
                    await manager.send_to(username, {
                        "type": "message", **msg
                    })
                    reply = await _ollama_reply(content)
                    ai_msg = db.save_message("Ollama", username, reply, "text")
                    await manager.send_to(username, {
                        "type": "message", **ai_msg
                    })
                else:
                    msg = db.save_message(username, receiver, content, "text")
                    payload = {"type": "message", **msg}
                    await manager.send_to(receiver, payload)
                    await manager.send_to(username, payload)

    except WebSocketDisconnect:
        manager.disconnect(username)
        await manager.broadcast_user_list()

# ── Ollama helper ─────────────────────────────────────────────────────────────
async def _ollama_reply(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            })
            return resp.json().get("response", "Sorry, I could not generate a response.")
    except Exception as e:
        return f"[Ollama unavailable: {e}]"

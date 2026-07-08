# CN2026 HW5 — Integrated Web Messenger Application
**Student:** Minsoo Bae (2022310865)

---

## How This Project Integrates Previous Homeworks

| HW | Concept | Used In This Project |
|----|---------|----------------------|
| HW1 | TCP/UDP client-server communication | FastAPI HTTP server + WebSocket real-time messaging |
| HW2 | Authenticated multi-client chatting | User auth (bcrypt hashing, JWT sessions), multi-user WebSocket manager |
| HW4 | Video streaming | Server-side MP4 streaming via HTTP range requests |

---

## Project Structure

```
hw5_app/
├── main.py           ← FastAPI backend (all API endpoints + WebSocket)
├── database.py       ← SQLite helpers (users, messages, files tables)
├── requirements.txt  ← Python dependencies
├── static/
│   ├── index.html    ← Single-page frontend (HTML + CSS + JS)
│   └── sample.mp4    ← ⚠️  Place your video file here (not included)
├── uploads/          ← Uploaded files stored here (auto-created)
└── db/
    └── messenger.db  ← SQLite database (auto-created on first run)
```

---

## Setup & Run Instructions

### 1. Install Python dependencies
```bash
py -m pip install -r requirements.txt

py -m pip install bcrypt==3.2.2
```

### 2. (Optional) Install Ollama for AI assistant
```bash
# Install Ollama from below website for WINDOWS
https://ollama.com/download

# Pull the recommended model
ollama pull llama3.2:3b

# Start Ollama server (in a separate terminal)
ollama serve
```
> If Ollama is not running, the AI assistant will return an error message but the rest of the app works normally.

### 3. Place your video file
Copy any `.mp4` file to `static/sample.mp4`. The name is the mp4 file should be sample.mp4
```bash
cp /path/to/your/video.mp4 static/sample.mp4
```

### 4. Start the server
```bash
py -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Open the app
Navigate to: **http://localhost:8000**

To simulate multiple clients, open the URL in multiple browser windows / incognito tabs.
**Do not open URL in same browser account**
For example, open one account in a normal browser account(ex: google) and then open another in incognito and another in another browser(ex: mozilla firefox)

---

## Features

### User Authentication
- Sign up / Login / Logout via the auth overlay
- Passwords stored as **bcrypt hashes** in SQLite
- Sessions managed with **JWT tokens** stored in HttpOnly cookies

### Messenger-style User List
- Shows all registered users
- 🟢 Green dot = Online, ⚫ Gray dot = Offline
- Status updates in real-time via WebSocket broadcast
- Search/filter box to find contacts quickly

### Real-time Chat
- Select any user from the sidebar to open a conversation
- Messages delivered instantly using **WebSocket**
- Full chat history persisted in SQLite and shown on reopen

### File Transfer
- Click 📎 to attach any file
- Files saved on the server under `uploads/`
- Receiver sees a download link in the chat bubble

### Video Streaming Room
- Click **▶️ Video Streaming Room** in the sidebar
- Server streams `static/sample.mp4` via HTTP range requests
- Any number of users can open the room simultaneously

### Ollama AI Assistant
- "Ollama" always appears online in the user list
- Chatting with Ollama sends your message to the local Ollama API (`llama3.2:3b`)
- Response is displayed as a chat bubble

### Weather API
- Weather for Seoul shown in the top-right corner
- Data fetched from **Open-Meteo** (free, no API key needed)
- Your server acts as a proxy: Browser → Your Server → Open-Meteo API
- Refreshes every 10 minutes

---

## Database Schema

### `users` table
| Column | Type | Description |
|--------|------|-------------|
| username | TEXT PK | Unique username |
| password_hash | TEXT | bcrypt hash |
| is_online | INTEGER | 0 or 1 |
| created_at | TEXT | ISO timestamp |

### `messages` table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| sender | TEXT | Sender username |
| receiver | TEXT | Receiver username |
| content | TEXT | Message text or file reference |
| msg_type | TEXT | 'text' or 'file' |
| timestamp | TEXT | ISO timestamp |

### `files` table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| uploader | TEXT | Who uploaded |
| receiver | TEXT | Intended recipient |
| filename | TEXT | Server-side stored name |
| orig_name | TEXT | Original file name |
| uploaded_at | TEXT | ISO timestamp |

# P-013 — Vinpearl Multilingual Travel Agent

> README này là hướng dẫn setup local cho thành viên mới sau khi clone/pull source về.
>
> Kiến trúc local hiện tại:
>
> - **Frontend:** React + Vite, chạy trên máy host tại `http://localhost:5173`
> - **Backend:** FastAPI + LangGraph, khuyến nghị chạy Docker tại `http://localhost:8000`
> - **PostgreSQL:** chạy trên Windows host
> - **Redis:** chạy bằng Docker Compose
> - **Chroma:** lưu trong Docker named volume `/app/storage/chroma_local`
> - **Embedding:** `intfloat/multilingual-e5-small`
> - **LLM:** cấu hình qua `.env`
> - **Chat memory:** lưu PostgreSQL (`app.session`, `app.message`), không dùng JSONL làm memory chính
> - **Lịch sử chat UI:** chỉ hiển thị cho user đã đăng nhập

---

# 1. Quick Start — Thành viên mới pull code về

## 1.1. Yêu cầu cài sẵn

Mỗi máy cần:

- Git
- Python **3.11**
- Node.js + npm
- PostgreSQL
- Docker Desktop
- PowerShell

Kiểm tra nhanh:

```powershell
git --version
py -3.11 --version
node --version
npm --version
docker --version
docker compose version
```

PostgreSQL phải đang chạy và thường dùng port:

```text
5432
```

---

## 1.2. Clone project

```powershell
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-013.git
cd P-013
```

Nếu project đã tồn tại:

```powershell
git status
git fetch origin
git pull
```

> Không `git reset --hard` nếu đang có code chưa commit.

---

# 2. Python Environment

Tại **root project `P-013`**:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Kiểm tra:

```powershell
python --version
```

Kỳ vọng:

```text
Python 3.11.x
```

---

# 3. Tạo file `.env`

Tạo `.env` tại **root project**.

Có thể bắt đầu bằng:

```powershell
Copy-Item .env.example .env
```

Sau đó cập nhật các biến cần thiết.

Ví dụ cấu hình local hiện tại:

```env
# =========================
# LLM
# =========================
LLM_PROVIDER=gemini
LLM_MODEL=gemini/gemini-3.5-flash-lite
LLM_API_KEY=<YOUR_LLM_API_KEY>
LLM_API_KEY_BACKUP=

LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=1500
LLM_TIMEOUT=60
LLM_MAX_RETRIES=2

# =========================
# Embedding
# =========================
LOCAL_EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=128

# Optional: public model normally does not require token
HF_TOKEN=

# =========================
# RAG
# =========================
TOP_K=5
MAX_CONTEXT_CHARS=12000
MIN_RELEVANCE_SCORE=0.35
CHROMA_COLLECTION=vinpearl_multilingual_e5_small

# =========================
# Startup
# =========================
RUN_MIGRATIONS=true
BOOTSTRAP_CORE_DATA=false
REBUILD_CHROMA_ON_START=false

# =========================
# Auth
# =========================
ADMIN_BOOTSTRAP_KEY=<YOUR_ADMIN_BOOTSTRAP_KEY>
AUTH_SESSION_DAYS=7
PASSWORD_PBKDF2_ITERATIONS=600000

# =========================
# API
# =========================
AGENT_API_KEY=dev-local-secret-key

# =========================
# Frontend
# =========================
VITE_API_BASE_URL=http://localhost:8000

# =========================
# App
# =========================
APP_ENV=development
LOG_LEVEL=INFO
```

> **Không commit `.env` có secret thật lên GitHub.**

---

# 4. PostgreSQL Local

## 4.1. Kiến trúc database

Backend Docker truy cập PostgreSQL trên Windows bằng:

```text
host.docker.internal:5432
```

Backend chạy trực tiếp trên Windows dùng:

```text
localhost:5432
```

Database mặc định:

```text
database: vinpearl
user:     vinpearl
```

---

## 4.2. Tạo PostgreSQL user và database

Ví dụ với PostgreSQL 18:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" `
  -U postgres `
  -c "CREATE USER vinpearl WITH PASSWORD '<POSTGRES_PASSWORD>';"
```

Tạo database:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" `
  -U postgres `
  -c "CREATE DATABASE vinpearl OWNER vinpearl;"
```

Nếu role/database đã tồn tại thì không cần tạo lại.

Kiểm tra kết nối:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" `
  -U vinpearl `
  -d vinpearl `
  -h localhost
```

---

## 4.3. QUAN TRỌNG — `DATABASE_URL`

### Nếu backend chạy trực tiếp trên Windows

Trong `.env`:

```env
DATABASE_URL=postgresql+pg8000://vinpearl:<POSTGRES_PASSWORD>@localhost:5432/vinpearl
```

### Nếu backend chạy Docker

`docker-compose.yml` hiện cấu hình backend kết nối PostgreSQL qua:

```text
host.docker.internal:5432
```

Mỗi thành viên phải kiểm tra `DATABASE_URL` trong `docker-compose.yml` và bảo đảm:

- username đúng
- password đúng PostgreSQL trên máy đó
- database là `vinpearl`
- host là `host.docker.internal`

Ví dụ cấu trúc:

```text
postgresql+pg8000://vinpearl:<POSTGRES_PASSWORD>@host.docker.internal:5432/vinpearl
```

> Không commit password cá nhân lên Git.

---

# 5. Kiểm tra ORM / Alembic

ORM hiện nằm tại:

```text
src/data_postgre/db
```

Kiểm tra metadata:

```powershell
python -c "from src.data_postgre.db import Base, AppBase; print('CORE:', len(Base.metadata.tables)); print('APP:', len(AppBase.metadata.tables))"
```

Kiểm tra Alembic:

```powershell
alembic current
```

Xem migration head:

```powershell
alembic heads
```

Chạy migration:

```powershell
alembic upgrade head
```

> Khi backend chạy Docker, entrypoint mặc định cũng tự chạy `alembic upgrade head` vì `RUN_MIGRATIONS=true`.

---

# 6. Setup dữ liệu PostgreSQL

Project có 2 bước dữ liệu:

```text
seed destination
        ↓
load Core business data
        ↓
PostgreSQL
```

Chạy:

```powershell
python -m scripts.seed_destinations
python -m scripts.load_core
```

`load_core` được thiết kế idempotent/upsert, tuy nhiên không cần chạy lại mỗi lần mở project nếu dữ liệu nguồn không đổi.

---

# 7. Chroma Vector Store

## 7.1. Nguyên tắc hiện tại

Document business được embedding khi ingest:

```text
PostgreSQL data
      ↓
chunk
      ↓
embed_documents()
      ↓
Chroma
```

Khi user chat:

```text
user query
    ↓
embed_query()
    ↓
so sánh với vector document đã lưu
```

Runtime **không embedding lại toàn bộ candidate documents**.

Điều này giảm latency đáng kể mà không thay đổi dữ liệu vector đã ingest.

---

## 7.2. Nếu chạy backend trực tiếp trên Windows

Sau khi PostgreSQL có dữ liệu:

```powershell
python -m src.backend.services.ingest_postgres --reset
```

Chroma sẽ nằm tại:

```text
./storage/chroma_local
```

---

## 7.3. Nếu chạy backend bằng Docker — lưu ý rất quan trọng

Docker dùng named volume:

```text
chroma_data:/app/storage
```

và Chroma nằm trong container tại:

```text
/app/storage/chroma_local
```

Vì vậy **không nên chỉ ingest Chroma trên Windows host rồi mong Docker nhìn thấy**.

Sau khi container `agent` đã chạy, ingest trực tiếp trong container:

```powershell
docker compose exec agent python -m src.backend.services.ingest_postgres --reset
```

Kiểm tra số document:

```powershell
docker compose exec agent python -c "import os,chromadb; p=os.getenv('CHROMA_DIR'); n=os.getenv('CHROMA_COLLECTION'); c=chromadb.PersistentClient(path=p).get_collection(name=n); print('Documents:', c.count())"
```

Kỳ vọng:

```text
Documents: > 0
```

---

# 8. Cách chạy khuyến nghị — Docker Backend + Local Frontend

Đây là cách local hiện tại nên dùng cho cả team.

```text
React/Vite trên Windows
        |
        v
FastAPI Backend trong Docker
        |
        +--> PostgreSQL Windows
        |
        +--> Redis Docker
        |
        +--> Chroma Docker Volume
```

---

## 8.1. Build backend image

`docker-compose.yml` dùng image:

```text
p013-backend:latest
```

Do đó khi mới pull source hoặc backend có code mới, build bằng:

```powershell
docker build -t p013-backend:latest .
```

> Không chỉ chạy `docker compose build`, vì service `agent` hiện dùng image đã đặt tên sẵn.

---

## 8.2. Start Backend + Redis

```powershell
docker compose up -d
```

Kiểm tra:

```powershell
docker compose ps
```

Xem log:

```powershell
docker compose logs -f agent
```

Redis:

```powershell
docker compose logs -f redis
```

---

## 8.3. Setup dữ liệu lần đầu cho máy mới

Sau khi `agent` chạy:

```powershell
docker compose exec agent python -m scripts.seed_destinations
docker compose exec agent python -m scripts.load_core
docker compose exec agent python -m src.backend.services.ingest_postgres --reset
```

Sau lần đầu:

- không cần seed mỗi ngày
- không cần load Core mỗi ngày
- không cần rebuild Chroma mỗi ngày

---

## 8.4. Start Frontend

### QUAN TRỌNG

`package.json` và `vite.config.js` nằm ở **root repo**.

`vite.config.js` đã cấu hình:

```text
root = src/frontend
```

Vì vậy chạy npm tại:

```text
P-013\
```

**Không cần `cd src/frontend`.**

Lần đầu:

```powershell
npm install
```

Chạy FE:

```powershell
npm run dev
```

Frontend:

```text
http://localhost:5173
```

Backend:

```text
http://localhost:8000
```

---

# 9. Cách chạy Backend trực tiếp trên Windows — Optional

Chỉ dùng khi cần debug Python không qua Docker.

Trong `.env`:

```env
DATABASE_URL=postgresql+pg8000://vinpearl:<POSTGRES_PASSWORD>@localhost:5432/vinpearl
REDIS_URL=redis://localhost:6379/0
CHROMA_DIR=./storage/chroma_local
```

Start Redis riêng:

```powershell
docker compose up -d redis
```

Sau đó:

```powershell
.venv\Scripts\activate
python -m uvicorn src.backend.main:app --reload --port 8000
```

Nếu Chroma host chưa có:

```powershell
python -m src.backend.services.ingest_postgres --reset
```

---

# 10. Backend URLs

Backend:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

Health:

```text
GET /health
```

Ready:

```text
GET /ready
```

Main chat API:

```text
POST /api/v1/chat
```

Compatibility API cho bài CP5:

```text
POST /ask
```

---

# 11. Kiểm tra Backend

## 11.1. Health

```powershell
python -c "import httpx; r=httpx.get('http://localhost:8000/health'); print(r.status_code); print(r.text)"
```

Kỳ vọng:

```text
200
{"status":"ok"}
```

---

## 11.2. Ready

```powershell
python -c "import httpx; r=httpx.get('http://localhost:8000/ready'); print(r.status_code); print(r.text)"
```

Kỳ vọng:

```text
200
{"status":"ready"}
```

Nếu `/ready` trả `503`:

```powershell
docker compose ps
docker compose logs redis
```

---

## 11.3. Test main Chat API

```powershell
$body = @{
  message = "Xin chào"
  session_id = $null
  user_id = $null
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/chat" `
  -ContentType "application/json" `
  -Body $body
```

Kỳ vọng có:

```text
answer
session_id
language
route
sources
```

---

## 11.4. Test `/ask`

```powershell
python -c "import httpx; r=httpx.post('http://localhost:8000/ask', headers={'X-API-Key':'dev-local-secret-key'}, json={'question':'Xin chào'}); print(r.status_code); print(r.text)"
```

Kỳ vọng HTTP `200`.

---

# 12. Authentication

Auth API:

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me
POST /api/v1/auth/logout
```

User đăng nhập nhận:

```text
access_token
```

Frontend gửi token theo:

```text
Authorization: Bearer <TOKEN>
```

---

# 13. Tạo Admin đầu tiên

Lấy `ADMIN_BOOTSTRAP_KEY` từ `.env`.

```powershell
$body = @{
  name = "P013 Admin"
  email = "admin@example.com"
  phone = $null
  password = "ChangeThisPassword123!"
  locale = "vi"
  bootstrap_key = "<ADMIN_BOOTSTRAP_KEY>"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/auth/bootstrap-admin" `
  -ContentType "application/json" `
  -Body $body
```

Chỉ bootstrap được khi hệ thống chưa có admin.

Trang quản lý nhân viên:

```text
/admin/staff
```

---

# 14. Chat Memory hiện tại

Chat memory hiện lưu trong PostgreSQL:

```text
app.session
app.message
app.event_log
```

Không còn dùng:

```text
storage/chat_history.jsonl
```

làm nguồn memory chính.

Nếu file JSONL legacy vẫn tồn tại trong volume, đó chỉ là dữ liệu cũ.

---

## 14.1. Kiểm tra sessions

Trong PostgreSQL:

```sql
SELECT
    id,
    user_id,
    channel,
    language,
    started_at,
    last_activity_at
FROM app.session
ORDER BY last_activity_at DESC;
```

---

## 14.2. Kiểm tra messages

```sql
SELECT
    session_id,
    seq,
    role,
    content,
    language,
    route,
    created_at
FROM app.message
ORDER BY created_at DESC;
```

Một turn thường tạo:

```text
seq 1  user
seq 2  assistant
```

Turn tiếp theo:

```text
seq 3  user
seq 4  assistant
```

---

# 15. Lịch sử chat theo tài khoản

## 15.1. Anonymous user

User chưa đăng nhập:

- vẫn chat bình thường
- vẫn có memory cho phiên hiện tại
- **không hiển thị sidebar lịch sử**
- không được gọi API lịch sử của tài khoản

---

## 15.2. Logged-in user

User đã đăng nhập:

- session gắn `app.session.user_id`
- sidebar hiển thị các phiên của chính user
- click phiên cũ sẽ load message từ PostgreSQL
- `New chat` tạo session mới
- **không xóa session cũ**
- logout sẽ clear active session khỏi browser
- user A không được đọc session của user B

History API:

```text
GET /api/v1/chat/sessions
GET /api/v1/chat/sessions/{session_id}/messages
```

Xóa một history thuộc chính user:

```text
DELETE /api/v1/chat/{session_id}/history
```

Các endpoint history yêu cầu:

```text
Authorization: Bearer <TOKEN>
```

---

# 16. Test lịch sử chat sau đăng nhập

Login:

```powershell
$body = @{
  identifier = "user@example.com"
  password = "YourPassword123!"
} | ConvertTo-Json

$login = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/auth/login" `
  -ContentType "application/json" `
  -Body $body

$token = $login.access_token
```

Headers:

```powershell
$headers = @{
  Authorization = "Bearer $token"
}
```

Lấy danh sách session:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://localhost:8000/api/v1/chat/sessions" `
  -Headers $headers
```

Lấy message của một session:

```powershell
$sessionId = "<SESSION_ID>"

Invoke-RestMethod `
  -Method Get `
  -Uri "http://localhost:8000/api/v1/chat/sessions/$sessionId/messages" `
  -Headers $headers
```

---

# 17. Multilingual Agent hiện tại

Luồng ngôn ngữ:

```text
user_message bất kỳ ngôn ngữ
        ↓
language/control
        ↓
English rag_query
        ↓
RAG + support routing
        ↓
trả lời theo ngôn ngữ user
```

Support triage dùng:

```text
user_message gốc
+
English rag_query
```

để tránh trường hợp cùng một ý nghĩa nhưng tiếng Việt chạy đúng còn tiếng Trung/Nhật/Hàn/Pháp/Đức... chạy sai route.

Các static template tối ưu trực tiếp hiện có cho:

```text
vi
en
zh
ja
ko
```

Ngôn ngữ khác vẫn có LLM fallback.

---

# 18. Conditional LLM Optimization

Agent không còn cố định gọi tất cả LLM nodes cho mọi câu.

Nguyên tắc:

```text
case rõ
→ deterministic fast-path

case mơ hồ
→ gọi thêm LLM judge
```

Ví dụ:

```text
Greeting
→ ít LLM call

Travel query rõ
→ control + answer + grounding

Support rõ cần nhân viên
→ đi thẳng ticket, không assessment dư

Support mơ hồ
→ LLM triage
```

Mục tiêu là giảm latency nhưng vẫn giữ:

- answer generation
- grounding validation
- fallback LLM cho case khó
- multilingual behavior

---

# 19. RAG Performance Optimization

Runtime hiện tại:

```text
Document embedding
→ chỉ làm lúc ingest/rebuild Chroma

Query embedding
→ vẫn chạy mỗi câu hỏi

Candidate document
→ reuse embedding đã lưu trong Chroma
```

Không chạy lại:

```text
embed_documents(candidate_texts)
```

mỗi request.

Nếu dữ liệu business thay đổi, chạy lại:

```powershell
docker compose exec agent python -m src.backend.services.ingest_postgres --reset
```

---

# 20. Khi nào phải rebuild Chroma?

Cần rebuild khi:

- dữ liệu PostgreSQL business thay đổi đáng kể
- chunk content thay đổi
- đổi embedding model
- Chroma volume bị xóa
- collection bị corrupt/mất

Không cần rebuild khi chỉ:

- sửa FE
- sửa prompt
- sửa routing
- sửa auth
- sửa history UI
- restart container

---

# 21. Khi pull code mới mỗi ngày

Quy trình thông thường:

```powershell
git pull
```

Activate Python env nếu cần:

```powershell
.venv\Scripts\activate
```

Nếu `requirements.txt` thay đổi:

```powershell
python -m pip install -r requirements.txt
```

Nếu backend code thay đổi:

```powershell
docker build -t p013-backend:latest .
docker compose up -d --force-recreate agent
```

Nếu chỉ FE thay đổi:

```powershell
npm run dev
```

Vite tự reload.

Nếu migration thay đổi:

```powershell
alembic upgrade head
```

hoặc recreate backend để Docker entrypoint tự chạy migration:

```powershell
docker compose up -d --force-recreate agent
```

Nếu dữ liệu Core thay đổi:

```powershell
docker compose exec agent python -m scripts.load_core
docker compose exec agent python -m src.backend.services.ingest_postgres --reset
```

---

# 22. Docker Commands thường dùng

Start:

```powershell
docker compose up -d
```

Status:

```powershell
docker compose ps
```

Backend logs:

```powershell
docker compose logs -f agent
```

Redis logs:

```powershell
docker compose logs -f redis
```

Restart backend:

```powershell
docker compose restart agent
```

Recreate backend với image mới:

```powershell
docker compose stop agent
docker compose rm -f agent
docker compose up -d agent
```

Stop toàn bộ:

```powershell
docker compose down
```

---

## CẢNH BÁO

Không chạy tùy tiện:

```powershell
docker compose down -v
```

`-v` sẽ xóa named volumes, có thể làm mất:

- Chroma index
- Hugging Face model cache
- Redis persisted data

Nếu Chroma bị xóa thì phải ingest lại.

---

# 23. Hugging Face / Embedding model cache

Docker cấu hình:

```text
HF_HOME=/app/storage/huggingface
```

Model embedding được cache trong Docker volume.

Lần đầu chạy/ingest có thể cần tải model nên chậm hơn.

Các lần sau model vẫn nằm trong volume nếu không xóa volume.

---

# 24. Troubleshooting

## 24.1. Backend không connect PostgreSQL

Kiểm tra PostgreSQL service:

```powershell
Get-Service *postgres*
```

Kiểm tra port:

```powershell
Test-NetConnection localhost -Port 5432
```

Nếu backend Docker:

```text
host = host.docker.internal
```

Nếu backend chạy trực tiếp:

```text
host = localhost
```

Kiểm tra username/password/database trong `DATABASE_URL`.

---

## 24.2. `/ready` trả 503

Kiểm tra Redis:

```powershell
docker compose ps
docker compose logs redis
```

Test:

```powershell
docker compose exec redis redis-cli ping
```

Kỳ vọng:

```text
PONG
```

---

## 24.3. Agent trả không có dữ liệu

Kiểm tra Chroma:

```powershell
docker compose exec agent python -c "import os,chromadb; p=os.getenv('CHROMA_DIR'); n=os.getenv('CHROMA_COLLECTION'); c=chromadb.PersistentClient(path=p).get_collection(name=n); print(c.count())"
```

Nếu collection trống/mất:

```powershell
docker compose exec agent python -m src.backend.services.ingest_postgres --reset
```

---

## 24.4. Frontend không gọi được backend

Kiểm tra `.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Sau khi đổi biến Vite, restart:

```powershell
npm run dev
```

Kiểm tra backend:

```text
http://localhost:8000/health
```

---

## 24.5. `npm run dev` báo không tìm thấy file

Chạy npm ở **root `P-013`**, không chạy trong `src/frontend`.

Đúng:

```powershell
cd D:\...\P-013
npm install
npm run dev
```

Vite sẽ tự dùng:

```text
src/frontend
```

làm frontend root.

---

## 24.6. Docker chạy code cũ sau khi sửa backend

Rebuild image:

```powershell
docker build -t p013-backend:latest .
```

Recreate:

```powershell
docker compose stop agent
docker compose rm -f agent
docker compose up -d agent
```

---

## 24.7. PostgreSQL có session nhưng FE không hiện history

History UI chỉ hiển thị khi:

- user đã đăng nhập
- request có Bearer token
- `app.session.user_id` đúng user hiện tại
- session có message

Kiểm tra:

```sql
SELECT id, user_id, last_activity_at
FROM app.session
ORDER BY last_activity_at DESC;
```

---

# 25. Test checklist sau khi setup máy mới

Thực hiện lần lượt:

```text
[ ] PostgreSQL running
[ ] Database vinpearl tồn tại
[ ] User vinpearl connect được
[ ] .env có LLM_API_KEY
[ ] docker build thành công
[ ] agent container Up
[ ] redis container Up/healthy
[ ] GET /health = 200
[ ] GET /ready = 200
[ ] Core data đã load
[ ] Chroma document count > 0
[ ] npm install thành công
[ ] npm run dev mở được localhost:5173
[ ] Chat "Xin chào" hoạt động
[ ] Query Vinpearl/Nha Trang trả data + sources
[ ] Login hoạt động
[ ] New chat không xóa history cũ
[ ] Sidebar history chỉ hiện khi login
[ ] Logout làm history biến mất
[ ] User khác không xem được history của user trước
[ ] Support multilingual route đúng
```

---

# 26. Trạng thái chức năng hiện tại

## Đã hoàn thành

- PostgreSQL Core schema
- PostgreSQL App schema
- Alembic migrations
- Destination seed
- Core data loader
- PostgreSQL → Chroma ingestion
- Chroma persistent volume
- Multilingual embedding
- FastAPI backend
- LangGraph agent
- React/Vite frontend
- Authentication
- Admin bootstrap
- Staff management
- Support ticket
- PostgreSQL chat memory
- Authenticated chat-history sidebar
- Session ownership protection
- Multilingual support routing
- Conditional LLM optimization
- Reuse document embeddings trong Chroma
- Source links / reranking
- Redis
- Docker image
- Docker Compose
- `/health`
- `/ready`
- `/api/v1/chat`
- `/ask`

---

## Chưa hoàn thành / bước tiếp theo

- Railway production deployment
- Railway PostgreSQL
- Railway Redis
- Railway Volume cho Chroma/Hugging Face cache
- Public Backend URL
- Public Frontend URL
- Production secrets / domain / CORS hardening
- Production monitoring & latency metrics

---

# 27. Setup nhanh nhất cho máy mới — Tóm tắt

Tại root project:

```powershell
# 1. Python
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt

# 2. Node
npm install

# 3. Tạo/cấu hình PostgreSQL + .env trước

# 4. Backend image
docker build -t p013-backend:latest .

# 5. Backend + Redis
docker compose up -d

# 6. Dữ liệu lần đầu
docker compose exec agent python -m scripts.seed_destinations
docker compose exec agent python -m scripts.load_core
docker compose exec agent python -m src.backend.services.ingest_postgres --reset

# 7. Check
docker compose ps

# 8. Frontend
npm run dev
```

Mở:

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8000
Swagger:  http://localhost:8000/docs
```

Nếu cả `/health`, `/ready`, Chroma và FE đều chạy thì máy đã setup xong.

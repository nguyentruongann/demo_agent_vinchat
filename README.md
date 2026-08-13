# P-013 — Vinpearl Multilingual Travel Agent

## 1. Setup môi trường local

### Tạo virtual environment

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
```

### Cài dependencies

```powershell
python -m pip install -r requirements.txt
```

---

## 2. PostgreSQL

### Kiểm tra ORM metadata

```powershell
python -c "from src.db import Base; print(len(Base.metadata.tables)); print(list(Base.metadata.tables.keys()))"
```

### Tạo PostgreSQL user

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" `
  -U postgres `
  -c "CREATE USER vinpearl WITH PASSWORD '<POSTGRES_PASSWORD>';"
```

> Nếu user `vinpearl` đã tồn tại thì bỏ qua bước này. Mật khẩu thật nên lấy từ `.env`, không ghi trực tiếp vào README khi commit Git.

### Kiểm tra migration hiện tại

```powershell
alembic current
```

### Chạy migrations

```powershell
alembic upgrade head
```

### Seed destination data

```powershell
python -m scripts.seed_destinations
```

### Load dữ liệu Core vào PostgreSQL

```powershell
python -m scripts.load_core
```

---

## 3. Tạo Chroma Vector Store từ PostgreSQL

Sau khi PostgreSQL đã có dữ liệu:

```powershell
python -m src.backend.services.ingest_postgres --reset
```

Lệnh này sẽ đọc dữ liệu business từ PostgreSQL, chunk dữ liệu, tạo embedding, ghi vectors vào Chroma và lưu tại `storage/chroma_local`.

---

## 4. Chạy Backend FastAPI local

```powershell
python -m uvicorn src.backend.main:app --reload --port 8000
```

Backend local:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

Health check:

```text
GET /health
```

Readiness check:

```text
GET /ready
```

---

## 5. Chạy Frontend local

Nếu frontend nằm tại `src/frontend`:

```powershell
cd D:\vinuni\T013\main\P-013\src\frontend
npm install
npm run dev
```

Frontend thường chạy tại:

```text
http://localhost:5173
```

Frontend gọi backend thông qua:

```env
VITE_API_BASE_URL=http://localhost:8000
```

---

## 6. Tạo Admin đầu tiên

Lấy giá trị `ADMIN_BOOTSTRAP_KEY` từ `.env`.

```powershell
$body = @{
  name = "P013 Admin"
  email = "admin@example.com"
  phone = $null
  password = "ChangeThisPassword123!"
  locale = "vi"
  bootstrap_key = "LAY_ADMIN_BOOTSTRAP_KEY_TRONG_ENV"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/auth/bootstrap-admin" `
  -ContentType "application/json" `
  -Body $body
```

Sau khi tạo admin thành công:

```text
/admin/staff
```

---

## 7. Docker

Project đã đóng gói Backend + Redis bằng Docker.

### Build image

```powershell
docker compose build
```

Image backend:

```text
p-013-agent:latest
```

### Chạy Docker Compose

```powershell
docker compose up
```

Kiến trúc local hiện tại:

```text
Frontend Vite
     |
     v
FastAPI Backend (Docker)
     |
     +--> PostgreSQL trên Windows host
     |
     +--> Redis container
     |
     +--> Chroma Docker Volume
```

PostgreSQL Windows được container truy cập bằng:

```text
host.docker.internal:5432
```

Redis được backend truy cập bằng:

```text
redis://redis:6379/0
```

Chroma trong Docker dùng:

```text
/app/storage/chroma_local
```

---

## 8. Kiểm tra Docker

### Health

```powershell
python -c "import httpx; r=httpx.get('http://localhost:8000/health'); print(r.status_code); print(r.text)"
```

Kỳ vọng:

```text
200
{"status":"ok"}
```

### Ready

```powershell
python -c "import httpx; r=httpx.get('http://localhost:8000/ready'); print(r.status_code); print(r.text)"
```

Kỳ vọng:

```text
200
{"status":"ready"}
```

### Test Agent API

Có API key:

```powershell
python -c "import httpx; r=httpx.post('http://localhost:8000/ask', headers={'X-API-Key':'dev-local-secret-key'}, json={'question':'Xin chào'}); print(r.status_code); print(r.text)"
```

Kỳ vọng HTTP `200` và response có `answer` cùng `session_id`.

---

## 9. Biến môi trường

### `.env`

Dùng cho môi trường local.

Ví dụ:

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini/gemini-3.5-flash-lite

LOCAL_EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=128

DATABASE_URL=postgresql+pg8000://vinpearl:<POSTGRES_PASSWORD>@localhost:5432/vinpearl

CHROMA_DIR=./storage/chroma_local
CHROMA_COLLECTION=vinpearl_multilingual_e5_small

VITE_API_BASE_URL=http://localhost:8000

ADMIN_BOOTSTRAP_KEY=<ADMIN_BOOTSTRAP_KEY>
AGENT_API_KEY=dev-local-secret-key
```

> Không commit `.env` có secret thật lên GitHub.

### `.env.railway.example`

Chỉ là file mẫu tham khảo cho Railway.

- Không dùng trực tiếp cho local
- Không chứa secret thật
- Khi deploy Railway sẽ khai báo Variables trên Railway Dashboard

---

## 10. Các lệnh thường dùng

### Setup đầy đủ từ đầu

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt

alembic current
alembic upgrade head

python -m scripts.seed_destinations
python -m scripts.load_core

python -m src.backend.services.ingest_postgres --reset
```

### Chạy backend không Docker

```powershell
python -m uvicorn src.backend.main:app --reload --port 8000
```

### Chạy Docker

```powershell
docker compose build
docker compose up
```

### Dừng Docker

```powershell
docker compose down
```

---

## 11. Trạng thái hiện tại

### Đã hoàn thành

- PostgreSQL schema
- Alembic migrations
- Seed destination
- Load Core data
- PostgreSQL → Chroma ingestion
- FastAPI Backend
- React/Vite Frontend
- Admin bootstrap
- Redis
- Docker image
- Docker Compose
- `/health`
- `/ready`
- `/ask`
- Docker local test

### Chưa thực hiện

- Railway deployment
- Railway PostgreSQL
- Railway Redis
- Railway Volume cho Chroma
- Public Backend URL
- Public Frontend URL

Railway sẽ triển khai ở bước tiếp theo.

# Tầng cơ sở dữ liệu

Mã nguồn trong thư mục này:

| File | Nội dung |
|---|---|
| `base.py` | `Base`, mixin `Timestamped` / `Sourced`, quy ước đặt tên ràng buộc |
| `core.py` | 41 bảng CORE — dữ liệu nghiệp vụ từ `data/*.json` |
| `app.py` | 7 bảng ứng dụng — người dùng, hội thoại, ticket |
| `errors.py` | Đọc mã SQLSTATE độc lập driver |

Đặc tả đầy đủ 48 bảng, kèm nguồn JSON và mức bằng chứng cho từng quan hệ:
[docs/DATABASE.md](../../docs/DATABASE.md).

---

## 1. Cài đặt lần đầu

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt

copy .env.example .env      # rồi điền LLM_API_KEY và POSTGRES_PASSWORD
```

---

## 2. Database (PostgreSQL 16 + pgvector)

Luôn cần **Docker Desktop đang chạy** trước khi gõ bất kỳ lệnh nào ở mục này.

### 2.1 Lần đầu — bốn lệnh, khoảng 2 phút

```bash
docker compose up -d --wait db          # 1. dựng Postgres, chờ tới khi healthy
python -m alembic upgrade head          # 2. tạo 48 bảng + view + extension
python -m scripts.seed_destinations     # 3. nạp 13 địa danh, 32 bí danh, 8 khu phức hợp
python -m scripts.load_core             # 4. nạp data/*.json -> 6.587 dòng
```

### 2.2 Các lần sau — một lệnh

```bash
docker compose up -d --wait db
```

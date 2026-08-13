## 1. Mục đích

Bộ CSV dùng để:

1. **Định nghĩa** câu hỏi / chuỗi hội thoại cần kiểm tra chatbot.
2. Có **đáp án tham chiếu** (`reference_hint`) bám nội dung đã crawl.
3. **Ghi nhận kết quả thật** sau khi chạy với backend (câu trả lời, thời gian, trạng thái).

Các cột kết quả mặc định **để trống** cho đến khi case được chạy thật — không điền sẵn `pending` / câu trả lời giả.

---

## 2. Cấu trúc cột

| Cột | Bắt buộc trước khi chạy? | Ý nghĩa |
|-----|--------------------------|---------|
| `test_id` | Có | Mã case duy nhất (`faq-001`, `promo-003`, `memory-nha-trang`, …) |
| `type` | Có | Nhóm case (xem mục 3) |
| `user_message` | Có | Câu hỏi gửi chatbot. Memory: nhiều lượt nối bằng ` \| ` |
| `reference_hint` | Có | Gợi ý / đáp án tham chiếu để đối chiếu thủ công hoặc chấm điểm |
| `assistant_answer` | **Để trống** | Câu trả lời thật từ API sau khi chạy |
| `response_time_ms` | **Để trống** | Tổng thời gian phản hồi (ms) |
| `status` | **Để trống** | `pass` / `fail` sau khi chạy; để trống nếu chưa chạy |

### Quy ước Memory / multi-turn

- Trong `user_message`: các lượt user cách nhau bởi ` | ` (dấu cách-pipe-dấu cách).
- Khi chạy: **cùng một `session_id`** cho mọi lượt của case đó.
- Trong `assistant_answer`: các câu trả lời tương ứng nối bằng ` || `.
- `reference_hint` cũng có thể dùng ` || ` để mô tả kỳ vọng từng lượt / kỳ vọng nhớ ngữ cảnh.

Ví dụ (rút gọn):

```text
user_message:
Tôi đang lên kế hoạch đi Nha Trang với gia đình. | Ở Nha Trang Vinpearl có những resort nào? | Bạn còn nhớ tôi đang hỏi về Nha Trang chứ?

reference_hint:
Ghi nhớ điểm đến: Nha Trang; đối tượng: gia đình. || Liệt kê resort tại Nha Trang: ... || Phải nhớ điểm đến hiện tại là Nha Trang.

assistant_answer (sau khi chạy):
<câu trả lời lượt 1> || <câu trả lời lượt 2> || <câu trả lời lượt 3>
```

---

## 3. Phân loại `type` (277 cases)

| `type` | Số lượng | Nội dung chính |
|--------|----------|----------------|
| `FAQ - General` | 8 | Đặt dịch vụ, ưu đãi, CSKH, thanh toán, hoàn tiền… |
| `FAQ - Hotels` | 12 | Check-in/out, giường phụ, phụ thu trẻ em, đưa đón… |
| `FAQ - Bundle Hotels Flights` | 7 | Combo KS + vé máy bay |
| `FAQ - Tours Experiences` | 22 | Voucher, tour, trải nghiệm |
| `FAQ - Flights` | 10 | Vé máy bay |
| `FAQ - VinClub` | 53 | Hội viên, hạng thẻ, tích điểm |
| `FAQ - VinWonders Safari` | 62 | Công viên / Safari |
| `Promotion` | 51 | Ưu đãi active + theo điểm đến |
| `Golf` | 11 | Số lỗ, par, tiện ích sân golf |
| `About` | 2 | Thương hiệu / MICE |
| `Hotel` | 9 | Giới thiệu resort từ About crawl |
| `Package` | 3 | Family Beach, Golf Stay & Play, Wellness |
| `Regulation` | 7 | Điều khoản / quy định |
| `Memory` | 20 | Chuỗi hội thoại cần nhớ ngữ cảnh |

Tiền tố `test_id` gợi ý nguồn: `faq-*`, `promo-*`, `golf-*`, `about-*`, `policy-*`, `memory-*`.

### Các chuỗi Memory tiêu biểu

| `test_id` | Kịch bản |
|-----------|----------|
| `memory-nha-trang` / `phu-quoc` / `hoi-an` | Điểm đến → resort → ưu đãi → nhớ điểm đến → tóm tắt |
| `memory-switch-dest` | Phú Quốc → đổi sang Nha Trang |
| `memory-correct-destination` | User sửa điểm đến giữa chừng |
| `memory-hotel-policy` | Check-in → trả muộn → giường phụ → đồ ăn ngoài |
| `memory-family-kids` | Thành phần đoàn → phụ thu → sức chứa |
| `memory-pronoun-followup` | «Ở đó / còn… thì sao» bám đúng entity |
| `memory-compare-hotels` | So sánh 2 resort → nhớ lựa chọn |
| `memory-vinwonders-safari` | VW vs Safari + trẻ nhỏ |
| `memory-trip-constraints` | 3N2Đ + ngân sách + thành phần đoàn |
| … | Xem đầy đủ trong CSV |

---

## 4. Cách tương tác với hệ thống

### 4.1. Chuẩn bị môi trường

```powershell
.\.venv\Scripts\Activate.ps1

# Postgres (nếu dùng Docker theo project) + backend
uvicorn src.backend.main:app --reload --host 127.0.0.1 --port 8000
```

Kiểm tra health:

```powershell
curl http://127.0.0.1:8000/health
```

Endpoint chat dùng cho test case:

```http
POST http://127.0.0.1:8000/api/v1/chat
Content-Type: application/json

{
  "message": "Vinpearl có những resort nào ở Nha Trang?",
  "session_id": "manual-demo-001"
}
```

Response quan trọng: field `answer` (và `session_id`).

### 4.2. Tương tác thủ công (1 case)

Phù hợp khi debug từng câu / Memory.

1. Mở CSV, chọn 1 `test_id` (ví dụ `faq-001`).
2. Copy `user_message` (Memory: tách từng đoạn theo ` | `).
3. Gọi API (hoặc UI chat) với **cùng `session_id`** cho mọi lượt của case đó.
4. Ghi lại:
   - `assistant_answer` = câu trả lời (Memory: nối ` || `)
   - `response_time_ms` = tổng ms các lượt (hoặc đo từng lượt rồi cộng)
   - `status` = `pass` nếu API OK và có câu trả lời; `fail` nếu lỗi / trống
5. Đối chiếu với `reference_hint` (nội dung có đủ ý chính không, Memory có nhớ đúng slot không).

PowerShell ví dụ 1 lượt:

```powershell
$body = @{
  message = "Thời gian phản hồi của Trung tâm Chăm sóc Khách hàng là bao lâu?"
  session_id = "manual-faq-003"
} | ConvertTo-Json

Measure-Command {
  $resp = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/chat" `
    -ContentType "application/json; charset=utf-8" -Body $body
  $resp.answer
}
```

### 4.3. Chạy tự động để điền cột còn trống (khuyến nghị)

Script: `src/test_cases/utils/run_test_case_csv.py`

- Đọc `test_case_vi.csv` (hoặc đường dẫn bạn truyền vào).
- Bỏ qua case đã có `status` = `pass`/`fail` (trừ khi `--force`).
- Gọi `/api/v1/chat`, điền `assistant_answer`, `response_time_ms`, `status`.
- Ghi đè lại cùng file; nếu Excel đang mở khóa file → ghi `*_results.csv`.

```powershell

# Smoke test 5 case đầu còn trống
python -m src.test_cases.utils.run_test_case_csv --limit 5

# Chỉ chạy vài id
python -m src.test_cases.utils.run_test_case_csv --only faq-001,memory-nha-trang

# Chạy hết phần chưa có status
python -m src.test_cases.utils.run_test_case_csv --resume

# Bản tiếng Anh
python -m src.test_cases.utils.run_test_case_csv src/test_cases/output/test_case_en.csv --limit 5

# Chạy lại case đã fail
python -m src.test_cases.utils.run_test_case_csv --only faq-010 --force
```

> **Lưu ý:** Đóng Excel trước khi chạy full suite để tránh `PermissionError`. Full 277 case tốn token/thời gian LLM — nên chạy `--limit` / `--only` trước.

### 4.4. Ý nghĩa `status` khi điền tự động

| `status` | Khi nào |
|----------|---------|
| *(trống)* | Chưa chạy |
| `pass` | API 200 và có `answer` (mọi lượt Memory thành công) |
| `fail` | HTTP lỗi, timeout, exception, hoặc thiếu câu trả lời |

`pass` **không** đồng nghĩa “đúng 100% so với `reference_hint`”. Việc chấm chất lượng nội dung vẫn cần review thủ công (hoặc bước chấm điểm riêng sau này).

Gợi ý review nhanh:

1. FAQ / Policy: đáp án có đúng số liệu / điều kiện chính trong `reference_hint` không?
2. Promotion: có nhầm sang ưu đãi khác không?
3. Memory: còn nhớ điểm đến / resort / thành phần đoàn sau nhiều lượt không?
4. Pronoun / switch / correct-destination: có bám entity mới nhất không?

Có thể bổ sung cột sau (không bắt buộc trong schema hiện tại): `reviewer_note`, `quality` (`ok` / `partial` / `wrong`).

---

## 5. Checklist điền phần còn lại

Dùng checklist này khi “làm đầy” bộ test:

- [ ] Backend `:8000` healthy, `.env` / Gemini key OK  
- [ ] Đóng Excel / phần mềm đang khóa `test_case_vi.csv`  
- [ ] Smoke `--limit 3` với 1 FAQ + 1 Promotion + 1 Memory  
- [ ] Chạy `--only` cho nhóm cần ưu tiên (ví dụ toàn bộ `memory-*`)  
- [ ] Chạy `--resume` cho phần còn trống  
- [ ] Spot-check 10–20 `pass`: đối chiếu `assistant_answer` ↔ `reference_hint`  
- [ ] Case `fail`: ghi chú lỗi (timeout / HTTP / empty), chạy lại `--force` sau khi sửa hệ thống  
- [ ] (Tuỳ chọn) Copy kết quả ra `test_case_vi_results_YYYYMMDD.csv` để giữ bản definition sạch  

### Không nên

- Điền sẵn `assistant_answer` bằng cách copy `reference_hint`.
- Đánh `status=pass` khi chưa gọi hệ thống thật.
- Gộp nhiều Memory case chung một `session_id` khi chạy tay (dễ nhiễm ngữ cảnh).
- Rebuild CSV từ crawl **sau** khi đã điền kết quả (sẽ mất cột đã chạy) — nên backup trước.

---

## 6. Tạo lại file định nghĩa (khi cần)

Nếu chỉ muốn **sinh lại** bộ câu hỏi/tham chiếu (xóa kết quả đã chạy):

| File | Lệnh |
|------|------|
| Tiếng Việt (schema simple + memory) | `python -m src.test_cases.utils.build_crawl_csv_simple` rồi đồng bộ/đổi tên về `test_case_vi.csv` nếu cần |
| Tiếng Anh | `python -m src.test_cases.utils.build_test_case_en` → `test_case_en.csv` |

File VI hiện tại (`test_case_vi.csv`) là bản đã tinh chỉnh (277 dòng, 20 Memory). Trước khi rebuild, hãy backup.

---

## 7. Tóm tắt nhanh

1. **Đọc** `user_message` + `reference_hint` để hiểu case.  
2. **Chạy** chat (tay hoặc `run_test_case_csv`).  
3. **Điền** `assistant_answer`, `response_time_ms`, `status`.  
4. **Review** nội dung so với `reference_hint`, đặc biệt nhóm `Memory`.  
5. Chỉ khi ổn định mới coi case là hoàn tất (`pass` + review OK).

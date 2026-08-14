# Frontend – Vinpearl AI Assistant

Frontend là ứng dụng React 19 chạy bằng Vite 8. Toàn bộ mã nguồn giao diện nằm
trong `src/frontend`; các file cấu hình dùng chung như `package.json`,
`vite.config.js` và `index.html` nằm ở thư mục gốc dự án.

## Chức năng hiện có

- Trang chủ giới thiệu điểm đến, khách sạn, combo và AI Concierge.
- Tìm kiếm khách sạn theo điểm đến, loại hình và mức giá.
- Xem chi tiết khách sạn, phòng, tiện ích và chính sách.
- Trang ưu đãi đọc dữ liệu thật từ PostgreSQL thông qua backend.
- Chatbot đa ngôn ngữ, hiển thị nguồn tham khảo và support ticket.
- Form gửi yêu cầu hỗ trợ.
- Trang giới thiệu, quy định, đăng nhập và đăng ký.
- Giao diện responsive cho desktop, tablet và mobile.

## Yêu cầu môi trường

- Node.js 20 trở lên.
- npm đi kèm Node.js.
- Backend chạy tại `http://127.0.0.1:8000` nếu muốn dùng API thật.

Frontend không sử dụng `requirements.txt`. Dependency JavaScript được quản lý
bởi `package.json` và khóa phiên bản trong `package-lock.json`.

## Cài đặt và chạy

Chạy các lệnh từ thư mục gốc dự án:

```powershell
cd D:\Demo-day\P-013
npm install
npm run dev
```

Mở địa chỉ Vite hiển thị trên terminal, thông thường là:

```text
http://localhost:5173
```

Nếu PowerShell chặn `npm.ps1`, dùng:

```powershell
npm.cmd run dev
```

Các lệnh kiểm tra:

```powershell
npm.cmd run lint
npm.cmd run build
npm.cmd run preview
```

## Chạy cùng backend

Mở terminal thứ nhất:

```powershell
cd D:\Demo-day\P-013\src\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn src.main:app --reload --port 8000
```

Mở terminal thứ hai:

```powershell
cd D:\Demo-day\P-013
npm.cmd run dev
```

`vite.config.js` tự chuyển tiếp request `/api/*` sang
`http://127.0.0.1:8000`. Lỗi `ECONNREFUSED 127.0.0.1:8000` nghĩa là backend
chưa chạy hoặc đã dừng.

## Điểm khởi động

- `index.html` nằm ở thư mục gốc vì Vite dùng đây làm tài liệu HTML đầu vào.
- `src/frontend/main.jsx` gắn React vào phần tử `#root`.
- `src/frontend/App.jsx` khai báo Router, Language Context và Auth Context.
- `src/frontend/routes/AppRoutes.jsx` quản lý route và layout chung.
- `src/frontend/index.css` chứa CSS toàn cục.

Không di chuyển `index.html` vào `src/frontend` nếu chưa đồng thời thay đổi cấu
hình Vite.

## Cấu trúc thư mục

```text
src/frontend/
├── components/          Component dùng lại ở nhiều trang
├── context/             Trạng thái đăng nhập và ngôn ngữ
├── data/                Dữ liệu cục bộ và media dùng cho phần chưa có API
├── pages/               Các trang theo route
├── routes/              Router và layout chung
├── services/            Hàm gọi backend API
├── styles/
│   ├── components/      CSS theo component
│   ├── pages/           CSS theo trang
│   └── routes/          CSS cho layout
├── App.jsx              Component gốc
├── main.jsx             Entry point React
├── index.css            CSS toàn cục
└── types.js             Kiểu dữ liệu JSDoc dùng chung
```

## Các route chính

| Đường dẫn | Trang | Chức năng |
| --- | --- | --- |
| `/` | `Home.jsx` | Trang chủ |
| `/about` | `About.jsx` | Giới thiệu |
| `/search` | `SearchResults.jsx` | Tìm kiếm khách sạn |
| `/hotels/:hotelId` | `HotelDetail.jsx` | Chi tiết khách sạn |
| `/promotions` | `Promotions.jsx` | Danh sách ưu đãi |
| `/chat`, `/chatbot` | `Chatbot.jsx` | AI Concierge |
| `/support` | `Ticket.jsx` | Gửi yêu cầu hỗ trợ |
| `/regulations` | `Regulations.jsx` | Quy định và chính sách |
| `/login` | `Login.jsx` | Đăng nhập |
| `/register` | `Register.jsx` | Đăng ký |

Các trang nội dung dùng chung `Header`, `Footer` và `ChatWidget`. Trang đăng
nhập và đăng ký sử dụng layout riêng.

## Kết nối API

Các lời gọi backend tập trung tại `src/frontend/services/api.js`.

| Chức năng | Endpoint chính |
| --- | --- |
| Chatbot | `POST /api/v1/chat` |
| Ưu đãi | `GET /api/v1/promotions` |
| Support ticket | API ticket được khai báo trong `services/api.js` |

Trang Promotions hỗ trợ:

- Lọc theo điểm đến và trạng thái.
- Tìm kiếm theo tiêu đề hoặc nội dung.
- Hiển thị sáu ưu đãi đầu tiên và nút “Xem thêm ưu đãi”.
- Hiển thị ảnh từ bảng `media` thông qua trường `image_url`.
- Dùng URL nguồn làm liên kết dự phòng khi ưu đãi không có `booking_url`.
- Hiển thị trạng thái tải, rỗng, lỗi và nút thử lại.

Chi tiết luồng dữ liệu Promotions nằm tại
`docs/PROMOTIONS_DB_API_FE.md`.

## Dữ liệu cục bộ

`src/frontend/data` vẫn chứa dữ liệu và media cục bộ cho các màn hình chưa được
nối đầy đủ với database. Riêng trang Promotions đã dùng API thật, không dùng
mock data cho danh sách ưu đãi, ảnh hay thời hạn áp dụng.

## Ngôn ngữ

`LanguageContext.jsx` quản lý ngôn ngữ hiển thị. Tiếng Anh và tiếng Việt đã có
nội dung chính; các ngôn ngữ chưa được dịch đầy đủ có thể dùng tiếng Anh làm
phương án dự phòng.

Khi thêm nội dung tiếng Việt:

- Viết đầy đủ dấu tiếng Việt.
- Lưu file bằng UTF-8.
- Không chuyển chuỗi có dấu sang dạng không dấu.
- Kiểm tra lại cả giao diện desktop và mobile sau khi sửa nội dung dài.

## Quy ước phát triển

- Component dùng lại đặt trong `components`.
- Trang gắn với URL đặt trong `pages`.
- Không gọi `fetch` trực tiếp rải rác trong component; thêm hàm vào
  `services/api.js`.
- Kiểu dữ liệu dùng chung được mô tả trong `types.js` bằng JSDoc.
- CSS đặt đúng thư mục và đặt tên class theo phạm vi component hoặc trang.
- Thành phần có thể bấm phải có trạng thái hover/focus và `cursor: pointer`.
- Không commit `.env`, mật khẩu, token hoặc thông tin kết nối database.
- Không sửa trực tiếp thư mục `dist`; đây là kết quả do Vite tạo ra.

## Xử lý lỗi thường gặp

### Frontend gọi API nhưng báo `ECONNREFUSED`

Khởi động backend ở port `8000`, sau đó tải lại trang.

### Trang Promotions báo không tải được dữ liệu

Kiểm tra lần lượt:

1. PostgreSQL đang chạy.
2. `src/backend/.env` có `DATABASE_URL` hợp lệ.
3. Backend mở được `http://localhost:8000/health`.
4. Endpoint mở được tại `http://localhost:8000/api/v1/promotions`.

### Ảnh ưu đãi không hiển thị

Frontend sẽ tự dùng nền và icon mặc định nếu URL ảnh lỗi. Kiểm tra trường
`image_url` trong response API và khả năng truy cập URL ảnh từ trình duyệt.

### PowerShell không chạy được npm

Dùng file thực thi Windows:

```powershell
npm.cmd run dev
```


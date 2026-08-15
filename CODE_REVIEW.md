# CHỨC NĂNG CÁC FILE TRONG `src/`

 
## Bản đồ thư mục

```text
src/
├── backend/
│   ├── agents/       # LangGraph Agent và các node
│   ├── api/          # FastAPI routes
│   ├── models/       # Pydantic schemas
│   └── services/     # RAG, DB, LLM, auth, memory, ticket...
├── data_postgre/
│   ├── db/           # SQLAlchemy ORM + migration
│   └── normalize/    # Chuẩn hóa dữ liệu crawl vào schema CORE
├── data_crawl/       # Dữ liệu crawl/JSON/notebook
└── frontend/
    ├── components/
    ├── context/
    ├── data/
    ├── locales/
    ├── pages/
    ├── routes/
    ├── services/
    └── styles/
```

## 1. Backend — Agent / LangGraph

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/backend/agents/graph.py`](src/backend/agents/graph.py) | Lắp LangGraph cho Agent: đăng ký các node, khai báo edge/conditional edge và quyết định nhánh xử lý từ START đến END. | [`route_after_classification()`](src/backend/agents/graph.py#L27)<br>[`route_after_safety()`](src/backend/agents/graph.py#L31)<br>[`route_after_guardrail()`](src/backend/agents/graph.py#L36)<br>[`route_after_support_triage()`](src/backend/agents/graph.py#L45)<br>[`route_after_assessment()`](src/backend/agents/graph.py#L53) |
| [`src/backend/agents/nodes/answer.py`](src/backend/agents/nodes/answer.py) | Node sinh câu trả lời cuối từ context đã retrieval, intent và entity/destination đã resolve. | [`generate_answer()`](src/backend/agents/nodes/answer.py#L34) |
| [`src/backend/agents/nodes/classify.py`](src/backend/agents/nodes/classify.py) | Node phân loại route của câu hỏi sau khi đã có ngôn ngữ và ngữ cảnh, ví dụ greeting, conversation context, out-of-scope hoặc RAG. | [`classify_input()`](src/backend/agents/nodes/classify.py#L54) |
| [`src/backend/agents/nodes/context_resolver.py`](src/backend/agents/nodes/context_resolver.py) | Node giải quyết ngữ cảnh hội thoại: xác định destination/entity mà câu hiện tại đang tham chiếu dựa trên câu hỏi hiện tại và memory các lượt trước. | [`resolve_conversation_context()`](src/backend/agents/nodes/context_resolver.py#L166) |
| [`src/backend/agents/nodes/grounding.py`](src/backend/agents/nodes/grounding.py) | Node kiểm tra câu trả lời có bám vào retrieved context/source hay không và ghi kết quả grounding vào state. | [`validate_grounding()`](src/backend/agents/nodes/grounding.py#L6) |
| [`src/backend/agents/nodes/guardrail.py`](src/backend/agents/nodes/guardrail.py) | Node kiểm tra input đầu vào: scope, safety, prompt injection; tạo request đã sanitize và xác định ngôn ngữ cho các turn bị chặn trước khi đi tiếp. | [`effective_user_message()`](src/backend/agents/nodes/guardrail.py#L16)<br>[`enforce_input_guardrail()`](src/backend/agents/nodes/guardrail.py#L106) |
| [`src/backend/agents/nodes/language.py`](src/backend/agents/nodes/language.py) | Node xử lý ngôn ngữ cho nhánh được phép: phát hiện ngôn ngữ, tạo `rag_query`, xác định coarse route và thực hiện semantic safety check. | [`detect_language_and_translate()`](src/backend/agents/nodes/language.py#L105) |
| [`src/backend/agents/nodes/language_guard.py`](src/backend/agents/nodes/language_guard.py) | Node cuối bảo đảm câu trả lời hiển thị đúng ngôn ngữ đầu vào đã lưu trong state trước khi trả cho người dùng. | [`enforce_response_language()`](src/backend/agents/nodes/language_guard.py#L7) |
| [`src/backend/agents/nodes/memory.py`](src/backend/agents/nodes/memory.py) | Hai node nối Agent với `MemoryService`: tải lịch sử hội thoại vào state trước xử lý và lưu turn sau khi hoàn tất. | [`load_conversation_memory()`](src/backend/agents/nodes/memory.py#L5)<br>[`save_conversation_memory()`](src/backend/agents/nodes/memory.py#L46) |
| [`src/backend/agents/nodes/retrieval.py`](src/backend/agents/nodes/retrieval.py) | Node truy xuất tri thức: phân tích query, lấy FAQ/RAG documents, gộp kết quả theo intent và đánh giá dữ liệu đã đủ để trả lời hay chưa. | [`retrieve_context()`](src/backend/agents/nodes/retrieval.py#L91)<br>[`assess_information()`](src/backend/agents/nodes/retrieval.py#L224) |
| [`src/backend/agents/nodes/static_responses.py`](src/backend/agents/nodes/static_responses.py) | Sinh các phản hồi không cần RAG chính: greeting, out-of-scope, sensitive, conversation-context và no-data theo ngôn ngữ hiện tại. | [`greeting_response()`](src/backend/agents/nodes/static_responses.py#L36)<br>[`out_of_scope_response()`](src/backend/agents/nodes/static_responses.py#L55)<br>[`sensitive_content_response()`](src/backend/agents/nodes/static_responses.py#L74)<br>[`conversation_context_response()`](src/backend/agents/nodes/static_responses.py#L165)<br>[`no_data_response()`](src/backend/agents/nodes/static_responses.py#L206) |
| [`src/backend/agents/nodes/support_triage.py`](src/backend/agents/nodes/support_triage.py) | Node phân loại yêu cầu hỗ trợ: xác định câu hỏi chỉ cần cung cấp thông tin hay cần chuyển sang nhân viên/ticket. | [`analyze_support_request()`](src/backend/agents/nodes/support_triage.py#L442) |
| [`src/backend/agents/nodes/ticket.py`](src/backend/agents/nodes/ticket.py) | Node tạo support ticket khi state được triage là cần nhân viên; đồng thời tạo nội dung phản hồi ticket theo ngôn ngữ người dùng. | [`create_ticket()`](src/backend/agents/nodes/ticket.py#L72) |
| [`src/backend/agents/scope_policy.py`](src/backend/agents/scope_policy.py) | Chứa prompt/chính sách phạm vi hỗ trợ của Agent Vinpearl/VinWonders để các node kiểm tra câu hỏi có thuộc domain hay không. | [`scope_policy_prompt()`](src/backend/agents/scope_policy.py#L66) |
| [`src/backend/agents/state.py`](src/backend/agents/state.py) | Định nghĩa `AgentState` — cấu trúc state dùng để truyền dữ liệu giữa các node của LangGraph. | [`AgentState`](src/backend/agents/state.py#L12) |

## 2. Backend — API routes

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/backend/api/about_routes.py`](src/backend/api/about_routes.py) | Router trang About: đọc thông tin tổ chức và highlight từ PostgreSQL để trả dữ liệu giới thiệu Vinpearl. | [`get_about_info()`](src/backend/api/about_routes.py#L26) |
| [`src/backend/api/auth_routes.py`](src/backend/api/auth_routes.py) | Router xác thực và quản trị tài khoản: register, login, logout, lấy user hiện tại, bootstrap admin và CRUD tài khoản staff. | [`register()`](src/backend/api/auth_routes.py#L35)<br>[`login()`](src/backend/api/auth_routes.py#L51)<br>[`me()`](src/backend/api/auth_routes.py#L59)<br>[`logout()`](src/backend/api/auth_routes.py#L64)<br>[`bootstrap_admin()`](src/backend/api/auth_routes.py#L72)<br>[`list_staff()`](src/backend/api/auth_routes.py#L94)<br>[`create_staff()`](src/backend/api/auth_routes.py#L101)<br>[`update_staff()`](src/backend/api/auth_routes.py#L116) |
| [`src/backend/api/catalog_routes.py`](src/backend/api/catalog_routes.py) | Router catalog: trả danh sách destination, danh sách property/hotel và chi tiết property cùng room, dining, amenity và dữ liệu liên quan. | [`list_destinations()`](src/backend/api/catalog_routes.py#L123)<br>[`list_properties()`](src/backend/api/catalog_routes.py#L200)<br>[`property_detail()`](src/backend/api/catalog_routes.py#L253) |
| [`src/backend/api/promotions_routes.py`](src/backend/api/promotions_routes.py) | Router ưu đãi: lấy danh sách promotion có filter/trạng thái và lấy chi tiết một promotion. | [`list_promotions()`](src/backend/api/promotions_routes.py#L72)<br>[`promotion_detail()`](src/backend/api/promotions_routes.py#L210) |
| [`src/backend/api/routes.py`](src/backend/api/routes.py) | Router chat chính: gọi LangGraph, dựng danh sách source/citation cho response, đọc danh sách phiên chat, đọc message history và xóa lịch sử chat. | [`chat()`](src/backend/api/routes.py#L221)<br>[`list_chat_sessions()`](src/backend/api/routes.py#L280)<br>[`get_chat_session_messages()`](src/backend/api/routes.py#L292)<br>[`clear_chat_history()`](src/backend/api/routes.py#L308) |
| [`src/backend/api/staff_routes.py`](src/backend/api/staff_routes.py) | Router ticket dành cho staff/admin: xem danh sách ticket và cập nhật trạng thái/phân công ticket. | [`list_tickets()`](src/backend/api/staff_routes.py#L36)<br>[`update_ticket()`](src/backend/api/staff_routes.py#L54) |
| [`src/backend/api/ticket_routes.py`](src/backend/api/ticket_routes.py) | Router support ticket dành cho user: tạo ticket thủ công và xem các ticket của tài khoản hiện tại. | [`create_manual_ticket()`](src/backend/api/ticket_routes.py#L34)<br>[`my_tickets()`](src/backend/api/ticket_routes.py#L54) |

## 3. Backend — Models

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/backend/models/auth.py`](src/backend/models/auth.py) | Khai báo Pydantic schema cho register/login, user public, auth response, bootstrap admin và thao tác tài khoản staff. | [`UserPublic`](src/backend/models/auth.py#L9)<br>[`RegisterRequest`](src/backend/models/auth.py#L19)<br>[`LoginRequest`](src/backend/models/auth.py#L43)<br>[`AuthResponse`](src/backend/models/auth.py#L48)<br>[`StaffCreateRequest`](src/backend/models/auth.py#L54)<br>[`StaffUpdateRequest`](src/backend/models/auth.py#L58)<br>[`BootstrapAdminRequest`](src/backend/models/auth.py#L66) |
| [`src/backend/models/catalog.py`](src/backend/models/catalog.py) | Khai báo Pydantic schema dữ liệu catalog: destination, room, dining, property summary/detail và response danh sách property. | [`DestinationSummary`](src/backend/models/catalog.py#L6)<br>[`RoomSummary`](src/backend/models/catalog.py#L20)<br>[`DiningSummary`](src/backend/models/catalog.py#L36)<br>[`PropertySummary`](src/backend/models/catalog.py#L45)<br>[`PropertyDetail`](src/backend/models/catalog.py#L62)<br>[`PropertyListResponse`](src/backend/models/catalog.py#L69) |
| [`src/backend/models/chat.py`](src/backend/models/chat.py) | Khai báo Pydantic schema cho chat request/response, source citation, session summary và chat history. | [`ChatRequest`](src/backend/models/chat.py#L7)<br>[`SourceItem`](src/backend/models/chat.py#L13)<br>[`ChatResponse`](src/backend/models/chat.py#L20)<br>[`ChatSessionSummary`](src/backend/models/chat.py#L30)<br>[`ChatHistoryMessage`](src/backend/models/chat.py#L39)<br>[`ChatSessionHistory`](src/backend/models/chat.py#L50) |
| [`src/backend/models/schemas.py`](src/backend/models/schemas.py) | Schema chat tối giản dùng cho các interface/đường gọi tương thích cũ gồm `ChatRequest` và `ChatResponse`. | [`ChatRequest`](src/backend/models/schemas.py#L4)<br>[`ChatResponse`](src/backend/models/schemas.py#L8) |
| [`src/backend/models/ticket.py`](src/backend/models/ticket.py) | Khai báo Pydantic schema cho tạo ticket thủ công, dữ liệu ticket public và cập nhật ticket. | [`ManualTicketCreate`](src/backend/models/ticket.py#L10)<br>[`TicketPublic`](src/backend/models/ticket.py#L35)<br>[`TicketUpdateRequest`](src/backend/models/ticket.py#L53) |

## 4. Backend — Services

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/backend/services/auth.py`](src/backend/services/auth.py) | Xử lý nghiệp vụ authentication: chuẩn hóa contact, hash/verify password, tạo user, login, phát hành/revoke bearer session và dependency kiểm tra role. | [`normalize_email()`](src/backend/services/auth.py#L25)<br>[`normalize_phone()`](src/backend/services/auth.py#L30)<br>[`ensure_unique_contacts()`](src/backend/services/auth.py#L43)<br>[`hash_password()`](src/backend/services/auth.py#L75)<br>[`verify_password()`](src/backend/services/auth.py#L87)<br>[`user_public()`](src/backend/services/auth.py#L107)<br>[`create_user()`](src/backend/services/auth.py#L119)<br>[`authenticate()`](src/backend/services/auth.py#L160)<br>… (+7) |
| [`src/backend/services/data_loader.py`](src/backend/services/data_loader.py) | Loader JSON tổng quát: đi đệ quy dữ liệu JSON, làm sạch scalar, chunk text và tạo document/metadata phục vụ retrieval. | [`load_json_documents()`](src/backend/services/data_loader.py#L102) |
| [`src/backend/services/db.py`](src/backend/services/db.py) | Tạo và cache SQLAlchemy engine/session factory; cung cấp context manager mở/đóng PostgreSQL session. | [`get_engine()`](src/backend/services/db.py#L10)<br>[`get_session_factory()`](src/backend/services/db.py#L16)<br>[`open_session()`](src/backend/services/db.py#L20) |
| [`src/backend/services/faq_matcher.py`](src/backend/services/faq_matcher.py) | Nạp FAQ và thực hiện matching câu hỏi FAQ bằng lexical/semantic similarity; trả FAQ dưới dạng retrieval document. | [`FAQEntry`](src/backend/services/faq_matcher.py#L62)<br>[`FAQMatcher`](src/backend/services/faq_matcher.py#L133) |
| [`src/backend/services/ingest_postgres.py`](src/backend/services/ingest_postgres.py) | CLI ingest: lấy document từ PostgreSQL, tạo embedding và upsert vào Chroma; hỗ trợ reset collection và lọc entity type. | [`main()`](src/backend/services/ingest_postgres.py#L23) |
| [`src/backend/services/llm.py`](src/backend/services/llm.py) | Wrapper gọi LLM qua LiteLLM; hỗ trợ primary/backup API key, retry, text response và parse JSON response. | [`LLMService`](src/backend/services/llm.py#L19) |
| [`src/backend/services/memory.py`](src/backend/services/memory.py) | Quản lý conversation memory trên PostgreSQL: session ownership, đọc lịch sử, format prompt context, lấy destination/entity gần đây, append turn và xóa lịch sử. | [`MemoryService`](src/backend/services/memory.py#L15) |
| [`src/backend/services/onnx_embeddings.py`](src/backend/services/onnx_embeddings.py) | Chạy mô hình E5 embedding bằng ONNX Runtime: tokenize batch, mean pooling, L2 normalize và trả vector embedding. | [`OnnxEmbeddingConfig`](src/backend/services/onnx_embeddings.py#L12)<br>[`OnnxE5Embedder`](src/backend/services/onnx_embeddings.py#L21) |
| [`src/backend/services/postgres_loader.py`](src/backend/services/postgres_loader.py) | Đọc các bảng CORE trong PostgreSQL và chuyển từng row/thực thể thành document + metadata dùng để ingest/search trong RAG. | [`load_postgres_documents()`](src/backend/services/postgres_loader.py#L351) |
| [`src/backend/services/query_parser.py`](src/backend/services/query_parser.py) | Chuẩn hóa câu hỏi và phân tích retrieval query: nhận diện destination, intent, generic discovery và tạo query theo từng intent. | [`normalize_text()`](src/backend/services/query_parser.py#L164)<br>[`load_destination_catalog()`](src/backend/services/query_parser.py#L175)<br>[`detect_destinations()`](src/backend/services/query_parser.py#L241)<br>[`detect_destination()`](src/backend/services/query_parser.py#L282)<br>[`detect_intents()`](src/backend/services/query_parser.py#L316)<br>[`detect_intent()`](src/backend/services/query_parser.py#L335)<br>[`build_intent_query()`](src/backend/services/query_parser.py#L340)<br>[`parse_retrieval_query()`](src/backend/services/query_parser.py#L381) |
| [`src/backend/services/rag.py`](src/backend/services/rag.py) | Dịch vụ RAG trung tâm: kết nối Chroma, embedding query/document, semantic search, keyword/hybrid search, named-entity retrieval, dedupe/rerank và build context. | [`RAGService`](src/backend/services/rag.py#L20)<br>[`get_rag_service()`](src/backend/services/rag.py#L1181) |
| [`src/backend/services/source_reranker.py`](src/backend/services/source_reranker.py) | Xếp hạng nguồn/citation dựa trên answer, entity và destination để chọn source phù hợp cho response. | [`SourceReranker`](src/backend/services/source_reranker.py#L61)<br>[`get_source_reranker()`](src/backend/services/source_reranker.py#L611) |
| [`src/backend/services/ticket.py`](src/backend/services/ticket.py) | Service ghi support ticket vào PostgreSQL từ dữ liệu contact, session, issue summary, reason và conversation context. | [`TicketService`](src/backend/services/ticket.py#L10) |

## 5. Backend — Entry & Configuration

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/backend/config.py`](src/backend/config.py) | Khai báo cấu hình backend từ biến môi trường: LLM, PostgreSQL, Chroma, embedding, CORS, auth và các ngưỡng retrieval; cung cấp `get_settings()` dùng chung. | [`Settings`](src/backend/config.py#L8)<br>[`get_settings()`](src/backend/config.py#L93) |
| [`src/backend/main.py`](src/backend/main.py) | Khởi tạo ứng dụng FastAPI, cấu hình CORS, mount các router API và khai báo các endpoint `/health`, `/ready`, `/ask`. | [`health()`](src/backend/main.py#L51)<br>[`AskRequest`](src/backend/main.py#L54)<br>[`ready()`](src/backend/main.py#L59)<br>[`ask()`](src/backend/main.py#L87) |

## 6. PostgreSQL — ORM / Database

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/data_postgre/db/README.md`](src/data_postgre/db/README.md) | Tài liệu mô tả tầng database, nhóm file ORM, cách cài PostgreSQL/pgvector và các lệnh khởi tạo/nạp dữ liệu. | — |
| [`src/data_postgre/db/__init__.py`](src/data_postgre/db/__init__.py) | Điểm export chung cho toàn bộ ORM model CORE và APP; tạo `CORE_TABLES`/`APP_TABLES` để code khác truy cập model theo tên bảng. | — |
| [`src/data_postgre/db/app.py`](src/data_postgre/db/app.py) | Định nghĩa các ORM model dữ liệu ứng dụng: user, auth session, chat session, message, citation, feedback, ticket và event log. | [`AppUser`](src/data_postgre/db/app.py#L46)<br>[`AuthSession`](src/data_postgre/db/app.py#L88)<br>[`ChatSession`](src/data_postgre/db/app.py#L110)<br>[`Message`](src/data_postgre/db/app.py#L141)<br>[`MessageCitation`](src/data_postgre/db/app.py#L186)<br>[`MessageFeedback`](src/data_postgre/db/app.py#L210)<br>[`Ticket`](src/data_postgre/db/app.py#L230)<br>[`EventLog`](src/data_postgre/db/app.py#L276) |
| [`src/data_postgre/db/base.py`](src/data_postgre/db/base.py) | Định nghĩa SQLAlchemy declarative base cho schema `core` và `app`, mixin timestamp/source, quy ước metadata và helper tra bảng. | [`Base`](src/data_postgre/db/base.py#L52)<br>[`AppBase`](src/data_postgre/db/base.py#L58)<br>[`Timestamped`](src/data_postgre/db/base.py#L64)<br>[`Sourced`](src/data_postgre/db/base.py#L78)<br>[`pk_text()`](src/data_postgre/db/base.py#L102)<br>[`by_bare_name()`](src/data_postgre/db/base.py#L107) |
| [`src/data_postgre/db/core.py`](src/data_postgre/db/core.py) | Định nghĩa các ORM model dữ liệu nghiệp vụ CORE: destination, property, room, attraction, golf, MICE, promotion, FAQ, policy, org info, source và các bảng liên kết. | [`IngestRun`](src/data_postgre/db/core.py#L45)<br>[`DataQualityIssue`](src/data_postgre/db/core.py#L65)<br>[`Brand`](src/data_postgre/db/core.py#L101)<br>[`Source`](src/data_postgre/db/core.py#L109)<br>[`Destination`](src/data_postgre/db/core.py#L138)<br>[`DestinationAlias`](src/data_postgre/db/core.py#L167)<br>[`Complex`](src/data_postgre/db/core.py#L194)<br>[`Media`](src/data_postgre/db/core.py#L220)<br>… (+28) |
| [`src/data_postgre/db/errors.py`](src/data_postgre/db/errors.py) | Helper đọc lỗi SQLAlchemy/driver: lấy SQLSTATE, tên constraint, nhận biết integrity violation và tạo mô tả lỗi. | [`sqlstate()`](src/data_postgre/db/errors.py#L38)<br>[`constraint_name()`](src/data_postgre/db/errors.py#L62)<br>[`is_integrity_violation()`](src/data_postgre/db/errors.py#L81)<br>[`describe()`](src/data_postgre/db/errors.py#L90) |
| [`src/data_postgre/db/migrations/20260809_auth_staff.sql`](src/data_postgre/db/migrations/20260809_auth_staff.sql) | Migration SQL bổ sung phone/role/is_active cho user, tạo `auth_session`, mở rộng ticket với contact/assignment/conversation fields và index liên quan. | — |

## 7. PostgreSQL — Normalize / Adapters

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/data_postgre/normalize/__init__.py`](src/data_postgre/normalize/__init__.py) | Đánh dấu package `normalize` chứa pipeline chuẩn hóa dữ liệu crawl trước khi ghi vào schema CORE. | — |
| [`src/data_postgre/normalize/adapters/__init__.py`](src/data_postgre/normalize/adapters/__init__.py) | Đánh dấu package các adapter chuyển từng nhóm dữ liệu crawl sang row chuẩn hóa cho PostgreSQL. | — |
| [`src/data_postgre/normalize/adapters/entertainment.py`](src/data_postgre/normalize/adapters/entertainment.py) | Adapter chuẩn hóa dữ liệu entertainment/VinWonders thành attraction, destination highlight, page link và các detail liên quan. | [`parse()`](src/data_postgre/normalize/adapters/entertainment.py#L66) |
| [`src/data_postgre/normalize/adapters/hotels.py`](src/data_postgre/normalize/adapters/hotels.py) | Adapter chuẩn hóa dữ liệu hotel/property: property, room, amenity và dining service. | [`parse()`](src/data_postgre/normalize/adapters/hotels.py#L44) |
| [`src/data_postgre/normalize/adapters/promotions.py`](src/data_postgre/normalize/adapters/promotions.py) | Adapter chuẩn hóa promotion: destination, benefit, code, section, block, term, relation, tag và property áp dụng. | [`parse()`](src/data_postgre/normalize/adapters/promotions.py#L65)<br>[`build_tags()`](src/data_postgre/normalize/adapters/promotions.py#L187) |
| [`src/data_postgre/normalize/adapters/simple.py`](src/data_postgre/normalize/adapters/simple.py) | Adapter cho các nguồn còn lại: golf, MICE, FAQ, regulations/policy và About/organization. | [`parse_golf()`](src/data_postgre/normalize/adapters/simple.py#L43)<br>[`parse_mice()`](src/data_postgre/normalize/adapters/simple.py#L170)<br>[`parse_faqs()`](src/data_postgre/normalize/adapters/simple.py#L267)<br>[`parse_regulations()`](src/data_postgre/normalize/adapters/simple.py#L324)<br>[`parse_about()`](src/data_postgre/normalize/adapters/simple.py#L393)<br>[`parse()`](src/data_postgre/normalize/adapters/simple.py#L436) |
| [`src/data_postgre/normalize/common.py`](src/data_postgre/normalize/common.py) | Các parser/helper chuẩn hóa kiểu dữ liệu dùng chung như stable ID, money, area, specifications, date, time range, language, domain và URL. | [`stable_id()`](src/data_postgre/normalize/common.py#L24)<br>[`Money`](src/data_postgre/normalize/common.py#L45)<br>[`parse_money()`](src/data_postgre/normalize/common.py#L72)<br>[`parse_area()`](src/data_postgre/normalize/common.py#L110)<br>[`parse_specifications()`](src/data_postgre/normalize/common.py#L146)<br>[`normalize_language()`](src/data_postgre/normalize/common.py#L167)<br>[`parse_int()`](src/data_postgre/normalize/common.py#L180)<br>[`parse_iso_date()`](src/data_postgre/normalize/common.py#L203)<br>… (+5) |
| [`src/data_postgre/normalize/context.py`](src/data_postgre/normalize/context.py) | Định nghĩa context dùng chung cho các adapter: gom row theo bảng, ghi data-quality issue và resolve destination/complex/source/media/link. | [`Issue`](src/data_postgre/normalize/context.py#L27)<br>[`Rows`](src/data_postgre/normalize/context.py#L39)<br>[`Context`](src/data_postgre/normalize/context.py#L83) |
| [`src/data_postgre/normalize/destinations.yaml`](src/data_postgre/normalize/destinations.yaml) | Master data viết tay cho destination, alias và complex; dùng làm khóa chuẩn để các adapter map chuỗi địa điểm trong dữ liệu crawl. | — |
| [`src/data_postgre/normalize/text.py`](src/data_postgre/normalize/text.py) | Các hàm chuẩn hóa text dùng chung: clean text, bỏ dấu, normalize alias và slugify. | [`clean_text()`](src/data_postgre/normalize/text.py#L20)<br>[`strip_accents()`](src/data_postgre/normalize/text.py#L37)<br>[`normalize_alias()`](src/data_postgre/normalize/text.py#L45)<br>[`slugify()`](src/data_postgre/normalize/text.py#L67) |

## 8. PostgreSQL — Run notes

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/data_postgre/run.md`](src/data_postgre/run.md) | Ghi lại quy trình migrate schema PostgreSQL, kiểm tra Alembic và chunk/ingest lại toàn bộ PostgreSQL sang Chroma. | — |

## 9. Crawl Data — About / FAQ / Regulations / Notebook

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/data_crawl/About/vinpearl_about.json`](src/data_crawl/About/vinpearl_about.json) | Dataset nội dung trang About Vinpearl: headline/introduction, danh sách hotels & resorts, signature packages, MICE/meeting-events và company info. | — |
| [`src/data_crawl/Faqs/vinpearl_faqs.json`](src/data_crawl/Faqs/vinpearl_faqs.json) | Dataset FAQ Vinpearl gồm category và danh sách câu hỏi–trả lời; source hiện có 174 item FAQ. | — |
| [`src/data_crawl/Regulations/vinpearl_regulations.json`](src/data_crawl/Regulations/vinpearl_regulations.json) | Dataset quy định/chính sách đã crawl: metadata tài liệu, headings, sections, lists, tables/plain text và danh sách lỗi crawl. | — |
| [`src/data_crawl/vinpearl_crawl.ipynb`](src/data_crawl/vinpearl_crawl.ipynb) | Notebook crawl/khảo sát dữ liệu Vinpearl/VinWonders: thử nghiệm request/Selenium/BeautifulSoup và tổng hợp các nhóm hotel, entertainment cùng dữ liệu liên quan. | — |

## 10. Crawl Data — Golf

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/data_crawl/Golf/cape_wickham_golf_links.json`](src/data_crawl/Golf/cape_wickham_golf_links.json) | Dữ liệu sân golf Cape Wickham: thông tin chung, location, amenities, experiences, course maps và source URLs. | — |
| [`src/data_crawl/Golf/golf_hai_phong.json`](src/data_crawl/Golf/golf_hai_phong.json) | Dữ liệu sân golf tại Hải Phòng: thông tin chung, location, amenities, experiences, course maps và source URLs. | — |
| [`src/data_crawl/Golf/golf_leman.json`](src/data_crawl/Golf/golf_leman.json) | Dữ liệu sân golf Leman: thông tin chung, location, amenities, experiences, course maps và source URLs. | — |
| [`src/data_crawl/Golf/golf_nam_hoi_an.json`](src/data_crawl/Golf/golf_nam_hoi_an.json) | Dữ liệu sân golf Nam Hội An: thông tin chung, location, amenities, experiences, course maps và source URLs. | — |
| [`src/data_crawl/Golf/golf_nha_trang.json`](src/data_crawl/Golf/golf_nha_trang.json) | Dữ liệu sân golf Nha Trang: thông tin chung, location, amenities, experiences, course maps và source URLs. | — |
| [`src/data_crawl/Golf/golf_phu_quoc.json`](src/data_crawl/Golf/golf_phu_quoc.json) | Dữ liệu sân golf Phú Quốc: thông tin chung, location, amenities, experiences, course maps và source URLs. | — |

## 11. Crawl Data — Promotions

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/data_crawl/Promotion/active_promotions.json`](src/data_crawl/Promotion/active_promotions.json) | Tập hợp các promotion đang ở trạng thái active trên toàn bộ dataset. File chứa 27 promotion. | — |
| [`src/data_crawl/Promotion/hai-phong-promotions.json`](src/data_crawl/Promotion/hai-phong-promotions.json) | Promotion được nhóm theo destination Hải Phòng. File chứa 10 promotion. | — |
| [`src/data_crawl/Promotion/hanoi-promotions.json`](src/data_crawl/Promotion/hanoi-promotions.json) | Promotion được nhóm theo destination Hà Nội. File chứa 6 promotion. | — |
| [`src/data_crawl/Promotion/ho-chi-minh-city-promotions.json`](src/data_crawl/Promotion/ho-chi-minh-city-promotions.json) | Promotion được nhóm theo destination Thành phố Hồ Chí Minh. File chứa 5 promotion. | — |
| [`src/data_crawl/Promotion/hoi-an-promotions.json`](src/data_crawl/Promotion/hoi-an-promotions.json) | Promotion được nhóm theo destination Hội An/Nam Hội An. File chứa 14 promotion. | — |
| [`src/data_crawl/Promotion/nghe-an-promotions.json`](src/data_crawl/Promotion/nghe-an-promotions.json) | Promotion được nhóm theo destination Nghệ An. File chứa 10 promotion. | — |
| [`src/data_crawl/Promotion/nha-trang-promotions.json`](src/data_crawl/Promotion/nha-trang-promotions.json) | Promotion được nhóm theo destination Nha Trang. File chứa 20 promotion. | — |
| [`src/data_crawl/Promotion/others-promotions.json`](src/data_crawl/Promotion/others-promotions.json) | Promotion của các destination còn lại/nhóm Nationwide/Unknown theo cấu trúc groups. File chứa 15 promotion. | — |
| [`src/data_crawl/Promotion/phu-quoc-promotions.json`](src/data_crawl/Promotion/phu-quoc-promotions.json) | Promotion được nhóm theo destination Phú Quốc. File chứa 17 promotion. | — |

## 12. Frontend — Entry / Config / Types

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/App.jsx`](src/frontend/App.jsx) | Component gốc: bọc ứng dụng bằng BrowserRouter, AuthProvider, LanguageProvider và render `AppRoutes`. | [`App()`](src/frontend/App.jsx#L6) |
| [`src/frontend/README.md`](src/frontend/README.md) | Tài liệu hướng dẫn cấu trúc frontend React/Vite, route, kết nối API, dữ liệu cục bộ, i18n và cách chạy project. | — |
| [`src/frontend/i18n.js`](src/frontend/i18n.js) | Khởi tạo i18next, đăng ký 5 locale `en/vi/ko/ja/zh`, chọn ngôn ngữ từ localStorage và cấu hình fallback. | — |
| [`src/frontend/index.css`](src/frontend/index.css) | CSS toàn cục: design tokens, typography, reset cơ bản, màu sắc và các utility class dùng chung. | — |
| [`src/frontend/index.html`](src/frontend/index.html) | HTML shell của frontend: khai báo metadata, phần tử `#root` và entry script để mount ứng dụng React. | — |
| [`src/frontend/main.jsx`](src/frontend/main.jsx) | Entry point React: nạp i18n/CSS toàn cục và mount `<App />` vào `#root`. | — |
| [`src/frontend/types.js`](src/frontend/types.js) | Định nghĩa kiểu dữ liệu JSDoc dùng chung cho frontend: Language, Hotel, Room, Destination, ChatMessage, Ticket, User, Promotion, SourceItem và paginated response. | — |

## 13. Frontend — Routes

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/routes/AppRoutes.jsx`](src/frontend/routes/AppRoutes.jsx) | Khai báo toàn bộ React Router route, layout dùng Header/Footer/ChatWidget và guard role cho staff/admin. | [`AppLayout()`](src/frontend/routes/AppRoutes.jsx#L21)<br>[`RequireRole()`](src/frontend/routes/AppRoutes.jsx#L33)<br>[`AppRoutes()`](src/frontend/routes/AppRoutes.jsx#L41) |

## 14. Frontend — Context

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/context/AuthContext.jsx`](src/frontend/context/AuthContext.jsx) | Context quản lý trạng thái đăng nhập: load current user, login, register, logout và cung cấp auth state cho component. | [`AuthProvider()`](src/frontend/context/AuthContext.jsx#L11)<br>[`useAuth()`](src/frontend/context/AuthContext.jsx#L57) |
| [`src/frontend/context/LanguageContext.jsx`](src/frontend/context/LanguageContext.jsx) | Context quản lý ngôn ngữ giao diện, đổi locale i18next, lưu lựa chọn và expose dictionary/translator cho component. | [`LanguageProvider()`](src/frontend/context/LanguageContext.jsx#L13)<br>[`useLanguage()`](src/frontend/context/LanguageContext.jsx#L46) |

## 15. Frontend — Services

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/services/api.js`](src/frontend/services/api.js) | Tập trung toàn bộ giao tiếp frontend ↔ backend và browser chat storage: catalog, promotion, chat, ticket, auth, staff APIs và session/message helpers. | [`currentLanguage()`](src/frontend/services/api.js#L4)<br>[`apiFetch()`](src/frontend/services/api.js#L9)<br>[`createSessionId()`](src/frontend/services/api.js#L17)<br>[`currentPageBootId()`](src/frontend/services/api.js#L25)<br>[`readStoredSession()`](src/frontend/services/api.js#L34)<br>[`writeStoredSession()`](src/frontend/services/api.js#L43)<br>[`setChatSessionId()`](src/frontend/services/api.js#L59)<br>[`clearChatSessionId()`](src/frontend/services/api.js#L63)<br>… (+32) |
| [`src/frontend/services/parseStructuredMessage.js`](src/frontend/services/parseStructuredMessage.js) | Parser biến raw AI text/structured content thành cấu trúc UI gồm lead, context, topic, timeline stop, source và action. | [`guessTopicIcon()`](src/frontend/services/parseStructuredMessage.js#L41)<br>[`getImplicitTopicTitle()`](src/frontend/services/parseStructuredMessage.js#L48)<br>[`stripMarkdownBold()`](src/frontend/services/parseStructuredMessage.js#L62)<br>[`extractLeadingEmoji()`](src/frontend/services/parseStructuredMessage.js#L66)<br>[`cleanBulletText()`](src/frontend/services/parseStructuredMessage.js#L72)<br>[`isBullet()`](src/frontend/services/parseStructuredMessage.js#L76)<br>[`isHeadingLine()`](src/frontend/services/parseStructuredMessage.js#L80)<br>[`parseTimeFromLine()`](src/frontend/services/parseStructuredMessage.js#L99)<br>… (+3) |

## 16. Frontend — Components

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/components/AboutHotelsGrid.jsx`](src/frontend/components/AboutHotelsGrid.jsx) | Grid/slider khách sạn dùng trên trang About; gọi API lấy hotel và hiển thị card/liên kết chi tiết. | [`AboutHotelsGrid()`](src/frontend/components/AboutHotelsGrid.jsx#L10) |
| [`src/frontend/components/ActionRow.jsx`](src/frontend/components/ActionRow.jsx) | Render các action button được truyền từ structured AI response và map action sang route frontend tương ứng. | [`ActionRow()`](src/frontend/components/ActionRow.jsx#L11) |
| [`src/frontend/components/ChatHistorySidebar.jsx`](src/frontend/components/ChatHistorySidebar.jsx) | Sidebar lịch sử chat: hiển thị danh sách session, chọn phiên, tạo chat mới, xóa phiên và format thời gian/label. | [`formatSessionTime()`](src/frontend/components/ChatHistorySidebar.jsx#L62)<br>[`ChatHistorySidebar()`](src/frontend/components/ChatHistorySidebar.jsx#L87) |
| [`src/frontend/components/ChatWidget.jsx`](src/frontend/components/ChatWidget.jsx) | Widget chat nổi dùng trên các trang: mở/đóng panel, gửi message tới Chat API, lưu message browser cho anonymous user và render AI response. | [`ChatWidget()`](src/frontend/components/ChatWidget.jsx#L11) |
| [`src/frontend/components/ContextStrip.jsx`](src/frontend/components/ContextStrip.jsx) | Hiển thị một dải context ngắn (icon + text) trong structured AI message. | [`ContextStrip()`](src/frontend/components/ContextStrip.jsx#L8) |
| [`src/frontend/components/DestinationCard.jsx`](src/frontend/components/DestinationCard.jsx) | Card destination có ảnh/tên/thông tin và liên kết sang trang search theo destination. | [`DestinationCard()`](src/frontend/components/DestinationCard.jsx#L8) |
| [`src/frontend/components/FilterSidebar.jsx`](src/frontend/components/FilterSidebar.jsx) | Sidebar điều khiển filter trên trang tìm kiếm khách sạn và reset các tiêu chí lọc. | [`FilterSidebar()`](src/frontend/components/FilterSidebar.jsx#L5) |
| [`src/frontend/components/Footer.jsx`](src/frontend/components/Footer.jsx) | Footer dùng chung của website: nhóm liên kết, thông tin thương hiệu/liên hệ và các phần cuối trang. | [`Footer()`](src/frontend/components/Footer.jsx#L20) |
| [`src/frontend/components/Header.jsx`](src/frontend/components/Header.jsx) | Header/navigation dùng chung: menu, trạng thái đăng nhập, chọn ngôn ngữ và navigation theo route. | [`Header()`](src/frontend/components/Header.jsx#L18) |
| [`src/frontend/components/HeroSearch.jsx`](src/frontend/components/HeroSearch.jsx) | Khối hero search trên trang chủ: nhận từ khóa/destination và điều hướng sang trang search. | [`HeroSearch()`](src/frontend/components/HeroSearch.jsx#L17) |
| [`src/frontend/components/HotelCard.jsx`](src/frontend/components/HotelCard.jsx) | Card hiển thị thông tin hotel/property, giá/địa điểm/tiện ích và điều hướng sang chi tiết hoặc chat/search. | [`HotelCard()`](src/frontend/components/HotelCard.jsx#L8) |
| [`src/frontend/components/InlineMarkdown.jsx`](src/frontend/components/InlineMarkdown.jsx) | Renderer Markdown inline nhẹ cho text trong component, dùng để hiển thị định dạng như bold/code/link ở cấp inline. | [`InlineMarkdown()`](src/frontend/components/InlineMarkdown.jsx#L8) |
| [`src/frontend/components/MarkdownContent.jsx`](src/frontend/components/MarkdownContent.jsx) | Renderer nội dung Markdown dạng block: paragraph, list và inline formatting. | [`trimTrailingPunctuation()`](src/frontend/components/MarkdownContent.jsx#L5)<br>[`renderInline()`](src/frontend/components/MarkdownContent.jsx#L9)<br>[`flushParagraph()`](src/frontend/components/MarkdownContent.jsx#L52)<br>[`flushList()`](src/frontend/components/MarkdownContent.jsx#L70)<br>[`MarkdownContent()`](src/frontend/components/MarkdownContent.jsx#L88) |
| [`src/frontend/components/Rail.jsx`](src/frontend/components/Rail.jsx) | Render timeline dọc cho các stop trong itinerary/structured topic, gồm thời gian, tên và mô tả. | [`Stop()`](src/frontend/components/Rail.jsx#L8)<br>[`Rail()`](src/frontend/components/Rail.jsx#L27) |
| [`src/frontend/components/RichMessage.jsx`](src/frontend/components/RichMessage.jsx) | Renderer message giàu nội dung: tokenize text, link, ảnh inline và source chip; dùng cho user/assistant message. | [`tokenize()`](src/frontend/components/RichMessage.jsx#L16)<br>[`InlineImage()`](src/frontend/components/RichMessage.jsx#L48)<br>[`InlineLink()`](src/frontend/components/RichMessage.jsx#L103)<br>[`RichMessage()`](src/frontend/components/RichMessage.jsx#L141)<br>[`SourceChips()`](src/frontend/components/RichMessage.jsx#L180)<br>[`SourceChip()`](src/frontend/components/RichMessage.jsx#L198) |
| [`src/frontend/components/SkeletonTopicCard.jsx`](src/frontend/components/SkeletonTopicCard.jsx) | Skeleton/loading UI mô phỏng topic card khi structured content đang tải. | [`SkeletonTopicCard()`](src/frontend/components/SkeletonTopicCard.jsx#L7)<br>[`SkeletonLoading()`](src/frontend/components/SkeletonTopicCard.jsx#L38) |
| [`src/frontend/components/SourcePills.jsx`](src/frontend/components/SourcePills.jsx) | Hiển thị danh sách source/citation dạng pill, cho phép mở link ngoài và mở rộng khi có nhiều nguồn. | [`SourcePills()`](src/frontend/components/SourcePills.jsx#L10) |
| [`src/frontend/components/StructuredMessage.jsx`](src/frontend/components/StructuredMessage.jsx) | Renderer cấp cao cho AI response: parse message rồi ghép ContextStrip, TopicCard, Rail, SourcePills, ActionRow hoặc fallback sang RichMessage. | [`StructuredMessage()`](src/frontend/components/StructuredMessage.jsx#L18) |
| [`src/frontend/components/TopicCard.jsx`](src/frontend/components/TopicCard.jsx) | Card topic có thể đóng/mở; hiển thị tiêu đề, subtitle, list item và timeline `Rail`. | [`TopicCard()`](src/frontend/components/TopicCard.jsx#L12) |

## 17. Frontend — Pages

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/pages/About.jsx`](src/frontend/pages/About.jsx) | Trang giới thiệu Vinpearl: tải About API, có dữ liệu JSON fallback và hiển thị thông tin tổ chức/hotel/highlight. | [`About()`](src/frontend/pages/About.jsx#L45) |
| [`src/frontend/pages/AdminStaff.jsx`](src/frontend/pages/AdminStaff.jsx) | Trang admin quản lý tài khoản staff: tải danh sách staff, tạo staff mới và cập nhật thông tin/role/trạng thái. | [`AdminStaff()`](src/frontend/pages/AdminStaff.jsx#L7) |
| [`src/frontend/pages/Chatbot.jsx`](src/frontend/pages/Chatbot.jsx) | Trang chat đầy đủ: quản lý session/history, gửi câu hỏi tới Agent, tải lại hội thoại, render message/source/related hotel và tạo chat mới. | [`displayTime()`](src/frontend/pages/Chatbot.jsx#L33)<br>[`historyMessageToUi()`](src/frontend/pages/Chatbot.jsx#L39)<br>[`loadStoredDraft()`](src/frontend/pages/Chatbot.jsx#L53)<br>[`saveStoredDraft()`](src/frontend/pages/Chatbot.jsx#L61)<br>[`clearStoredDraft()`](src/frontend/pages/Chatbot.jsx#L69)<br>[`historyButtonLabel()`](src/frontend/pages/Chatbot.jsx#L77)<br>[`newChatLabel()`](src/frontend/pages/Chatbot.jsx#L87)<br>[`closeHistoryLabel()`](src/frontend/pages/Chatbot.jsx#L97)<br>… (+1) |
| [`src/frontend/pages/Home.jsx`](src/frontend/pages/Home.jsx) | Trang chủ: tải destination, hotel, promotion và dựng các section khám phá, tìm kiếm, featured content. | [`Home()`](src/frontend/pages/Home.jsx#L11) |
| [`src/frontend/pages/HotelDetail.jsx`](src/frontend/pages/HotelDetail.jsx) | Trang chi tiết hotel/property: lấy `hotelId`, gọi detail API và hiển thị mô tả, room, amenity, dining, location và source. | [`formatPrice()`](src/frontend/pages/HotelDetail.jsx#L8)<br>[`localizedCopy()`](src/frontend/pages/HotelDetail.jsx#L17)<br>[`RoomPrice()`](src/frontend/pages/HotelDetail.jsx#L21)<br>[`HotelDetail()`](src/frontend/pages/HotelDetail.jsx#L52) |
| [`src/frontend/pages/Login.jsx`](src/frontend/pages/Login.jsx) | Trang đăng nhập: thu thập credential, gọi AuthContext login và điều hướng sau khi xác thực. | [`Login()`](src/frontend/pages/Login.jsx#L8) |
| [`src/frontend/pages/PromotionDetail.jsx`](src/frontend/pages/PromotionDetail.jsx) | Trang chi tiết một ưu đãi: tải promotion theo ID và render summary, date, benefit, section, block, term, link/CTA. | [`normalizeText()`](src/frontend/pages/PromotionDetail.jsx#L32)<br>[`formatDate()`](src/frontend/pages/PromotionDetail.jsx#L36)<br>[`PlainText()`](src/frontend/pages/PromotionDetail.jsx#L47)<br>[`StructuredBlock()`](src/frontend/pages/PromotionDetail.jsx#L53)<br>[`TextList()`](src/frontend/pages/PromotionDetail.jsx#L122)<br>[`PromotionDetail()`](src/frontend/pages/PromotionDetail.jsx#L132) |
| [`src/frontend/pages/Promotions.jsx`](src/frontend/pages/Promotions.jsx) | Trang danh sách ưu đãi: tải promotion/destination, search/filter theo destination/trạng thái và điều hướng tới promotion detail. | [`PromotionSelect()`](src/frontend/pages/Promotions.jsx#L20)<br>[`formatDate()`](src/frontend/pages/Promotions.jsx#L74)<br>[`getDestinations()`](src/frontend/pages/Promotions.jsx#L86)<br>[`Promotions()`](src/frontend/pages/Promotions.jsx#L99) |
| [`src/frontend/pages/Register.jsx`](src/frontend/pages/Register.jsx) | Trang đăng ký: nhập name/email/phone/password, gọi AuthContext register và điều hướng sau khi tạo tài khoản. | [`Register()`](src/frontend/pages/Register.jsx#L8) |
| [`src/frontend/pages/Regulations.jsx`](src/frontend/pages/Regulations.jsx) | Trang quy định/chính sách: đọc JSON regulations, hỗ trợ tìm tài liệu và render heading, section, list, table theo ngôn ngữ giao diện. | [`getDocTitle()`](src/frontend/pages/Regulations.jsx#L54)<br>[`normalizeCell()`](src/frontend/pages/Regulations.jsx#L60)<br>[`getTableKind()`](src/frontend/pages/Regulations.jsx#L64)<br>[`buildContentBlocks()`](src/frontend/pages/Regulations.jsx#L91)<br>[`translateText()`](src/frontend/pages/Regulations.jsx#L157)<br>[`InlineText()`](src/frontend/pages/Regulations.jsx#L164)<br>[`translateCheckInCell()`](src/frontend/pages/Regulations.jsx#L212)<br>[`translateTableHeader()`](src/frontend/pages/Regulations.jsx#L263)<br>… (+2) |
| [`src/frontend/pages/SearchResults.jsx`](src/frontend/pages/SearchResults.jsx) | Trang kết quả tìm kiếm hotel/property: đọc query params, tải destination/hotel, áp dụng filter và render HotelCard. | [`SearchResults()`](src/frontend/pages/SearchResults.jsx#L10) |
| [`src/frontend/pages/StaffTickets.jsx`](src/frontend/pages/StaffTickets.jsx) | Trang staff/admin xử lý ticket: tải ticket, filter/hiển thị trạng thái và cập nhật ticket. | [`StaffTickets()`](src/frontend/pages/StaffTickets.jsx#L8) |
| [`src/frontend/pages/Ticket.jsx`](src/frontend/pages/Ticket.jsx) | Trang support ticket cho user: gửi form ticket và tải danh sách ticket của tài khoản hiện tại. | [`Ticket()`](src/frontend/pages/Ticket.jsx#L18) |

## 18. Frontend — Locales

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/locales/en.json`](src/frontend/locales/en.json) | Bộ chuỗi giao diện tiếng Anh. | — |
| [`src/frontend/locales/ja.json`](src/frontend/locales/ja.json) | Bộ chuỗi giao diện tiếng Nhật. | — |
| [`src/frontend/locales/ko.json`](src/frontend/locales/ko.json) | Bộ chuỗi giao diện tiếng Hàn. | — |
| [`src/frontend/locales/vi.json`](src/frontend/locales/vi.json) | Bộ chuỗi giao diện tiếng Việt. | — |
| [`src/frontend/locales/zh.json`](src/frontend/locales/zh.json) | Bộ chuỗi giao diện tiếng Trung. | — |

## 19. Frontend — Local Data / Media

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/data/mediaAssets.js`](src/frontend/data/mediaAssets.js) | Registry URL media dùng chung: logo, hero banner, ảnh hotel/destination và video. | — |
| [`src/frontend/data/mockData.js`](src/frontend/data/mockData.js) | Dữ liệu mock cục bộ cho destination, hotel và combo dùng ở các phần frontend cần dữ liệu mẫu/fallback. | — |

## 20. Frontend — Styles / Components

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/styles/components/AboutHotelsGrid.css`](src/frontend/styles/components/AboutHotelsGrid.css) | CSS riêng cho component `AboutHotelsGrid`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/ChatHistorySidebar.css`](src/frontend/styles/components/ChatHistorySidebar.css) | CSS riêng cho component `ChatHistorySidebar`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/ChatWidget.css`](src/frontend/styles/components/ChatWidget.css) | CSS riêng cho component `ChatWidget`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/DestinationCard.css`](src/frontend/styles/components/DestinationCard.css) | CSS riêng cho component `DestinationCard`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/FilterSidebar.css`](src/frontend/styles/components/FilterSidebar.css) | CSS riêng cho component `FilterSidebar`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/Footer.css`](src/frontend/styles/components/Footer.css) | CSS riêng cho component `Footer`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/Header.css`](src/frontend/styles/components/Header.css) | CSS riêng cho component `Header`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/HeroSearch.css`](src/frontend/styles/components/HeroSearch.css) | CSS riêng cho component `HeroSearch`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/HotelCard.css`](src/frontend/styles/components/HotelCard.css) | CSS riêng cho component `HotelCard`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/RichMessage.css`](src/frontend/styles/components/RichMessage.css) | CSS riêng cho component `RichMessage`: layout, typography, state và responsive của component. | — |
| [`src/frontend/styles/components/StructuredMessage.css`](src/frontend/styles/components/StructuredMessage.css) | CSS riêng cho component `StructuredMessage`: layout, typography, state và responsive của component. | — |

## 21. Frontend — Styles / Pages

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/styles/pages/About.css`](src/frontend/styles/pages/About.css) | CSS riêng cho trang `About`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/AdminStaff.css`](src/frontend/styles/pages/AdminStaff.css) | CSS riêng cho trang `AdminStaff`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/Chatbot.css`](src/frontend/styles/pages/Chatbot.css) | CSS riêng cho trang `Chatbot`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/Home.css`](src/frontend/styles/pages/Home.css) | CSS riêng cho trang `Home`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/HotelDetail.css`](src/frontend/styles/pages/HotelDetail.css) | CSS riêng cho trang `HotelDetail`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/Login.css`](src/frontend/styles/pages/Login.css) | CSS riêng cho trang `Login`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/PromotionDetail.css`](src/frontend/styles/pages/PromotionDetail.css) | CSS riêng cho trang `PromotionDetail`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/Promotions.css`](src/frontend/styles/pages/Promotions.css) | CSS riêng cho trang `Promotions`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/Register.css`](src/frontend/styles/pages/Register.css) | CSS riêng cho trang `Register`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/Regulations.css`](src/frontend/styles/pages/Regulations.css) | CSS riêng cho trang `Regulations`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/SearchResults.css`](src/frontend/styles/pages/SearchResults.css) | CSS riêng cho trang `SearchResults`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/StaffTickets.css`](src/frontend/styles/pages/StaffTickets.css) | CSS riêng cho trang `StaffTickets`: bố cục, section, form/card/table và responsive của page. | — |
| [`src/frontend/styles/pages/Ticket.css`](src/frontend/styles/pages/Ticket.css) | CSS riêng cho trang `Ticket`: bố cục, section, form/card/table và responsive của page. | — |

## 22. Frontend — Styles / Routes

| File | Chức năng | Thành phần chính |
|---|---|---|
| [`src/frontend/styles/routes/AppRoutes.css`](src/frontend/styles/routes/AppRoutes.css) | CSS cho layout/router `AppRoutes` và vùng bố cục chung của các route. | — |

## 23. Mapping nhanh — Agent workflow → file

| Node / bước | File triển khai | Function chính |
|---|---|---|
| `load_memory` | [`src/backend/agents/nodes/memory.py`](src/backend/agents/nodes/memory.py) | [`load_conversation_memory()`](src/backend/agents/nodes/memory.py#L5) |
| `guardrail` | [`src/backend/agents/nodes/guardrail.py`](src/backend/agents/nodes/guardrail.py) | [`enforce_input_guardrail()`](src/backend/agents/nodes/guardrail.py#L106) |
| `language` | [`src/backend/agents/nodes/language.py`](src/backend/agents/nodes/language.py) | [`detect_language_and_translate()`](src/backend/agents/nodes/language.py#L105) |
| `resolve_context` | [`src/backend/agents/nodes/context_resolver.py`](src/backend/agents/nodes/context_resolver.py) | [`resolve_conversation_context()`](src/backend/agents/nodes/context_resolver.py#L166) |
| `classify` | [`src/backend/agents/nodes/classify.py`](src/backend/agents/nodes/classify.py) | [`classify_input()`](src/backend/agents/nodes/classify.py#L54) |
| `retrieve` | [`src/backend/agents/nodes/retrieval.py`](src/backend/agents/nodes/retrieval.py) | [`retrieve_context()`](src/backend/agents/nodes/retrieval.py#L91) |
| `support_triage` | [`src/backend/agents/nodes/support_triage.py`](src/backend/agents/nodes/support_triage.py) | [`analyze_support_request()`](src/backend/agents/nodes/support_triage.py#L442) |
| `assess` | [`src/backend/agents/nodes/retrieval.py`](src/backend/agents/nodes/retrieval.py) | [`assess_information()`](src/backend/agents/nodes/retrieval.py#L224) |
| `answer` | [`src/backend/agents/nodes/answer.py`](src/backend/agents/nodes/answer.py) | [`generate_answer()`](src/backend/agents/nodes/answer.py#L34) |
| `grounding` | [`src/backend/agents/nodes/grounding.py`](src/backend/agents/nodes/grounding.py) | [`validate_grounding()`](src/backend/agents/nodes/grounding.py#L6) |
| `ticket` | [`src/backend/agents/nodes/ticket.py`](src/backend/agents/nodes/ticket.py) | [`create_ticket()`](src/backend/agents/nodes/ticket.py#L72) |
| `language_guard` | [`src/backend/agents/nodes/language_guard.py`](src/backend/agents/nodes/language_guard.py) | [`enforce_response_language()`](src/backend/agents/nodes/language_guard.py#L7) |
| `save_memory` | [`src/backend/agents/nodes/memory.py`](src/backend/agents/nodes/memory.py) | [`save_conversation_memory()`](src/backend/agents/nodes/memory.py#L46) |

## 24. Mapping nhanh — API → file

| Nhóm API | File | Nội dung chính |
|---|---|---|
| Chat & history | [`src/backend/api/routes.py`](src/backend/api/routes.py) | Chat Agent, source/citation, danh sách session, message history, xóa history |
| Authentication | [`src/backend/api/auth_routes.py`](src/backend/api/auth_routes.py) | Register/login/logout/me, bootstrap admin, quản lý staff |
| Catalog | [`src/backend/api/catalog_routes.py`](src/backend/api/catalog_routes.py) | Destination và property/hotel catalog |
| Promotions | [`src/backend/api/promotions_routes.py`](src/backend/api/promotions_routes.py) | Danh sách và chi tiết promotion |
| About | [`src/backend/api/about_routes.py`](src/backend/api/about_routes.py) | Thông tin About/organization |
| User tickets | [`src/backend/api/ticket_routes.py`](src/backend/api/ticket_routes.py) | Tạo/xem ticket của user |
| Staff tickets | [`src/backend/api/staff_routes.py`](src/backend/api/staff_routes.py) | Xem/cập nhật ticket cho staff/admin |

## 25. Mapping nhanh — Frontend route → page

| Route | Page | Chức năng |
|---|---|---|
| `/` | [`Home.jsx`](src/frontend/pages/Home.jsx) | Trang chủ |
| `/about` | [`About.jsx`](src/frontend/pages/About.jsx) | Giới thiệu |
| `/search` | [`SearchResults.jsx`](src/frontend/pages/SearchResults.jsx) | Tìm kiếm property/hotel |
| `/hotels/:hotelId` | [`HotelDetail.jsx`](src/frontend/pages/HotelDetail.jsx) | Chi tiết hotel/property |
| `/promotions` | [`Promotions.jsx`](src/frontend/pages/Promotions.jsx) | Danh sách promotion |
| `/promotions/:promotionId` | [`PromotionDetail.jsx`](src/frontend/pages/PromotionDetail.jsx) | Chi tiết promotion |
| `/regulations` | [`Regulations.jsx`](src/frontend/pages/Regulations.jsx) | Quy định/chính sách |
| `/chat`, `/chatbot` | [`Chatbot.jsx`](src/frontend/pages/Chatbot.jsx) | Trang AI chat đầy đủ |
| `/support` | [`Ticket.jsx`](src/frontend/pages/Ticket.jsx) | Support ticket cho user |
| `/login` | [`Login.jsx`](src/frontend/pages/Login.jsx) | Đăng nhập |
| `/register` | [`Register.jsx`](src/frontend/pages/Register.jsx) | Đăng ký |
| `/staff/tickets` | [`StaffTickets.jsx`](src/frontend/pages/StaffTickets.jsx) | Xử lý ticket cho staff/admin |
| `/admin/staff` | [`AdminStaff.jsx`](src/frontend/pages/AdminStaff.jsx) | Quản lý staff cho admin |

# RD NGẮN – GỘP DATA + MIGRATE POSTGRESQL + CHUNK LẠI

1. Tạo migration gộp bảng / chuyển schema
alembic revision -m "merge tables and move to core app schemas"

2. Kiểm tra syntax migration
python -m py_compile .\alembic\versions\<migration_file>.py

3. Apply migration
alembic upgrade head

4. Kiểm tra revision
alembic current

5. Kiểm tra schema
python -c "from sqlalchemy import create_engine,inspect; from src.backend.config import get_settings; e=create_engine(get_settings().database_url); i=inspect(e); print('CORE:',len(i.get_table_names(schema='core'))); print('APP:',len(i.get_table_names(schema='app'))); print('PUBLIC:',i.get_table_names(schema='public'))"

6. Kiểm tra Alembic
alembic check

7. Nếu còn diff constraint
alembic revision --autogenerate -m "sync constraints after schema merge"

8. Apply constraint migration
alembic upgrade head

9. Kiểm tra lại
alembic check

10. Tạo migration xóa bảng legacy
alembic revision -m "drop legacy merged tables"

11. Apply
alembic upgrade head

12. Kiểm tra public
python -c "from sqlalchemy import create_engine,inspect; from src.backend.config import get_settings; e=create_engine(get_settings().database_url); i=inspect(e); print(i.get_table_names(schema='public'))"

Kỳ vọng:
['alembic_version']

13. Kiểm tra lần cuối
alembic check

Kỳ vọng:
No new upgrade operations detected.

14. Chunk lại toàn bộ PostgreSQL -> Chroma
python -m src.backend.services.ingest_postgres --reset

Kỳ vọng:
34 tables
4276 rows
4592 chunks
[Chroma] upserted 4592/4592
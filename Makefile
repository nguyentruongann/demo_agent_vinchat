.PHONY: run test lint format typecheck check clean \
        db-up db-down db-shell db-tables migrate-new migrate-up migrate-down db-check db-reset

# ---- Database ----
db-up:              ## Khoi dong Postgres, cho toi khi healthy
	docker compose up -d --wait db

db-down:            ## Dung container, GIU nguyen du lieu
	docker compose stop db

db-shell:           ## Mo psql
	docker compose exec db psql -U vinpearl -d vinpearl

db-tables:          ## Dem bang trong lugc do public
	docker compose exec db psql -U vinpearl -d vinpearl -c "\dt"

migrate-new:        ## Sinh migration moi: make migrate-new m="them cot x"
	python -m alembic revision --autogenerate -m "$(m)"

migrate-up:         ## Ap moi migration con thieu
	python -m alembic upgrade head

migrate-down:       ## Lui lai mot buoc
	python -m alembic downgrade -1

db-check:           ## Bao loi neu model va DB lech nhau
	python -m alembic check

db-reset:           ## XOA SACH du lieu roi dung lai lugc do
	docker compose down -v db
	docker compose up -d --wait db
	python -m alembic upgrade head

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

check: lint format test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +

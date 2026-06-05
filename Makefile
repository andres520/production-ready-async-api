.PHONY: dev prod down logs test lint sample

dev:
	docker compose up --build

prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f api worker

test:
	python -m pytest

lint:
	python -m ruff check app tests

sample:
	curl -F "file=@samples/report.csv" http://localhost:8000/tasks

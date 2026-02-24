.PHONY: all logs run test down

run:
	cd src && uv run python -m bot.bot

test:
	cd src && uv run pytest ../tests/

down:
	docker compose down

up:
	docker compose up -d --build

logs:
	docker compose logs -f

all:
	make down
	make up
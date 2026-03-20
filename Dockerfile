FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-root --no-interaction

COPY fetch_messages.py .

CMD ["poetry", "run", "python", "fetch_messages.py"]

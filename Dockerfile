# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем Poetry
ENV POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache

RUN pip install --no-cache-dir poetry==${POETRY_VERSION}

# Копируем файлы конфигурации зависимостей
COPY pyproject.toml poetry.lock* ./

# Устанавливаем зависимости (без dev-зависимостей)
RUN poetry install --only main --no-root && rm -rf $POETRY_CACHE_DIR

# Копируем код приложения
COPY src/ .

# Создаем непривилегированного пользователя
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# Переключаемся на непривилегированного пользователя
USER botuser

# Открываем порт для webhook сервера
EXPOSE 8080

# Запускаем бота
CMD ["python", "main.py"]

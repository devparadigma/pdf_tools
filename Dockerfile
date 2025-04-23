# Используем официальный образ Python
FROM python:3.12-slim

# Установка системных зависимостей для OpenCV, Tesseract и Poppler
RUN apt-get update && apt-get install -y \
    ghostscript \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы приложения в контейнер
COPY app.py /app/
COPY templates /app/templates/
COPY static /app/static/
# Копирование зависимостей Python
COPY requirements.txt .

# Установка зависимостей Python
RUN pip install --no-cache-dir -r requirements.txt

# Указываем команду для запуска Flask-сервера
CMD ["python", "app.py"]

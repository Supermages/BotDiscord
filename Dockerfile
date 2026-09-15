FROM python:3.11-slim

# Evitar que Python escriba archivos .pyc y activar salida sin buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias básicas del sistema requeridas por Playwright, fuentes y compiladores
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium y todas sus dependencias de sistema en Linux
RUN playwright install --with-deps chromium

# Copiar el resto del proyecto
COPY . .

# Crear punto de volumen para persistencia de datos (base de datos y exportaciones)
VOLUME ["/app/data"]

# Comando de inicio del bot
CMD ["python", "bot.py"]

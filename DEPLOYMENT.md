# 🚀 Guía Universal de Despliegue - EriduBot

EriduBot está completamente preparado para desplegarse en cualquier entorno: contenedores Docker, servidores VPS (Ubuntu/Debian), máquinas locales o plataformas en la nube.

---

## ⚙️ Requisitos y Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto (puedes basarte en `.env.example`):

```env
# Obligatorio: Token de tu aplicación de Discord
DISCORD_TOKEN="tu_token_de_discord_aqui"

# Opcional: Rol administrativo para comandos protegidos
ROL_ADMIN="Bot Admin"

# Opcional: Puerto para healthcheck HTTP (si tu hosting en la nube lo requiere)
# PORT=8080

# Opcional: Activar recarga en caliente de código (recomendado solo en desarrollo)
# AUTO_RELOAD=false
```

---

## 🐳 Opción 1: Despliegue Universal con Docker (Recomendada)

La forma más limpia, portátil y aislada de ejecutar el bot. Funciona exactamente igual en tu ordenador, en un VPS (DigitalOcean, Hetzner, Oracle, Linode, AWS) o en un servidor casero.

### Iniciar el bot:
```bash
docker compose up -d --build
```

### Características del contenedor:
- **Persistencia garantizada**: El volumen `./data:/app/data` asegura que la base de datos SQLite (`eridubot.sqlite`) y las exportaciones de chat se guarden en tu disco y nunca se pierdan al reiniciar o actualizar la imagen.
- **Playwright Chromium preinstalado**: El `Dockerfile` ya incluye todas las dependencias del sistema operativo Linux, compiladores y fuentes necesarias para renderizar emojis y texto nítido.
- **Reinicio automático**: Configurado con `restart: unless-stopped`.

### Comandos de control con Docker:
```bash
# Ver los registros del bot en tiempo real
docker compose logs -f

# Reiniciar el bot
docker compose restart

# Detener el bot
docker compose down

# Actualizar con nuevo código
git pull
docker compose up -d --build
```

---

## 🐍 Opción 2: Ejecución Directa con Python (Sin Docker)

Si prefieres ejecutar el bot directamente en tu sistema operativo:

### 1. Requisitos:
- Python 3.11 o superior.
- Node.js / Playwright.

### 2. Instalación:
```bash
# Crear entorno virtual (opcional pero recomendado)
python -m venv venv

# Activar entorno virtual
# En Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# En Linux/macOS:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Instalar Chromium de Playwright
playwright install chromium
```

### 3. Iniciar:
```bash
python bot.py
```

---

## ☁️ Opción 3: Plataformas PaaS en la Nube (Render, Railway, Koyeb, etc.)

El bot está equipado con un servidor HTTP ligero interno que se activa automáticamente cuando la plataforma asigna una variable de entorno `PORT`:

1. **Configuración del servicio**:
   - Tipo de servicio: **Web Service** (Docker).
   - Variables de entorno:
     - `DISCORD_TOKEN`: Tu token.
     - `PORT`: El puerto de tu proveedor (o `8080`).
     - `ROL_ADMIN`: `Bot Admin`.
2. **Healthcheck**:
   - Endpoint de salud disponible en `GET /health` y `GET /`.
   - Retorna `{ "status": "online", "bot": "EriduBot#...", "cogs": [...] }` con código 200 OK.

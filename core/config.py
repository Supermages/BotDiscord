import os
import logging
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Config:
    # --- Discord Credentials & Permissions ---
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    if not DISCORD_TOKEN:
        raise ValueError(
            "❌ ERROR CRÍTICO: No se ha configurado 'DISCORD_TOKEN' en el entorno o archivo .env. "
            "Por favor, revisa tu archivo .env o las variables de tu servidor."
        )

    ROL_ADMIN = os.getenv("ROL_ADMIN", "Bot Admin")
    TUPPER_WEBHOOK_ID = os.getenv("TUPPER_WEBHOOK_ID", "").strip()

    # --- Persistencia y Rutas en la Nube ---
    DATABASE_PATH = os.getenv(
        "DATABASE_PATH", 
        os.path.join(BASE_DIR, "data", "eridubot.sqlite")
    )
    EXPORT_FOLDER = os.getenv(
        "EXPORT_FOLDER", 
        os.path.join(BASE_DIR, "data", "exportaciones")
    )

    # --- Límites de Mensajes y Segmentación ---
    try:
        MAX_MENSAJES_TOTAL = int(os.getenv("MAX_MENSAJES_TOTAL", 50))
        MENSAJES_POR_IMAGEN = int(os.getenv("MENSAJES_POR_IMAGEN", 10))
    except ValueError:
        logging.warning("⚠️ Error parseando límites numéricos en .env. Usando valores por defecto (50 total, 10 por imagen).")
        MAX_MENSAJES_TOTAL = 50
        MENSAJES_POR_IMAGEN = 10

    try:
        SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT", 500))
    except ValueError:
        SEARCH_LIMIT = 500

    @classmethod
    def asegurar_directorios(cls):
        """Crea las carpetas necesarias si no existen."""
        os.makedirs(cls.EXPORT_FOLDER, exist_ok=True)
        os.makedirs(os.path.dirname(cls.DATABASE_PATH), exist_ok=True)

# Asegurar directorios al importar
Config.asegurar_directorios()

import aiosqlite
from contextlib import asynccontextmanager
from core.config import Config

DB_FILE = Config.DATABASE_PATH

# --- Caché en memoria para evitar consultas N+1 en bucles de escaneo ---
# Se mutan in situ (nunca se reasignan) para que todos los repos y la fachada
# compartan los mismos diccionarios.
_cache_personajes = {}
_cache_webhooks = {}
_cache_guild_modo = {}

def get_db_path():
    return DB_FILE

def set_db_path(path):
    global DB_FILE
    DB_FILE = path

@asynccontextmanager
async def conectar():
    """
    Abre una conexión a la base de datos con los PRAGMAs de integridad y
    concurrencia aplicados. Debe usarse en CADA conexión, porque en SQLite
    las PRAGMAs (salvo journal_mode) son por conexión:

    - foreign_keys=ON: sin esto, las FOREIGN KEY y los ON DELETE CASCADE
      declarados en las tablas NO se aplican y el inventario se corrompe
      silenciosamente con filas huérfanas.
    - busy_timeout (10 s): espera en vez de fallar de inmediato con
      'database is locked' ante escrituras concurrentes.
    - synchronous=NORMAL: compromiso latencia/durabilidad recomendado en WAL.
    - timeout=10 en connect(): mismo límite a nivel de driver sqlite3.
    """
    async with aiosqlite.connect(DB_FILE, timeout=10) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute("PRAGMA busy_timeout=10000;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        yield db

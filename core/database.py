import aiosqlite
import os
from core.config import Config

DB_FILE = Config.DATABASE_PATH

# --- Caché en memoria para evitar consultas N+1 en bucles de escaneo ---
_cache_personajes = {}
_cache_webhooks = {}
_cache_guild_modo = {}

def get_db_path():
    return DB_FILE

def set_db_path(path):
    global DB_FILE
    DB_FILE = path

async def inicializar_base():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Personaje_Tabla (
                tupper_tag TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                lado TEXT NOT NULL,
                avatar_url TEXT,
                color TEXT DEFAULT '#FFFFFF',
                color_texto TEXT DEFAULT '#000000'
            )
        ''')
        # Índice para acelerar búsquedas insensibles a mayúsculas por nombre
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_personaje_nombre_lower 
            ON Personaje_Tabla(LOWER(nombre))
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Tupperbox_Webhooks (
                guild_id TEXT PRIMARY KEY,
                webhook_id TEXT NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Guild_Config (
                guild_id TEXT PRIMARY KEY,
                modo_captura TEXT DEFAULT 'TUPPER'
            )
        ''')
        await db.commit()

async def obtener_personaje(tupper_tag):
    if tupper_tag in _cache_personajes:
        return _cache_personajes[tupper_tag]

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            'SELECT nombre, lado, avatar_url, color, color_texto FROM Personaje_Tabla WHERE tupper_tag = ?', 
            (tupper_tag,)
        ) as cursor:
            res = await cursor.fetchone()
            if res:
                _cache_personajes[tupper_tag] = res
            return res

async def guardar_personaje(tupper_tag, nombre, lado, avatar_url, color="#FFFFFF", color_texto="#000000"):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR REPLACE INTO Personaje_Tabla (tupper_tag, nombre, lado, avatar_url, color, color_texto)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (tupper_tag, nombre, lado, avatar_url, color, color_texto))
        await db.commit()
    # Actualizar caché
    _cache_personajes[tupper_tag] = (nombre, lado, avatar_url, color, color_texto)

async def actualizar_personaje(tupper_tag, lado=None, color=None, color_texto=None):
    async with aiosqlite.connect(DB_FILE) as db:
        if lado:
            await db.execute('UPDATE Personaje_Tabla SET lado = ? WHERE tupper_tag = ?', (lado, tupper_tag))
        if color:
            await db.execute('UPDATE Personaje_Tabla SET color = ? WHERE tupper_tag = ?', (color, tupper_tag))
        if color_texto:
            await db.execute('UPDATE Personaje_Tabla SET color_texto = ? WHERE tupper_tag = ?', (color_texto, tupper_tag))
        await db.commit()
    
    # Invalidar caché para forzar recarga en la siguiente lectura
    _cache_personajes.pop(tupper_tag, None)

async def guardar_tupperbox_webhook(guild_id, webhook_id):
    g_id = str(guild_id)
    w_id = str(webhook_id)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR REPLACE INTO Tupperbox_Webhooks (guild_id, webhook_id)
            VALUES (?, ?)
        ''', (g_id, w_id))
        await db.commit()
    _cache_webhooks[g_id] = w_id

async def obtener_tupperbox_webhook(guild_id):
    g_id = str(guild_id)
    if g_id in _cache_webhooks:
        return (_cache_webhooks[g_id],)

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT webhook_id FROM Tupperbox_Webhooks WHERE guild_id = ?', (g_id,)) as cursor:
            resultado = await cursor.fetchone()
            if resultado:
                _cache_webhooks[g_id] = resultado[0]
            return resultado

async def buscar_personaje_por_nombre_db(nombre):
    """Búsqueda directa indexada en SQL por nombre insensible a mayúsculas."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            'SELECT tupper_tag, nombre, lado, avatar_url, color, color_texto FROM Personaje_Tabla WHERE LOWER(nombre) = LOWER(?) LIMIT 1', 
            (nombre,)
        ) as cursor:
            return await cursor.fetchone()

async def set_modo_captura(guild_id, modo):
    """ modo puede ser 'TUPPER' o 'TODO' """
    g_id = str(guild_id)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR REPLACE INTO Guild_Config (guild_id, modo_captura)
            VALUES (?, ?)
        ''', (g_id, modo))
        await db.commit()
    _cache_guild_modo[g_id] = modo

async def get_modo_captura(guild_id):
    g_id = str(guild_id)
    if g_id in _cache_guild_modo:
        return _cache_guild_modo[g_id]

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT modo_captura FROM Guild_Config WHERE guild_id = ?', (g_id,)) as cursor:
            resultado = await cursor.fetchone()
            modo = resultado[0] if resultado else 'TUPPER'
            _cache_guild_modo[g_id] = modo
            return modo
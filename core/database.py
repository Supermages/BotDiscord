import aiosqlite
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, 'data', 'eridubot.sqlite')

async def inicializar_base():
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
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT nombre, lado, avatar_url, color, color_texto FROM Personaje_Tabla WHERE tupper_tag = ?', (tupper_tag,)) as cursor:
            return await cursor.fetchone()

async def guardar_personaje(tupper_tag, nombre, lado, avatar_url, color="#FFFFFF", color_texto="#000000"):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR REPLACE INTO Personaje_Tabla (tupper_tag, nombre, lado, avatar_url, color, color_texto)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (tupper_tag, nombre, lado, avatar_url, color, color_texto))
        await db.commit()

async def actualizar_personaje(tupper_tag, lado=None, color=None, color_texto=None):
    async with aiosqlite.connect(DB_FILE) as db:
        if lado:
            await db.execute('UPDATE Personaje_Tabla SET lado = ? WHERE tupper_tag = ?', (lado, tupper_tag))
        if color:
            await db.execute('UPDATE Personaje_Tabla SET color = ? WHERE tupper_tag = ?', (color, tupper_tag))
        if color_texto:
            await db.execute('UPDATE Personaje_Tabla SET color_texto = ? WHERE tupper_tag = ?', (color_texto, tupper_tag))
        await db.commit()

async def guardar_tupperbox_webhook(guild_id, webhook_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Tupperbox_Webhooks (
                guild_id TEXT PRIMARY KEY,
                webhook_id TEXT NOT NULL
            )
        ''')
        await db.execute('''
            INSERT OR REPLACE INTO Tupperbox_Webhooks (guild_id, webhook_id)
            VALUES (?, ?)
        ''', (str(guild_id), str(webhook_id)))
        await db.commit()

async def obtener_tupperbox_webhook(guild_id):
    async with aiosqlite.connect(DB_FILE) as db:
        # Seleccionamos solo el ID
        cursor = await db.execute('SELECT webhook_id FROM Tupperbox_Webhooks WHERE guild_id = ?', (str(guild_id),))
        resultado = await cursor.fetchone()
        await cursor.close()
        return resultado # Devuelve una tupla (id,) o None
        
async def buscar_personaje_por_nombre_db(nombre):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT * FROM Personaje_Tabla') as cursor:
            # Iteramos asincronamente (no es lo más eficiente en SQL puro, pero sirve para tu lógica actual)
            async for row in cursor:
                # row[1] es la columna 'nombre'
                if row[1].lower() == nombre.lower():
                    return row
    return None

async def set_modo_captura(guild_id, modo):
    """ modo puede ser 'TUPPER' o 'TODO' """
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR REPLACE INTO Guild_Config (guild_id, modo_captura)
            VALUES (?, ?)
        ''', (str(guild_id), modo))
        await db.commit()

async def get_modo_captura(guild_id):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT modo_captura FROM Guild_Config WHERE guild_id = ?', (str(guild_id),)) as cursor:
            resultado = await cursor.fetchone()
            return resultado[0] if resultado else 'TUPPER'
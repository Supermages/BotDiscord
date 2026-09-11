import aiosqlite
import os
import logging
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
                color_texto TEXT DEFAULT '#000000',
                owner_id TEXT DEFAULT NULL
            )
        ''')
        # Migración segura: añadir columna owner_id si la tabla existía previamente
        try:
            await db.execute('ALTER TABLE Personaje_Tabla ADD COLUMN owner_id TEXT DEFAULT NULL;')
            await db.commit()
        except Exception:
            pass

        # Índice para acelerar búsquedas insensibles a mayúsculas por nombre
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_personaje_nombre_lower 
            ON Personaje_Tabla(LOWER(nombre))
        ''')
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_personaje_owner 
            ON Personaje_Tabla(owner_id)
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

        # --- TABLAS DE INVENTARIO Y CRAFTEO (ESTILO MYTHOS) ---
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Items_Catalogo (
                item_id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                emoji TEXT DEFAULT '📦',
                categoria TEXT DEFAULT 'Material',
                descripcion TEXT DEFAULT '',
                es_usable INTEGER DEFAULT 0,
                mensaje_uso TEXT DEFAULT ''
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Inventarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                personaje_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                cantidad INTEGER NOT NULL DEFAULT 1,
                UNIQUE(personaje_id, item_id),
                FOREIGN KEY (personaje_id) REFERENCES Personaje_Tabla(tupper_tag) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES Items_Catalogo(item_id) ON DELETE CASCADE
            )
        ''')
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_inventario_personaje 
            ON Inventarios(personaje_id)
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Recetas_Crafteo (
                receta_id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                resultado_item_id TEXT NOT NULL,
                resultado_cantidad INTEGER DEFAULT 1,
                descripcion TEXT DEFAULT '',
                FOREIGN KEY (resultado_item_id) REFERENCES Items_Catalogo(item_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Recetas_Ingredientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receta_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                cantidad INTEGER NOT NULL DEFAULT 1,
                UNIQUE(receta_id, item_id),
                FOREIGN KEY (receta_id) REFERENCES Recetas_Crafteo(receta_id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES Items_Catalogo(item_id)
            )
        ''')
        await db.commit()

# ==========================================
# 1. GESTIÓN DE PERSONAJES Y PROPIEDAD
# ==========================================

async def obtener_personaje(tupper_tag):
    if tupper_tag in _cache_personajes:
        return _cache_personajes[tupper_tag]

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            'SELECT nombre, lado, avatar_url, color, color_texto, owner_id FROM Personaje_Tabla WHERE tupper_tag = ?', 
            (tupper_tag,)
        ) as cursor:
            res = await cursor.fetchone()
            if res:
                _cache_personajes[tupper_tag] = res
            return res

async def guardar_personaje(tupper_tag, nombre, lado, avatar_url, color="#FFFFFF", color_texto="#000000", owner_id=None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO Personaje_Tabla (tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tupper_tag) DO UPDATE SET
                nombre=excluded.nombre,
                lado=excluded.lado,
                avatar_url=excluded.avatar_url,
                color=excluded.color,
                color_texto=excluded.color_texto,
                owner_id=COALESCE(Personaje_Tabla.owner_id, excluded.owner_id)
        ''', (tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id))
        await db.commit()
    _cache_personajes[tupper_tag] = (nombre, lado, avatar_url, color, color_texto, owner_id)

async def actualizar_personaje(tupper_tag, lado=None, color=None, color_texto=None, owner_id=None):
    async with aiosqlite.connect(DB_FILE) as db:
        if lado:
            await db.execute('UPDATE Personaje_Tabla SET lado = ? WHERE tupper_tag = ?', (lado, tupper_tag))
        if color:
            await db.execute('UPDATE Personaje_Tabla SET color = ? WHERE tupper_tag = ?', (color, tupper_tag))
        if color_texto:
            await db.execute('UPDATE Personaje_Tabla SET color_texto = ? WHERE tupper_tag = ?', (color_texto, tupper_tag))
        if owner_id is not None:
            await db.execute('UPDATE Personaje_Tabla SET owner_id = ? WHERE tupper_tag = ?', (owner_id, tupper_tag))
        await db.commit()
    _cache_personajes.pop(tupper_tag, None)

async def vincular_owner_personaje(tupper_tag: str, owner_id: str):
    """Vincula un personaje a un usuario de Discord."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE Personaje_Tabla SET owner_id = ? WHERE tupper_tag = ?', (str(owner_id), tupper_tag))
        await db.commit()
    _cache_personajes.pop(tupper_tag, None)

async def obtener_personajes_por_owner(owner_id: str) -> list[dict]:
    """Retorna todos los personajes vinculados a un usuario de Discord."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id FROM Personaje_Tabla WHERE owner_id = ?', 
            (str(owner_id),)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def buscar_personaje_por_nombre_db(nombre: str) -> tuple | None:
    """Búsqueda directa indexada en SQL por nombre o tupper_tag insensible a mayúsculas."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            '''SELECT tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id 
               FROM Personaje_Tabla 
               WHERE LOWER(nombre) = LOWER(?) OR LOWER(tupper_tag) = LOWER(?) 
               LIMIT 1''', 
            (nombre, nombre)
        ) as cursor:
            return await cursor.fetchone()

async def listar_todos_personajes() -> list[tuple]:
    """Lista todos los personajes registrados (útil para autocompletado)."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT tupper_tag, nombre, owner_id FROM Personaje_Tabla ORDER BY nombre ASC') as cursor:
            return await cursor.fetchall()

# ==========================================
# 2. CATÁLOGO DE ÍTEMS
# ==========================================

async def crear_o_actualizar_item(item_id: str, nombre: str, emoji: str = "📦", categoria: str = "Material", descripcion: str = "", es_usable: int = 0, mensaje_uso: str = ""):
    iid = item_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO Items_Catalogo (item_id, nombre, emoji, categoria, descripcion, es_usable, mensaje_uso)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                nombre=excluded.nombre,
                emoji=excluded.emoji,
                categoria=excluded.categoria,
                descripcion=excluded.descripcion,
                es_usable=excluded.es_usable,
                mensaje_uso=excluded.mensaje_uso
        ''', (iid, nombre, emoji, categoria, descripcion, es_usable, mensaje_uso))
        await db.commit()

async def obtener_item(item_id: str) -> dict | None:
    iid = item_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM Items_Catalogo WHERE item_id = ? OR LOWER(nombre) = LOWER(?)', 
            (iid, item_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def listar_items_catalogo(categoria: str = None) -> list[dict]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        if categoria:
            query = 'SELECT * FROM Items_Catalogo WHERE LOWER(categoria) = LOWER(?) ORDER BY nombre ASC'
            params = (categoria,)
        else:
            query = 'SELECT * FROM Items_Catalogo ORDER BY categoria ASC, nombre ASC'
            params = ()
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def eliminar_item_catalogo(item_id: str) -> bool:
    iid = item_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('DELETE FROM Items_Catalogo WHERE item_id = ?', (iid,))
        await db.commit()
        return cursor.rowcount > 0

# ==========================================
# 3. GESTIÓN DE INVENTARIOS
# ==========================================

async def obtener_inventario_personaje(tupper_tag: str) -> list[dict]:
    """Retorna los ítems en el inventario de un personaje combinados con sus metadatos del catálogo."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT 
                i.item_id, 
                i.cantidad, 
                COALESCE(c.nombre, i.item_id) AS nombre,
                COALESCE(c.emoji, '📦') AS emoji,
                COALESCE(c.categoria, 'Otros') AS categoria,
                COALESCE(c.descripcion, '') AS descripcion,
                COALESCE(c.es_usable, 0) AS es_usable,
                COALESCE(c.mensaje_uso, '') AS mensaje_uso
            FROM Inventarios i
            LEFT JOIN Items_Catalogo c ON i.item_id = c.item_id
            WHERE i.personaje_id = ? AND i.cantidad > 0
            ORDER BY c.categoria ASC, c.nombre ASC
        ''', (tupper_tag,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def obtener_cantidad_item(tupper_tag: str, item_id: str) -> int:
    iid = item_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            'SELECT cantidad FROM Inventarios WHERE personaje_id = ? AND item_id = ?', 
            (tupper_tag, iid)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def modificar_cantidad_inventario(tupper_tag: str, item_id: str, delta: int) -> int:
    """
    Suma o resta delta a la cantidad de un ítem en el inventario.
    Si la nueva cantidad es <= 0, elimina el registro. Retorna la nueva cantidad final.
    """
    iid = item_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            'SELECT cantidad FROM Inventarios WHERE personaje_id = ? AND item_id = ?', 
            (tupper_tag, iid)
        ) as cursor:
            row = await cursor.fetchone()
            actual = row[0] if row else 0

        nueva_cantidad = actual + delta

        if nueva_cantidad > 0:
            await db.execute('''
                INSERT INTO Inventarios (personaje_id, item_id, cantidad)
                VALUES (?, ?, ?)
                ON CONFLICT(personaje_id, item_id) DO UPDATE SET cantidad = excluded.cantidad
            ''', (tupper_tag, iid, nueva_cantidad))
        else:
            await db.execute(
                'DELETE FROM Inventarios WHERE personaje_id = ? AND item_id = ?', 
                (tupper_tag, iid)
            )
            nueva_cantidad = 0

        await db.commit()
        return nueva_cantidad

async def transferir_item_atomico(origen_tag: str, destino_tag: str, item_id: str, cantidad: int) -> tuple[bool, str]:
    """
    Transfiere una cantidad de un ítem de un personaje a otro en una transacción atómica protegida.
    """
    if cantidad <= 0:
        return False, "La cantidad a transferir debe ser mayor a 0."

    if origen_tag.lower() == destino_tag.lower():
        return False, "No puedes transferir ítems al mismo personaje."

    iid = item_id.strip().lower()

    async with aiosqlite.connect(DB_FILE) as db:
        # 1. Comprobar existencia del personaje destino
        async with db.execute('SELECT nombre FROM Personaje_Tabla WHERE tupper_tag = ?', (destino_tag,)) as cur:
            if not await cur.fetchone():
                return False, f"El personaje destino '{destino_tag}' no existe en el sistema."

        # 2. Comprobar saldo en origen
        async with db.execute(
            'SELECT cantidad FROM Inventarios WHERE personaje_id = ? AND item_id = ?', 
            (origen_tag, iid)
        ) as cur:
            row = await cur.fetchone()
            disponible = row[0] if row else 0

        if disponible < cantidad:
            return False, f"Stock insuficiente. El personaje solo tiene x{disponible} de este ítem."

        # 3. Transacción atómica de transferencia
        nuevo_origen = disponible - cantidad
        if nuevo_origen > 0:
            await db.execute(
                'UPDATE Inventarios SET cantidad = ? WHERE personaje_id = ? AND item_id = ?', 
                (nuevo_origen, origen_tag, iid)
            )
        else:
            await db.execute(
                'DELETE FROM Inventarios WHERE personaje_id = ? AND item_id = ?', 
                (origen_tag, iid)
            )

        # Sumar a destino
        await db.execute('''
            INSERT INTO Inventarios (personaje_id, item_id, cantidad)
            VALUES (?, ?, ?)
            ON CONFLICT(personaje_id, item_id) DO UPDATE SET cantidad = cantidad + excluded.cantidad
        ''', (destino_tag, iid, cantidad))

        await db.commit()
        return True, "Transferencia realizada con éxito."

# ==========================================
# 4. GESTIÓN DE RECETAS DE CRAFTEO
# ==========================================

async def crear_receta(receta_id: str, nombre: str, resultado_item_id: str, resultado_cantidad: int, ingredientes: dict[str, int], descripcion: str = ""):
    rid = receta_id.strip().lower()
    res_id = resultado_item_id.strip().lower()

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO Recetas_Crafteo (receta_id, nombre, resultado_item_id, resultado_cantidad, descripcion)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(receta_id) DO UPDATE SET
                nombre=excluded.nombre,
                resultado_item_id=excluded.resultado_item_id,
                resultado_cantidad=excluded.resultado_cantidad,
                descripcion=excluded.descripcion
        ''', (rid, nombre, res_id, resultado_cantidad, descripcion))

        # Reemplazar ingredientes
        await db.execute('DELETE FROM Recetas_Ingredientes WHERE receta_id = ?', (rid,))
        for ing_id, ing_cant in ingredientes.items():
            if ing_cant > 0:
                await db.execute('''
                    INSERT INTO Recetas_Ingredientes (receta_id, item_id, cantidad)
                    VALUES (?, ?, ?)
                ''', (rid, ing_id.strip().lower(), ing_cant))

        await db.commit()

async def obtener_receta(receta_id: str) -> dict | None:
    rid = receta_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT 
                r.*, 
                c.nombre AS resultado_nombre, 
                c.emoji AS resultado_emoji
            FROM Recetas_Crafteo r
            LEFT JOIN Items_Catalogo c ON r.resultado_item_id = c.item_id
            WHERE r.receta_id = ? OR LOWER(r.nombre) = LOWER(?)
        ''', (rid, receta_id)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            receta = dict(row)

        # Cargar ingredientes
        async with db.execute('''
            SELECT 
                ri.item_id, 
                ri.cantidad, 
                COALESCE(c.nombre, ri.item_id) AS nombre,
                COALESCE(c.emoji, '📦') AS emoji
            FROM Recetas_Ingredientes ri
            LEFT JOIN Items_Catalogo c ON ri.item_id = c.item_id
            WHERE ri.receta_id = ?
        ''', (receta['receta_id'],)) as cur:
            ing_rows = await cur.fetchall()
            receta['ingredientes'] = [dict(r) for r in ing_rows]

        return receta

async def listar_recetas() -> list[dict]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT 
                r.*, 
                c.nombre AS resultado_nombre, 
                c.emoji AS resultado_emoji
            FROM Recetas_Crafteo r
            LEFT JOIN Items_Catalogo c ON r.resultado_item_id = c.item_id
            ORDER BY r.nombre ASC
        ''') as cur:
            recetas = [dict(r) for r in await cur.fetchall()]

        for r in recetas:
            async with db.execute('''
                SELECT 
                    ri.item_id, 
                    ri.cantidad, 
                    COALESCE(c.nombre, ri.item_id) AS nombre,
                    COALESCE(c.emoji, '📦') AS emoji
                FROM Recetas_Ingredientes ri
                LEFT JOIN Items_Catalogo c ON ri.item_id = c.item_id
                WHERE ri.receta_id = ?
            ''', (r['receta_id'],)) as cur:
                r['ingredientes'] = [dict(ing) for ing in await cur.fetchall()]

        return recetas

async def eliminar_receta(receta_id: str) -> bool:
    rid = receta_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('DELETE FROM Recetas_Crafteo WHERE receta_id = ?', (rid,))
        await db.execute('DELETE FROM Recetas_Ingredientes WHERE receta_id = ?', (rid,))
        await db.commit()
        return cursor.rowcount > 0

# ==========================================
# 5. CONFIGURACIÓN DEL SERVIDOR Y WEBHOOKS
# ==========================================

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

async def set_modo_captura(guild_id, modo):
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
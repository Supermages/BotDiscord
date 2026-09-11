import aiosqlite
import os
import logging
import unicodedata
import re
from core.config import Config

DB_FILE = Config.DATABASE_PATH

# --- Caché en memoria para evitar consultas N+1 en bucles de escaneo ---
_cache_personajes = {}
_cache_webhooks = {}
_cache_guild_modo = {}

def normalizar_texto(texto: str) -> str:
    """
    Normaliza texto eliminando diacríticos, símbolos decorativos y fuentes especiales
    para permitir búsquedas insensibles a caracteres Unicode fancy.
    Ej: '★ 𝕬𝖗𝖙𝖚𝖗𝖔 ★' -> 'arturo', '【Elena】' -> 'elena', 'René' -> 'rene'
    """
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(texto))
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    lower = sin_tildes.lower()
    alfanumerico = re.sub(r'[^a-z0-9\s]', '', lower)
    return " ".join(alfanumerico.split())

def limpiar_termino_busqueda(texto: str) -> str:
    """
    Limpia prefijos de autocompletado (como emojis 🛡️, 📦, ⭐) y sufijos
    de información como (@dueño), (ID: ...), (Sin vincular), (Activo), etc.
    Esto permite que si Discord envía la etiqueta visible del Choice en vez del value,
    la búsqueda reconozca el nombre real del personaje.
    """
    if not texto:
        return ""
    # Quitar emojis y espacios iniciales
    limpio = re.sub(r'^[🛡️📦⭐✨\s]+', '', str(texto)).strip()
    # Quitar etiquetas finales entre paréntesis (ej: ' (@Sayaka...)', ' (ID: 12345)', ' (Sin vincular)')
    limpio = re.sub(r'\s*\((?:@[^)]+|ID:\s*[^)]+|Sin vincular|Activo|Reserva|En Reserva)\)\s*$', '', limpio).strip()
    return limpio


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

        # Migración: añadir columna creator_id para la reserva personal del usuario
        try:
            await db.execute('ALTER TABLE Personaje_Tabla ADD COLUMN creator_id TEXT DEFAULT NULL;')
            await db.commit()
        except Exception:
            pass

        # Índices para acelerar búsquedas
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_personaje_nombre_lower 
            ON Personaje_Tabla(LOWER(nombre))
        ''')
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_personaje_owner 
            ON Personaje_Tabla(owner_id)
        ''')
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_personaje_creator 
            ON Personaje_Tabla(creator_id)
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
                modo_captura TEXT DEFAULT 'TUPPER',
                limite_personajes INTEGER DEFAULT 3
            )
        ''')
        try:
            await db.execute('ALTER TABLE Guild_Config ADD COLUMN limite_personajes INTEGER DEFAULT 3;')
            await db.commit()
        except Exception:
            pass

        # --- TABLAS DE INVENTARIO Y CRAFTEO (ESTILO MYTHOS) ---
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Scripts_Catalogo (
                script_id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                codigo TEXT NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS Items_Catalogo (
                item_id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                emoji TEXT DEFAULT '📦',
                categoria TEXT DEFAULT 'Material',
                descripcion TEXT DEFAULT '',
                es_usable INTEGER DEFAULT 0,
                mensaje_uso TEXT DEFAULT '',
                script_uso TEXT DEFAULT '',
                script_id TEXT DEFAULT NULL,
                FOREIGN KEY (script_id) REFERENCES Scripts_Catalogo(script_id) ON DELETE SET NULL
            )
        ''')
        try:
            await db.execute('ALTER TABLE Items_Catalogo ADD COLUMN script_uso TEXT DEFAULT "";')
            await db.commit()
        except Exception:
            pass
        try:
            await db.execute('ALTER TABLE Items_Catalogo ADD COLUMN script_id TEXT DEFAULT NULL;')
            await db.commit()
        except Exception:
            pass
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
            'SELECT nombre, lado, avatar_url, color, color_texto, owner_id, creator_id FROM Personaje_Tabla WHERE tupper_tag = ?', 
            (tupper_tag,)
        ) as cursor:
            res = await cursor.fetchone()
            if res:
                _cache_personajes[tupper_tag] = res
            return res

async def guardar_personaje(tupper_tag, nombre, lado, avatar_url, color="#FFFFFF", color_texto="#000000", owner_id=None, creator_id=None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO Personaje_Tabla (tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tupper_tag) DO UPDATE SET
                nombre=excluded.nombre,
                lado=excluded.lado,
                avatar_url=excluded.avatar_url,
                color=excluded.color,
                color_texto=excluded.color_texto,
                owner_id=COALESCE(Personaje_Tabla.owner_id, excluded.owner_id),
                creator_id=COALESCE(Personaje_Tabla.creator_id, excluded.creator_id)
        ''', (tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id))
        await db.commit()
    _cache_personajes[tupper_tag] = (nombre, lado, avatar_url, color, color_texto, owner_id, creator_id)

async def actualizar_personaje(tupper_tag, lado=None, color=None, color_texto=None, owner_id=None, creator_id=None):
    async with aiosqlite.connect(DB_FILE) as db:
        if lado:
            await db.execute('UPDATE Personaje_Tabla SET lado = ? WHERE tupper_tag = ?', (lado, tupper_tag))
        if color:
            await db.execute('UPDATE Personaje_Tabla SET color = ? WHERE tupper_tag = ?', (color, tupper_tag))
        if color_texto:
            await db.execute('UPDATE Personaje_Tabla SET color_texto = ? WHERE tupper_tag = ?', (color_texto, tupper_tag))
        if owner_id is not None:
            await db.execute('UPDATE Personaje_Tabla SET owner_id = ? WHERE tupper_tag = ?', (owner_id, tupper_tag))
        if creator_id is not None:
            await db.execute('UPDATE Personaje_Tabla SET creator_id = ? WHERE tupper_tag = ?', (creator_id, tupper_tag))
        await db.commit()
    _cache_personajes.pop(tupper_tag, None)

async def vincular_owner_personaje(tupper_tag: str, owner_id: str):
    """Vincula forzosamente un personaje a un usuario de Discord como activo."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE Personaje_Tabla SET owner_id = ?, creator_id = COALESCE(creator_id, ?) WHERE tupper_tag = ?', (str(owner_id), str(owner_id), tupper_tag))
        await db.commit()
    _cache_personajes.pop(tupper_tag, None)

async def obtener_limite_personajes(guild_id: str = None) -> int:
    """Obtiene el límite de personajes activos configurado para el servidor (por defecto 3)."""
    if not guild_id:
        return 3
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT limite_personajes FROM Guild_Config WHERE guild_id = ?', (str(guild_id),)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] is not None:
                return int(row[0])
    return 3

async def establecer_limite_personajes(guild_id: str, limite: int):
    """Establece el límite de personajes activos por usuario para el servidor."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO Guild_Config (guild_id, limite_personajes)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET limite_personajes = excluded.limite_personajes
        ''', (str(guild_id), limite))
        await db.commit()

async def obtener_personajes_por_owner(owner_id: str) -> list[dict]:
    """Retorna los personajes que el usuario tiene actualmente vinculados en activo."""
    return await obtener_personajes_activos(owner_id)

async def obtener_personajes_activos(user_id: str) -> list[dict]:
    """Retorna los personajes que el usuario tiene actualmente activos (owner_id = user_id)."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id 
               FROM Personaje_Tabla 
               WHERE owner_id = ? 
               ORDER BY nombre ASC''', 
            (str(user_id),)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def obtener_personajes_vinculados_con_owner() -> list[dict]:
    """Retorna todos los personajes activos/vinculados a algún usuario en el sistema."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id 
               FROM Personaje_Tabla 
               WHERE owner_id IS NOT NULL AND owner_id != '' 
               ORDER BY nombre ASC'''
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def obtener_personajes_reserva(user_id: str) -> list[dict]:
    """Retorna los personajes en reserva del usuario (creator_id = user_id y sin activar)."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id 
               FROM Personaje_Tabla 
               WHERE (creator_id = ? OR (creator_id IS NULL AND owner_id IS NULL)) AND (owner_id IS NULL OR owner_id = '')
               ORDER BY nombre ASC''', 
            (str(user_id),)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def activar_personaje(user_id: str, tupper_tag: str, limite: int = 3) -> tuple[bool, str, dict | None]:
    """
    Activa un personaje de la reserva asignándole owner_id = user_id.
    Comprueba que el usuario no supere el límite permitido.
    """
    owner_str = str(user_id)
    async with aiosqlite.connect(DB_FILE) as db:
        # 1. Comprobar cuántos personajes activos tiene el usuario
        async with db.execute('SELECT COUNT(*) FROM Personaje_Tabla WHERE owner_id = ?', (owner_str,)) as cursor:
            row = await cursor.fetchone()
            activos_count = row[0] if row else 0

        if activos_count >= limite:
            return False, f"Has alcanzado el límite máximo de personajes activos ({activos_count}/{limite}). Desactiva uno primero con `/pj desvincular`.", None

        # 2. Comprobar el personaje
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM Personaje_Tabla WHERE tupper_tag = ?', (tupper_tag,)) as cursor:
            pj = await cursor.fetchone()

        if not pj:
            return False, f"El personaje '{tupper_tag}' no existe en la base de datos.", None

        pj_dict = dict(pj)
        current_owner = pj_dict.get("owner_id")
        current_creator = pj_dict.get("creator_id")

        if current_owner and str(current_owner) == owner_str:
            return False, f"**{pj_dict['nombre']}** ya está activo en tu cuenta.", pj_dict

        if current_owner and str(current_owner) != owner_str:
            return False, f"El personaje ya está activo a nombre de otro usuario (<@{current_owner}>).", None

        if current_creator and str(current_creator) != owner_str:
            return False, f"Este personaje pertenece a la reserva de otro usuario.", None

        # 3. Activar
        await db.execute(
            'UPDATE Personaje_Tabla SET owner_id = ?, creator_id = COALESCE(creator_id, ?) WHERE tupper_tag = ?', 
            (owner_str, owner_str, tupper_tag)
        )
        await db.commit()
        _cache_personajes.pop(tupper_tag, None)
        pj_dict["owner_id"] = owner_str
        return True, f"¡**{pj_dict['nombre']}** activado con éxito! ({activos_count + 1}/{limite} activos)", pj_dict

async def desactivar_personaje(user_id: str, tupper_tag: str) -> tuple[bool, str]:
    """
    Desactiva un personaje pasándolo a reserva (owner_id = NULL).
    Conserva creator_id = user_id para que nadie más pueda reclamarlo.
    """
    owner_str = str(user_id)
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT owner_id, nombre FROM Personaje_Tabla WHERE tupper_tag = ?', (tupper_tag,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            return False, f"El personaje '{tupper_tag}' no existe."

        current_owner, nombre = row[0], row[1]
        if not current_owner or str(current_owner) != owner_str:
            return False, f"No puedes desactivar a **{nombre}** porque no está activo en tu cuenta."

        await db.execute('UPDATE Personaje_Tabla SET owner_id = NULL WHERE tupper_tag = ?', (tupper_tag,))
        await db.commit()
        _cache_personajes.pop(tupper_tag, None)
        return True, f"**{nombre}** ha sido guardado en tu reserva (inactivo). Su inventario e ítems se mantienen intactos."

async def buscar_personaje_por_nombre_db(nombre: str) -> tuple | None:
    """
    Búsqueda directa indexada en SQL por nombre o tupper_tag insensible a mayúsculas.
    Soporta términos limpiados de decoradores de autocompletado (🛡️, 📦, (@dueño))
    y similitud fonética/normalizada Unicode avanzada.
    """
    if not nombre:
        return None

    termino_limpio = limpiar_termino_busqueda(nombre)

    async with aiosqlite.connect(DB_FILE) as db:
        # 1. Búsqueda directa exacta o insensible a mayúsculas
        terminos_directos = [nombre]
        if termino_limpio and termino_limpio != nombre:
            terminos_directos.append(termino_limpio)

        for t in terminos_directos:
            async with db.execute(
                '''SELECT tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id 
                   FROM Personaje_Tabla 
                   WHERE LOWER(nombre) = LOWER(?) OR LOWER(tupper_tag) = LOWER(?) 
                   LIMIT 1''', 
                (t, t)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row

        # 2. Búsqueda con normalización Unicode avanzada (letras góticas, símbolos, corchetes, etc.)
        target_norm = normalizar_texto(termino_limpio) or normalizar_texto(nombre)
        if target_norm:
            async with db.execute(
                'SELECT tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id FROM Personaje_Tabla'
            ) as cursor:
                todos = await cursor.fetchall()
                # Coincidencia normalizada exacta
                for p in todos:
                    if normalizar_texto(p[1]) == target_norm or normalizar_texto(p[0]) == target_norm:
                        return p
                # Coincidencia normalizada por contención bidireccional
                for p in todos:
                    p_nom = normalizar_texto(p[1])
                    p_tag = normalizar_texto(p[0])
                    if (p_nom and (target_norm in p_nom or p_nom in target_norm)) or \
                       (p_tag and (target_norm in p_tag or p_tag in target_norm)):
                        return p

    return None


async def listar_todos_personajes() -> list[tuple]:
    """Lista todos los personajes registrados (útil para autocompletado)."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT tupper_tag, nombre, owner_id, creator_id FROM Personaje_Tabla ORDER BY nombre ASC') as cursor:
            return await cursor.fetchall()

async def auto_vincular_o_crear_personaje(tupper_name: str, avatar_url: str, user_id: str) -> tuple[bool, str]:
    """
    Registra en la reserva un personaje detectado pasivamente por webhook de Tupperbox.
    Guarda creator_id = user_id y owner_id = NULL para que lo active manualmente.
    """
    tupper_tag = tupper_name.strip()
    owner_str = str(user_id)
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT owner_id, creator_id, avatar_url FROM Personaje_Tabla WHERE tupper_tag = ?', (tupper_tag,)) as cursor:
            row = await cursor.fetchone()
            
        if not row:
            await db.execute('''
                INSERT INTO Personaje_Tabla (tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id)
                VALUES (?, ?, 'I', ?, '#FFFFFF', '#000000', NULL, ?)
            ''', (tupper_tag, tupper_tag, avatar_url or "", owner_str))
            await db.commit()
            _cache_personajes.pop(tupper_tag, None)
            return True, "creado_en_reserva"

        current_owner, current_creator, current_avatar = row[0], row[1], row[2]
        if current_creator is None or current_creator == "":
            await db.execute('UPDATE Personaje_Tabla SET creator_id = ?, avatar_url = COALESCE(NULLIF(?, ""), avatar_url) WHERE tupper_tag = ?', (owner_str, avatar_url, tupper_tag))
            await db.commit()
            _cache_personajes.pop(tupper_tag, None)
            return True, "guardado_en_reserva"
        elif str(current_creator) == owner_str:
            if avatar_url and avatar_url != current_avatar:
                await db.execute('UPDATE Personaje_Tabla SET avatar_url = ? WHERE tupper_tag = ?', (avatar_url, tupper_tag))
                await db.commit()
                _cache_personajes.pop(tupper_tag, None)
                return True, "actualizado"
            return True, "sin_cambios"
        else:
            return False, "pertenece_a_otro"

async def importar_tuppers_batch(owner_id: str, tuppers: list[dict]) -> dict:
    """
    Importa masivamente los tuppers exportados desde Tupperbox (tul!export) a la reserva del usuario.
    Guarda creator_id = owner_id y deja owner_id = NULL para que el usuario los active manualmente.
    """
    owner_str = str(owner_id)
    resultado = {
        "creados": [],
        "actualizados": [],
        "conflictos": []
    }

    async with aiosqlite.connect(DB_FILE) as db:
        for t in tuppers:
            nombre = str(t.get("name", "")).strip()
            if not nombre:
                continue

            avatar_url = str(t.get("avatar_url") or "").strip()
            
            async with db.execute('SELECT owner_id, creator_id, avatar_url FROM Personaje_Tabla WHERE tupper_tag = ?', (nombre,)) as cursor:
                row = await cursor.fetchone()

            if not row:
                await db.execute('''
                    INSERT INTO Personaje_Tabla (tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id)
                    VALUES (?, ?, 'I', ?, '#FFFFFF', '#000000', NULL, ?)
                ''', (nombre, nombre, avatar_url, owner_str))
                resultado["creados"].append(nombre)
                _cache_personajes.pop(nombre, None)
            else:
                curr_owner, curr_creator, _ = row[0], row[1], row[2]
                if (curr_creator is None or curr_creator == "" or str(curr_creator) == owner_str) and \
                   (curr_owner is None or curr_owner == "" or str(curr_owner) == owner_str):
                    await db.execute('''
                        UPDATE Personaje_Tabla 
                        SET creator_id = ?, 
                            avatar_url = CASE WHEN ? != '' THEN ? ELSE avatar_url END
                        WHERE tupper_tag = ?
                    ''', (owner_str, avatar_url, avatar_url, nombre))
                    resultado["actualizados"].append(nombre)
                    _cache_personajes.pop(nombre, None)
                else:
                    resultado["conflictos"].append(nombre)

        await db.commit()

    return resultado

# ==========================================
# 2. CATÁLOGO DE ÍTEMS
# ==========================================

async def crear_o_actualizar_item(item_id: str, nombre: str, emoji: str = "📦", categoria: str = "Material", descripcion: str = "", es_usable: int = 0, mensaje_uso: str = "", script_uso: str = None):
    iid = item_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO Items_Catalogo (item_id, nombre, emoji, categoria, descripcion, es_usable, mensaje_uso, script_uso)
            VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, ''))
            ON CONFLICT(item_id) DO UPDATE SET
                nombre=excluded.nombre,
                emoji=excluded.emoji,
                categoria=excluded.categoria,
                descripcion=excluded.descripcion,
                es_usable=excluded.es_usable,
                mensaje_uso=excluded.mensaje_uso,
                script_uso=COALESCE(?, Items_Catalogo.script_uso)
        ''', (iid, nombre, emoji, categoria, descripcion, es_usable, mensaje_uso, script_uso, script_uso))
        await db.commit()

async def editar_item_catalogo(
    item_id: str,
    nuevo_id: str = None,
    nombre: str = None,
    emoji: str = None,
    categoria: str = None,
    descripcion: str = None,
    es_usable: int = None,
    mensaje_uso: str = None,
    script_uso: str = None,
    script_id: str = None
) -> tuple[bool, str, dict | None]:
    """
    Edita cualquier propiedad de un ítem existente en el catálogo.
    Si se especifica nuevo_id, actualiza en cascada las referencias en inventarios y recetas.
    Retorna (éxito, mensaje, item_actualizado).
    """
    iid = item_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute('SELECT * FROM Items_Catalogo WHERE item_id = ? OR LOWER(nombre) = LOWER(?)', (iid, item_id))
        actual = await cur.fetchone()
        if not actual:
            return False, f"El ítem '{item_id}' no existe en el catálogo.", None

        actual_dict = dict(actual)
        target_id = actual_dict["item_id"]

        # Si se solicita cambiar el ID
        if nuevo_id and nuevo_id.strip().lower() != target_id:
            clean_nuevo_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', nuevo_id.strip().lower())
            # Comprobar colisión
            c_check = await db.execute('SELECT 1 FROM Items_Catalogo WHERE item_id = ?', (clean_nuevo_id,))
            if await c_check.fetchone():
                return False, f"Ya existe otro ítem con el identificador `{clean_nuevo_id}`.", None

            # Actualizar en cascada en las tablas que referencian el ítem
            await db.execute('UPDATE Inventarios SET item_id = ? WHERE item_id = ?', (clean_nuevo_id, target_id))
            await db.execute('UPDATE Recetas_Crafteo SET resultado_item_id = ? WHERE resultado_item_id = ?', (clean_nuevo_id, target_id))
            await db.execute('UPDATE Recetas_Ingredientes SET item_id = ? WHERE item_id = ?', (clean_nuevo_id, target_id))
            await db.execute('UPDATE Items_Catalogo SET item_id = ? WHERE item_id = ?', (clean_nuevo_id, target_id))
            target_id = clean_nuevo_id

        # Determinar valores finales
        nuevo_nombre = nombre if nombre is not None else actual_dict["nombre"]
        nuevo_emoji = emoji if emoji is not None else actual_dict["emoji"]
        nueva_categoria = categoria if categoria is not None else actual_dict["categoria"]
        nueva_descripcion = descripcion if descripcion is not None else actual_dict["descripcion"]
        nuevo_es_usable = es_usable if es_usable is not None else actual_dict["es_usable"]
        nuevo_mensaje_uso = mensaje_uso if mensaje_uso is not None else actual_dict["mensaje_uso"]
        nuevo_script_uso = script_uso if script_uso is not None else actual_dict["script_uso"]
        
        if script_id is not None:
            clean_sid = script_id.strip().lower()
            if clean_sid in ("", "none", "ninguno"):
                nuevo_script_id = None
            else:
                nuevo_script_id = clean_sid
        else:
            nuevo_script_id = actual_dict.get("script_id")

        await db.execute('''
            UPDATE Items_Catalogo SET
                nombre = ?,
                emoji = ?,
                categoria = ?,
                descripcion = ?,
                es_usable = ?,
                mensaje_uso = ?,
                script_uso = ?,
                script_id = ?
            WHERE item_id = ?
        ''', (
            nuevo_nombre,
            nuevo_emoji,
            nueva_categoria,
            nueva_descripcion,
            nuevo_es_usable,
            nuevo_mensaje_uso,
            nuevo_script_uso,
            nuevo_script_id,
            target_id
        ))
        await db.commit()

        c_updated = await db.execute('SELECT * FROM Items_Catalogo WHERE item_id = ?', (target_id,))
        row_up = await c_updated.fetchone()
        return True, "Ítem modificado con éxito.", dict(row_up)

async def actualizar_script_item(item_id: str, script: str) -> bool:
    """Actualiza el script Lua específico de un ítem en el catálogo."""
    iid = item_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            'UPDATE Items_Catalogo SET script_uso = ?, es_usable = CASE WHEN ? != "" THEN 1 ELSE es_usable END WHERE item_id = ? OR LOWER(nombre) = LOWER(?)', 
            (script, script.strip() if script else "", iid, item_id)
        )
        await db.commit()
        return cursor.rowcount > 0

async def asignar_script_item(item_id: str, script_id: str | None) -> tuple[bool, str]:
    """Asigna o desvincula un script compartido a un ítem, activando su usabilidad."""
    iid = item_id.strip().lower()
    sid = script_id.strip().lower() if script_id and script_id.strip().lower() not in ("none", "ninguno", "") else None

    async with aiosqlite.connect(DB_FILE) as db:
        if sid:
            cur = await db.execute('SELECT 1 FROM Scripts_Catalogo WHERE script_id = ?', (sid,))
            if not await cur.fetchone():
                return False, f"El script compartido con ID `{sid}` no existe."

        cur = await db.execute(
            'UPDATE Items_Catalogo SET script_id = ?, es_usable = CASE WHEN ? IS NOT NULL THEN 1 ELSE es_usable END WHERE item_id = ? OR LOWER(nombre) = LOWER(?)', 
            (sid, sid, iid, item_id)
        )
        await db.commit()
        if cur.rowcount > 0:
            return True, f"Script compartido `{sid}` asignado con éxito (ítem activado como usable)." if sid else "Script compartido desasignado."
        return False, f"No se encontró el ítem `{item_id}`."

# ==========================================
# BIBLIOTECA DE SCRIPTS COMPARTIDOS (LUA)
# ==========================================

async def crear_o_actualizar_script(script_id: str, nombre: str, descripcion: str = "", codigo: str = "") -> bool:
    """Crea o actualiza un script compartido en la biblioteca."""
    sid = re.sub(r'[^a-zA-Z0-9_\-]', '_', script_id.strip().lower())
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO Scripts_Catalogo (script_id, nombre, descripcion, codigo)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(script_id) DO UPDATE SET
                nombre=excluded.nombre,
                descripcion=excluded.descripcion,
                codigo=excluded.codigo
        ''', (sid, nombre, descripcion, codigo))
        await db.commit()
        return True

async def obtener_script(script_id: str) -> dict | None:
    """Obtiene un script compartido por ID o nombre."""
    if not script_id:
        return None
    sid = script_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM Scripts_Catalogo WHERE script_id = ? OR LOWER(nombre) = LOWER(?)',
            (sid, script_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def listar_scripts() -> list[dict]:
    """Retorna todos los scripts compartidos registrados."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM Scripts_Catalogo ORDER BY nombre ASC') as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def eliminar_script(script_id: str) -> bool:
    """Elimina un script compartido y lo desasigna de los ítems asociados."""
    sid = script_id.strip().lower()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE Items_Catalogo SET script_id = NULL WHERE script_id = ?', (sid,))
        cur = await db.execute('DELETE FROM Scripts_Catalogo WHERE script_id = ?', (sid,))
        await db.commit()
        return cur.rowcount > 0

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
                COALESCE(c.mensaje_uso, '') AS mensaje_uso,
                COALESCE(c.script_uso, '') AS script_uso,
                COALESCE(c.script_id, '') AS script_id
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
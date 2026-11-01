import re
import aiosqlite
from core.repos.base import conectar

# ==========================================
# 2. CATÁLOGO DE ÍTEMS
# ==========================================

async def crear_o_actualizar_item(item_id: str, nombre: str, emoji: str = "📦", categoria: str = "Material", descripcion: str = "", es_usable: int = 0, mensaje_uso: str = "", script_uso: str = None):
    iid = item_id.strip().lower()
    async with conectar() as db:
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
    async with conectar() as db:
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
    async with conectar() as db:
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

    async with conectar() as db:
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
    async with conectar() as db:
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
    async with conectar() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM Scripts_Catalogo WHERE script_id = ? OR LOWER(nombre) = LOWER(?)',
            (sid, script_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def listar_scripts() -> list[dict]:
    """Retorna todos los scripts compartidos registrados."""
    async with conectar() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM Scripts_Catalogo ORDER BY nombre ASC') as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def eliminar_script(script_id: str) -> bool:
    """Elimina un script compartido y lo desasigna de los ítems asociados."""
    sid = script_id.strip().lower()
    async with conectar() as db:
        await db.execute('UPDATE Items_Catalogo SET script_id = NULL WHERE script_id = ?', (sid,))
        cur = await db.execute('DELETE FROM Scripts_Catalogo WHERE script_id = ?', (sid,))
        await db.commit()
        return cur.rowcount > 0

async def obtener_item(item_id: str) -> dict | None:
    iid = item_id.strip().lower()
    async with conectar() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM Items_Catalogo WHERE item_id = ? OR LOWER(nombre) = LOWER(?)', 
            (iid, item_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def listar_items_catalogo(categoria: str = None) -> list[dict]:
    async with conectar() as db:
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
    async with conectar() as db:
        cursor = await db.execute('DELETE FROM Items_Catalogo WHERE item_id = ?', (iid,))
        await db.commit()
        return cursor.rowcount > 0

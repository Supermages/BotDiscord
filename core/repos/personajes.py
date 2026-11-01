import aiosqlite
from core.repos.base import conectar, _cache_personajes
from core.repos.texto import normalizar_texto, limpiar_termino_busqueda

# ==========================================
# 1. GESTIÓN DE PERSONAJES Y PROPIEDAD
# ==========================================

async def obtener_personaje(tupper_tag):
    if tupper_tag in _cache_personajes:
        return _cache_personajes[tupper_tag]

    async with conectar() as db:
        async with db.execute(
            'SELECT nombre, lado, avatar_url, color, color_texto, owner_id, creator_id FROM Personaje_Tabla WHERE tupper_tag = ?', 
            (tupper_tag,)
        ) as cursor:
            res = await cursor.fetchone()
            if res:
                _cache_personajes[tupper_tag] = res
            return res

async def guardar_personaje(tupper_tag, nombre, lado, avatar_url, color="#FFFFFF", color_texto="#000000", owner_id=None, creator_id=None):
    async with conectar() as db:
        await db.execute('''
            INSERT INTO Personaje_Tabla (tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tupper_tag) DO UPDATE SET
                nombre=excluded.nombre,
                lado=excluded.lado,
                avatar_url=CASE 
                    WHEN excluded.avatar_url IS NOT NULL 
                         AND excluded.avatar_url != '' 
                         AND excluded.avatar_url NOT LIKE '%embed/avatars/%' 
                    THEN excluded.avatar_url 
                    ELSE COALESCE(Personaje_Tabla.avatar_url, excluded.avatar_url) 
                END,
                color=excluded.color,
                color_texto=excluded.color_texto,
                owner_id=COALESCE(Personaje_Tabla.owner_id, excluded.owner_id),
                creator_id=COALESCE(Personaje_Tabla.creator_id, excluded.creator_id)
        ''', (tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id))
        await db.commit()
    _cache_personajes[tupper_tag] = (nombre, lado, avatar_url, color, color_texto, owner_id, creator_id)

async def actualizar_personaje(tupper_tag, nombre=None, avatar_url=None, lado=None, color=None, color_texto=None, owner_id=None, creator_id=None):
    async with conectar() as db:
        if nombre is not None:
            await db.execute('UPDATE Personaje_Tabla SET nombre = ? WHERE tupper_tag = ?', (str(nombre).strip(), tupper_tag))
        if avatar_url is not None:
            await db.execute('UPDATE Personaje_Tabla SET avatar_url = ? WHERE tupper_tag = ?', (str(avatar_url).strip(), tupper_tag))
        if lado:
            await db.execute('UPDATE Personaje_Tabla SET lado = ? WHERE tupper_tag = ?', (lado, tupper_tag))
        if color:
            await db.execute('UPDATE Personaje_Tabla SET color = ? WHERE tupper_tag = ?', (color, tupper_tag))
        if color_texto:
            await db.execute('UPDATE Personaje_Tabla SET color_texto = ? WHERE tupper_tag = ?', (color_texto, tupper_tag))
        if owner_id is not None:
            await db.execute('UPDATE Personaje_Tabla SET owner_id = ? WHERE tupper_tag = ?', (str(owner_id), tupper_tag))
        if creator_id is not None:
            await db.execute('UPDATE Personaje_Tabla SET creator_id = ? WHERE tupper_tag = ?', (str(creator_id), tupper_tag))
        await db.commit()
    _cache_personajes.pop(tupper_tag, None)

async def vincular_owner_personaje(tupper_tag: str, owner_id: str):
    """Vincula forzosamente un personaje a un usuario de Discord como activo."""
    async with conectar() as db:
        await db.execute('UPDATE Personaje_Tabla SET owner_id = ?, creator_id = COALESCE(creator_id, ?) WHERE tupper_tag = ?', (str(owner_id), str(owner_id), tupper_tag))
        await db.commit()
    _cache_personajes.pop(tupper_tag, None)


async def obtener_personajes_por_owner(owner_id: str) -> list[dict]:
    """Retorna los personajes que el usuario tiene actualmente vinculados en activo."""
    return await obtener_personajes_activos(owner_id)

async def obtener_personajes_activos(user_id: str) -> list[dict]:
    """Retorna los personajes que el usuario tiene actualmente activos (owner_id = user_id)."""
    async with conectar() as db:
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
    async with conectar() as db:
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
    async with conectar() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id, creator_id 
               FROM Personaje_Tabla 
               WHERE creator_id = ? AND (owner_id IS NULL OR owner_id = '')
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
    async with conectar() as db:
        # BEGIN IMMEDIATE: evita la carrera al contar el cupo de personajes activos
        await db.execute("BEGIN IMMEDIATE")

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

        if not current_creator or str(current_creator) != owner_str:
            return False, "Este personaje no pertenece a tu reserva personal. Puedes importarlo con `/pj importar` o crearlo con Tupperbox.", None

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
    async with conectar() as db:
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

    async with conectar() as db:
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
    async with conectar() as db:
        async with db.execute('SELECT tupper_tag, nombre, owner_id, creator_id FROM Personaje_Tabla ORDER BY nombre ASC') as cursor:
            return await cursor.fetchall()

async def auto_vincular_o_crear_personaje(tupper_name: str, avatar_url: str, user_id: str) -> tuple[bool, str]:
    """
    Registra en la reserva un personaje detectado pasivamente por webhook de Tupperbox.
    Guarda creator_id = user_id y owner_id = NULL para que lo active manualmente.
    """
    tupper_tag = tupper_name.strip()
    owner_str = str(user_id)
    async with conectar() as db:
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

    async with conectar() as db:
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

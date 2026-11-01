import aiosqlite
from core.repos.base import conectar

# ==========================================
# 3. GESTIÓN DE INVENTARIOS
# ==========================================

async def obtener_inventario_personaje(tupper_tag: str) -> list[dict]:
    """Retorna los ítems en el inventario de un personaje combinados con sus metadatos del catálogo."""
    async with conectar() as db:
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
    async with conectar() as db:
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
    async with conectar() as db:
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

    async with conectar() as db:
        # BEGIN IMMEDIATE: toma el candado de escritura ANTES de leer el stock
        # para evitar la carrera check-then-act entre transferencias concurrentes.
        await db.execute("BEGIN IMMEDIATE")

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

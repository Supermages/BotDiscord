import aiosqlite
from core.repos.base import conectar

# ==========================================
# 4. GESTIÓN DE RECETAS DE CRAFTEO
# ==========================================

async def crear_receta(receta_id: str, nombre: str, resultado_item_id: str, resultado_cantidad: int, ingredientes: dict[str, int], descripcion: str = ""):
    rid = receta_id.strip().lower()
    res_id = resultado_item_id.strip().lower()

    async with conectar() as db:
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
    async with conectar() as db:
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
    async with conectar() as db:
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

        if not recetas:
            return recetas

        # Segunda consulta única para TODOS los ingredientes (evita N+1 por receta)
        async with db.execute('''
            SELECT 
                ri.receta_id,
                ri.item_id, 
                ri.cantidad, 
                COALESCE(c.nombre, ri.item_id) AS nombre,
                COALESCE(c.emoji, '📦') AS emoji
            FROM Recetas_Ingredientes ri
            LEFT JOIN Items_Catalogo c ON ri.item_id = c.item_id
        ''') as cur:
            por_receta = {}
            for ing in await cur.fetchall():
                por_receta.setdefault(ing['receta_id'], []).append(dict(ing))

        for r in recetas:
            r['ingredientes'] = por_receta.get(r['receta_id'], [])

        return recetas

async def eliminar_receta(receta_id: str) -> bool:
    rid = receta_id.strip().lower()
    async with conectar() as db:
        cursor = await db.execute('DELETE FROM Recetas_Crafteo WHERE receta_id = ?', (rid,))
        await db.execute('DELETE FROM Recetas_Ingredientes WHERE receta_id = ?', (rid,))
        await db.commit()
        return cursor.rowcount > 0

import os
import logging
from core.repos import base
from core.repos.base import conectar

async def inicializar_base():
    os.makedirs(os.path.dirname(base.get_db_path()), exist_ok=True)
    async with conectar() as db:
        # Optimización de concurrencia y persistencia:
        # WAL (Write-Ahead Logging) permite múltiples lectores concurrentes sin bloquear escrituras
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

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

        # Limpieza de filas huérfanas creadas cuando las FK no se aplicaban
        # (p. ej. ítems entregados con texto libre en vez de item_id del catálogo)
        borrados = await _limpiar_filas_huerfanas(db)
        if any(borrados):
            await db.commit()
            logging.warning(f"[DB] Limpieza de huérfanos al inicializar: Inventarios={borrados[0]}, Ingredientes={borrados[1]}, Recetas={borrados[2]}")

async def _limpiar_filas_huerfanas(db) -> tuple[int, int, int]:
    """
    Elimina filas huérfanas creadas históricamente cuando las FOREIGN KEY no
    se aplicaban (ítems de inventario/recetas que ya no existen en el catálogo).
    Retorna (inventarios_borrados, ingredientes_borrados, recetas_borradas).
    """
    cur = await db.execute('DELETE FROM Inventarios WHERE item_id NOT IN (SELECT item_id FROM Items_Catalogo)')
    inv = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    cur = await db.execute('DELETE FROM Recetas_Ingredientes WHERE item_id NOT IN (SELECT item_id FROM Items_Catalogo)')
    ing = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    cur = await db.execute('DELETE FROM Recetas_Crafteo WHERE resultado_item_id NOT IN (SELECT item_id FROM Items_Catalogo)')
    rec = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    return inv, ing, rec

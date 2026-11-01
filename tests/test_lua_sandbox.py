"""
Tests de seguridad del sandbox Lua y de integridad referencial (FK) de la DB:
- services/lua_service.py: presupuesto de instrucciones, sandbox, bridge async.
- core/database.py: FOREIGN KEYs activas en todas las conexiones y cascadas.
"""

import os
import sys
import asyncio
import sqlite3
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.config import Config
from core.database import (
    inicializar_base,
    set_db_path,
    get_db_path,
    conectar,
    guardar_personaje,
    crear_o_actualizar_item,
    modificar_cantidad_inventario,
    eliminar_item_catalogo,
    obtener_inventario_personaje,
)
from services.lua_service import LuaEngine, LUA_MAX_INSTRUCCIONES

TEST_DB = os.path.join(BASE_DIR, "data", "test_lua_sandbox.sqlite")


class TestLuaSandbox(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.prev_db = get_db_path()
        set_db_path(TEST_DB)
        if os.path.exists(TEST_DB):
            try:
                os.remove(TEST_DB)
            except Exception:
                pass
        await inicializar_base()
        await guardar_personaje("arturo", "Arturo", "I", "")
        await crear_o_actualizar_item("pocion", "Pocion de cura", emoji="🧪", es_usable=1)
        await modificar_cantidad_inventario("arturo", "pocion", 3)
        self.engine = LuaEngine(db_path=TEST_DB)

    async def asyncTearDown(self):
        set_db_path(self.prev_db)
        for f in [TEST_DB, TEST_DB + "-wal", TEST_DB + "-shm"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    async def test_bucle_infinito_aborta_por_presupuesto(self):
        """Un script con bucle infinito debe abortarse, no colgar el bot."""
        ok, msg, _ = self.engine.ejecutar_script(
            "while true do end", "arturo", "pocion"
        )
        self.assertFalse(ok)
        self.assertIn("Presupuesto de instrucciones", msg)

    async def test_sandbox_anula_librerias_peligrosas(self):
        """os/io/load deben ser nil dentro del sandbox."""
        ok, msg, _ = self.engine.ejecutar_script(
            "if os == nil and io == nil and load == nil then reply('sandbox ok') else reply('FUGA') end",
            "arturo", "pocion"
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "sandbox ok")

    async def test_script_normal_funciona_y_muta_inventario(self):
        """El bridge de inventario (take/give) sigue funcionando con FK activas."""
        ok, msg, _ = self.engine.ejecutar_script(
            "reply('consumo') take_character_item(char, item, 1)",
            "arturo", "pocion"
        )
        self.assertTrue(ok)
        inventario = await obtener_inventario_personaje("arturo")
        cantidad = next((i["cantidad"] for i in inventario if i["item_id"] == "pocion"), 0)
        self.assertEqual(cantidad, 2)

    async def test_give_item_inexistente_rechazado_por_fk(self):
        """No se puede dar un ítem que no exista en el catálogo (integridad)."""
        ok, msg, _ = self.engine.ejecutar_script(
            'local r = give_character_item(char, "item_fantasma_xyz", 5) if r then reply("dado") else reply("rechazado") end',
            "arturo", "pocion"
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "rechazado")
        inventario = await obtener_inventario_personaje("arturo")
        self.assertFalse(any(i["item_id"] == "item_fantasma_xyz" for i in inventario))

    async def test_ejecutar_script_async(self):
        """La variante async corre en hilo aparte sin bloquear el event loop."""
        ok, msg, _ = await self.engine.ejecutar_script_async(
            "reply('async ok')", "arturo", "pocion"
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "async ok")


class TestIntegridadReferencial(unittest.IsolatedAsyncioTestCase):
    """Las FOREIGN KEY deben aplicarse en TODAS las conexiones (bug histórico)."""

    async def asyncSetUp(self):
        self.prev_db = get_db_path()
        set_db_path(TEST_DB)
        if os.path.exists(TEST_DB):
            try:
                os.remove(TEST_DB)
            except Exception:
                pass
        await inicializar_base()
        await guardar_personaje("arturo", "Arturo", "I", "")
        await crear_o_actualizar_item("pocion", "Pocion de cura", emoji="🧪", es_usable=1)
        await modificar_cantidad_inventario("arturo", "pocion", 2)

    async def asyncTearDown(self):
        set_db_path(self.prev_db)
        for f in [TEST_DB, TEST_DB + "-wal", TEST_DB + "-shm"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    async def test_fk_activas_en_cada_conexion(self):
        """conectar() debe activar foreign_keys en cada conexión que abre."""
        async with conectar() as db:
            async with db.execute("PRAGMA foreign_keys") as cur:
                row = await cur.fetchone()
                self.assertEqual(row[0], 1, "foreign_keys debe estar ON en toda conexión")

    async def test_insertar_item_inexistente_en_inventario_falla(self):
        """INSERT de inventario con item_id fuera del catálogo debe fallar (FK)."""
        async with conectar() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                await db.execute(
                    "INSERT INTO Inventarios (personaje_id, item_id, cantidad) VALUES (?, ?, ?)",
                    ("arturo", "no_existe", 1)
                )
                await db.commit()

    async def test_eliminar_item_del_catalogo_cascada_inventario(self):
        """ON DELETE CASCADE: borrar el ítem del catálogo limpia su inventario."""
        await eliminar_item_catalogo("pocion")
        inventario = await obtener_inventario_personaje("arturo")
        self.assertFalse(any(i["item_id"] == "pocion" for i in inventario))


if __name__ == "__main__":
    unittest.main()

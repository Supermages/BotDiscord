"""
Suite de Pruebas Automatizadas de Optimizaciones y Concurrencia para EriduBot.
Verifica:
1. Modo SQLite WAL y pragmas de persistencia.
2. Resistencia de concurrencia bajo lecturas y escrituras masivas simultaneas.
3. Renderizado de capturas por lotes (Batch Evaluation en Playwright).
4. Desactivacion de componentes en timeout (on_timeout) de las Vistas UI.
5. Integridad de base de datos en operaciones CRUD de personajes e inventario.
"""

import os
import sys
import asyncio
import unittest
from unittest.mock import MagicMock
import aiosqlite
import discord

# Asegurar que el directorio raiz este en sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.database import (
    inicializar_base,
    set_db_path,
    get_db_path,
    guardar_personaje,
    obtener_personaje,
    actualizar_personaje,
    activar_personaje,
    desactivar_personaje,
    obtener_personajes_activos,
    obtener_personajes_reserva
)
from renderer.captura import generar_captura, cerrar_navegador
from ui.views import LadoView, EditPersonajeView
from ui.character_views import CharacterPanelView
from ui.inventory_views import InventoryView, TransferConfirmView, RecipesView

TEST_DB_PATH = os.path.join(BASE_DIR, "data", "test_eridubot.sqlite")
TEST_EXPORT_IMG = os.path.join(BASE_DIR, "data", "test_batch_captura.png")


class TestOptimizations(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Configurar base de datos aislada para testing
        self.original_db = get_db_path()
        set_db_path(TEST_DB_PATH)
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass
        await inicializar_base()

    async def asyncTearDown(self):
        # Restaurar path original y limpiar archivos temporales
        set_db_path(self.original_db)
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass
        # Limpiar posibles archivos wal/shm
        for extra in [TEST_DB_PATH + "-wal", TEST_DB_PATH + "-shm"]:
            if os.path.exists(extra):
                try:
                    os.remove(extra)
                except Exception:
                    pass

        if os.path.exists(TEST_EXPORT_IMG):
            try:
                os.remove(TEST_EXPORT_IMG)
            except Exception:
                pass

    async def test_01_wal_mode_active(self):
        """Verifica que inicializar_base activa correctamente el modo WAL y pragmas en SQLite."""
        async with aiosqlite.connect(TEST_DB_PATH) as db:
            async with db.execute("PRAGMA journal_mode;") as cursor:
                row = await cursor.fetchone()
                journal_mode = row[0].lower() if row else ""
            
            async with db.execute("PRAGMA synchronous;") as cursor:
                row = await cursor.fetchone()
                sync_mode = row[0] if row else None

        self.assertEqual(journal_mode, "wal", f"Se esperaba modo 'wal', pero se obtuvo '{journal_mode}'")
        self.assertIsNotNone(sync_mode, "No se pudo obtener el valor de PRAGMA synchronous")
        print("  [PASS] Test 1: PRAGMA journal_mode=WAL y synchronous verificados.")

    async def test_02_database_concurrency_stress(self):
        """Prueba de estres con multiples lectores y escritores simultaneos para verificar ausencia de bloqueos."""
        # Insertar primero datos base
        for i in range(5):
            await guardar_personaje(
                tupper_tag=f"tag_{i}",
                nombre=f"Personaje_{i}",
                lado="I",
                avatar_url=f"http://example.com/p{i}.png",
                color="#112233",
                color_texto="#FFFFFF",
                creator_id="user_stress_test"
            )

        async def worker_lectura(identificador: int):
            for step in range(10):
                tag = f"tag_{step % 5}"
                pj = await obtener_personaje(tag)
                self.assertIsNotNone(pj, f"No se encontro el personaje {tag} durante lectura concurrente")
                await asyncio.sleep(0.005)

        async def worker_escritura(identificador: int):
            for step in range(5):
                tag = f"tag_{identificador}_{step}"
                await guardar_personaje(
                    tupper_tag=tag,
                    nombre=f"Concurrent_{identificador}_{step}",
                    lado="D",
                    avatar_url="http://example.com/c.png",
                    color="#AABBCC",
                    color_texto="#000000",
                    creator_id=f"user_{identificador}"
                )
                await asyncio.sleep(0.01)

        # 15 lectores simultaneos y 10 escritores simultaneos
        tareas = []
        for r in range(15):
            tareas.append(worker_lectura(r))
        for w in range(10):
            tareas.append(worker_escritura(w))

        # gather no debe lanzar sqlite3.OperationalError: database is locked
        await asyncio.gather(*tareas)
        print("  [PASS] Test 2: Concurrencia SQLite (25 tareas simultaneas sin bloqueos).")

    async def test_03_ui_views_timeout(self):
        """Verifica que on_timeout() desactiva todos los botones y selectores en todas las vistas interactivas."""
        # 1. LadoView
        lado_view = LadoView(autor_id=12345, personaje_id="test_tag", personaje_nombre="Test", avatar_url="")
        self.assertFalse(any(item.disabled for item in lado_view.children))
        await lado_view.on_timeout()
        self.assertTrue(all(item.disabled for item in lado_view.children), "LadoView no desactivo todos sus items en on_timeout")

        # 2. EditPersonajeView
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user.id = 12345
        edit_view = EditPersonajeView(
            interaction=mock_interaction,
            personaje_id="tag_edit",
            nombre="NombreTest",
            lado="I",
            color="#FFFFFF",
            color_texto="#000000",
            avatar_url=""
        )
        self.assertFalse(any(item.disabled for item in edit_view.children))
        await edit_view.on_timeout()
        self.assertTrue(all(item.disabled for item in edit_view.children), "EditPersonajeView no desactivo todos sus items en on_timeout")

        # 3. CharacterPanelView
        mock_user = MagicMock(spec=discord.User)
        mock_user.id = 99999
        panel_view = CharacterPanelView(user=mock_user, guild_id="123")
        panel_view._reconstruir_componentes()
        await panel_view.on_timeout()
        self.assertTrue(all(item.disabled for item in panel_view.children), "CharacterPanelView no desactivo todos sus items en on_timeout")

        # 4. TransferConfirmView
        transfer_view = TransferConfirmView(autor_id=12345)
        self.assertFalse(any(item.disabled for item in transfer_view.children))
        await transfer_view.on_timeout()
        self.assertTrue(all(item.disabled for item in transfer_view.children), "TransferConfirmView no desactivo todos sus items en on_timeout")

        # 5. RecipesView
        recetas_mock = [
            {
                "receta_id": "r1",
                "nombre": "Pocion",
                "descripcion": "Cura",
                "resultado_emoji": "🧪",
                "resultado_nombre": "Pocion Menor",
                "resultado_cantidad": 1,
                "ingredientes": [{"emoji": "🌿", "nombre": "Hierba", "cantidad": 2}]
            }
        ]
        rec_view = RecipesView(recetas=recetas_mock, autor_id=12345)
        await rec_view.on_timeout()
        self.assertTrue(all(item.disabled for item in rec_view.children), "RecipesView no desactivo todos sus items en on_timeout")

        # 6. InventoryView
        items_mock = [{"item_id": "i1", "nombre": "Espada", "emoji": "⚔️", "cantidad": 1}]
        inv_view = InventoryView(items_mock, "Guerrero", "", 12345)
        await inv_view.on_timeout()
        self.assertTrue(all(item.disabled for item in inv_view.children), "InventoryView no desactivo todos sus items en on_timeout")

        print("  [PASS] Test 3: Desactivacion on_timeout en 6 Vistas UI verificada exitosamente.")

    async def test_04_character_crud_integrity(self):
        """Verifica la persistencia y transiciones de estado de personajes (crear, editar, activar, reservar)."""
        user_id = "test_user_42"
        # 1. Crear personaje
        await guardar_personaje(
            tupper_tag="tag_mago",
            nombre="Mago Oscuro",
            lado="I",
            avatar_url="https://example.com/mago.png",
            color="#223344",
            color_texto="#EEEEEE",
            creator_id=user_id
        )

        pj = await obtener_personaje("tag_mago")
        self.assertIsNotNone(pj)
        self.assertEqual(pj[0], "Mago Oscuro")
        self.assertEqual(pj[1], "I")

        # 2. Actualizar personaje
        await actualizar_personaje(
            tupper_tag="tag_mago",
            nombre="Archimago",
            lado="D",
            avatar_url="https://example.com/archimago.png",
            color="#FF5500",
            color_texto="#FFFFFF"
        )
        pj_actualizado = await obtener_personaje("tag_mago")
        self.assertEqual(pj_actualizado[0], "Archimago")
        self.assertEqual(pj_actualizado[1], "D")
        self.assertEqual(pj_actualizado[3], "#FF5500")

        # 3. Ciclo de activacion / reserva
        ok, msg, _ = await activar_personaje(user_id, "tag_mago", limite=3)
        self.assertTrue(ok)
        activos = await obtener_personajes_activos(user_id)
        self.assertEqual(len(activos), 1)
        self.assertEqual(activos[0]["tupper_tag"], "tag_mago")

        ok_desact, _ = await desactivar_personaje(user_id, "tag_mago")
        self.assertTrue(ok_desact)
        activos_post = await obtener_personajes_activos(user_id)
        self.assertEqual(len(activos_post), 0)

        reserva = await obtener_personajes_reserva(user_id)
        self.assertEqual(len(reserva), 1)
        self.assertEqual(reserva[0]["tupper_tag"], "tag_mago")

        print("  [PASS] Test 4: CRUD e integridad de personajes (crear, actualizar, cupos).")

    async def test_05_playwright_batch_render(self):
        """Verifica que la optimizacion de batch render en Playwright genera imagenes validas."""
        # Insertar dos personajes para el chat
        await guardar_personaje("alice", "Alice", "I", "https://cdn.discordapp.com/embed/avatars/1.png", "#2C3E50", "#FFFFFF")
        await guardar_personaje("bob", "Bob", "D", "https://cdn.discordapp.com/embed/avatars/2.png", "#27AE60", "#FFFFFF")

        chat_mock = {
            "Chat": {
                "titulo": "Sesion de Rol - Batch Render Test",
                "fecha": "2026-10-03",
                "mensajes": [
                    {"Personaje": "alice", "Mensaje": "Hola Bob, listo para la mision?", "Adjuntos": []},
                    {"Personaje": "bob", "Mensaje": "Siempre preparado Alice. Vamos!", "Adjuntos": []},
                    {"Personaje": "alice", "Mensaje": "Revisemos el inventario primero.", "Adjuntos": []},
                    {"Personaje": "bob", "Mensaje": "Tengo las pociones y las armas.", "Adjuntos": []}
                ]
            }
        }

        try:
            ruta_generada = await generar_captura(chat_mock, output_path=TEST_EXPORT_IMG)
            self.assertTrue(os.path.exists(ruta_generada), "No se genero el archivo de imagen de captura")
            tamanio = os.path.getsize(ruta_generada)
            self.assertGreater(tamanio, 1000, f"El archivo generado es demasiado pequenio: {tamanio} bytes")
            print(f"  [PASS] Test 5: Playwright Batch Render completado exitosamente ({tamanio} bytes).")
        finally:
            await cerrar_navegador()


def run_tests():
    print("=" * 65)
    print(" EJECUTANDO SUITE DE TESTS INTERNOS - ERIDUBOT")
    print("=" * 65)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestOptimizations)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("=" * 65)
    if result.wasSuccessful():
        print(" TODOS LOS TESTS PASARON EXITOSAMENTE [PASS]")
        return 0
    else:
        print(f" TESTS FALLIDOS: {len(result.failures)} errores: {len(result.errors)}")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())

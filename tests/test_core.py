"""
Tests unitarios y de integracion para el modulo Core de EriduBot:
- core/config.py
- core/formatters.py
- core/permissions.py
- core/database.py
"""

import os
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import discord
from core.config import Config, BASE_DIR
from core.formatters import limpiar_formato_discord
from core.permissions import requiere_admin, es_admin, PermisoDenegado
from core.database import (
    inicializar_base,
    set_db_path,
    get_db_path,
    normalizar_texto,
    limpiar_termino_busqueda,
    guardar_personaje,
    obtener_personaje,
    buscar_personaje_por_nombre_db,
    actualizar_personaje,
    activar_personaje,
    desactivar_personaje,
    obtener_personajes_activos,
    obtener_personajes_reserva,
    obtener_limite_personajes,
    establecer_limite_personajes,
    guardar_tupperbox_webhook,
    obtener_tupperbox_webhook,
    get_modo_captura,
    set_modo_captura,
    crear_o_actualizar_item,
    obtener_item,
    eliminar_item_catalogo,
    obtener_inventario_personaje,
    modificar_cantidad_inventario,
    transferir_item_atomico,
    crear_receta,
    obtener_receta,
    eliminar_receta
)
from services.crafting_service import verificar_y_craftear

TEST_DB = os.path.join(BASE_DIR, "data", "test_core.sqlite")


class TestCoreConfigAndFormatters(unittest.TestCase):

    def test_config_paths_and_defaults(self):
        """Verifica que las rutas y constantes de configuracion sean validas."""
        self.assertTrue(os.path.isabs(BASE_DIR))
        self.assertTrue(isinstance(Config.MAX_MENSAJES_TOTAL, int))
        self.assertGreater(Config.MAX_MENSAJES_TOTAL, 0)
        self.assertIsNotNone(Config.DATABASE_PATH)
        self.assertIsNotNone(Config.EXPORT_FOLDER)

    def test_formatters_limpiar_discord(self):
        """Verifica la conversion de sintaxis de Discord a HTML para el renderizador."""
        # 1. Limpieza de GIFs
        texto_gif = "Hola mira https://tenor.com/view/funny-cat-12345 adios"
        limpio_gif = limpiar_formato_discord(texto_gif)
        self.assertNotIn("tenor.com", limpio_gif)

        # 2. Reemplazo de emojis personalizados
        texto_emoji = "Reacciona <:fuego:9876543210>"
        limpio_emoji = limpiar_formato_discord(texto_emoji)
        self.assertIn('<img class="custom-emoji"', limpio_emoji)
        self.assertIn('cdn.discordapp.com/emojis/9876543210.png', limpio_emoji)

        # 3. Encabezados de Discord
        self.assertIn("font-size: 1.05em", limpiar_formato_discord("### Subtitulo"))
        self.assertIn("font-size: 1.18em", limpiar_formato_discord("## Titulo"))
        self.assertIn("font-size: 1.35em", limpiar_formato_discord("# Titulo Principal"))

        # 4. Citas y subtexto
        self.assertIn("border-left", limpiar_formato_discord("> Esto es una cita"))
        self.assertIn("font-size: 0.82em", limpiar_formato_discord("-# Esto es un subtexto"))

    def test_normalizar_texto(self):
        """Verifica que normalizar_texto elimine fuentes fancy y diacriticos."""
        self.assertEqual(normalizar_texto("★ 𝕬𝖗𝖙𝖚𝖗𝖔 ★"), "arturo")
        self.assertEqual(normalizar_texto("【Elena】"), "elena")
        self.assertEqual(normalizar_texto("René"), "rene")
        self.assertEqual(normalizar_texto(""), "")

    def test_limpiar_termino_busqueda(self):
        """Verifica que limpiar_termino_busqueda retire emojis y sufijos de autocompletado."""
        self.assertEqual(limpiar_termino_busqueda("🛡️ Arturo (Activo)"), "Arturo")
        self.assertEqual(limpiar_termino_busqueda("📦 Sayaka (@Dueño)"), "Sayaka")
        self.assertEqual(limpiar_termino_busqueda("⭐ Elena (ID: 12345)"), "Elena")
        self.assertEqual(limpiar_termino_busqueda(""), "")


class TestCorePermissions(unittest.IsolatedAsyncioTestCase):

    async def test_requiere_admin_decorator(self):
        """Verifica que el decorador requiere_admin permita solo a usuarios con permiso/rol admin."""
        mock_admin_role = MagicMock()
        mock_admin_role.name = Config.ROL_ADMIN
        mock_admin_role.id = 111111

        mock_other_role = MagicMock()
        mock_other_role.name = "Jugador"
        mock_other_role.id = 222222

        def _member(roles):
            member = MagicMock(spec=discord.Member)
            member.roles = roles
            # Sin permisos de servidor: la vía de paso debe ser el rol/permiso explícito
            member.guild_permissions.administrator = False
            member.guild_permissions.manage_guild = False
            return member

        # Usuario sin rol admin -> lanza PermisoDenegado (respuesta efímera vía on_tree_error)
        mock_interaction_deny = MagicMock(spec=discord.Interaction)
        mock_interaction_deny.user = _member([mock_other_role])

        check_dec = requiere_admin()

        @check_dec
        async def dummy_command(interaction):
            pass

        predicate = dummy_command.__discord_app_commands_checks__[0]

        with self.assertRaises(PermisoDenegado):
            await predicate(mock_interaction_deny)

        # Usuario con rol admin -> pasa
        mock_interaction_allow = MagicMock(spec=discord.Interaction)
        mock_interaction_allow.user = _member([mock_other_role, mock_admin_role])

        result_allow = await predicate(mock_interaction_allow)
        self.assertTrue(result_allow)

        # Usuario con permiso Discord administrator -> también pasa (vía robusta)
        member_discord_admin = _member([mock_other_role])
        member_discord_admin.guild_permissions.administrator = True
        mock_interaction_discord_admin = MagicMock(spec=discord.Interaction)
        mock_interaction_discord_admin.user = member_discord_admin
        result_discord_admin = await predicate(mock_interaction_discord_admin)
        self.assertTrue(result_discord_admin)


class TestCoreDatabase(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.prev_db = get_db_path()
        set_db_path(TEST_DB)
        if os.path.exists(TEST_DB):
            try:
                os.remove(TEST_DB)
            except Exception:
                pass
        await inicializar_base()

    async def asyncTearDown(self):
        set_db_path(self.prev_db)
        for f in [TEST_DB, TEST_DB + "-wal", TEST_DB + "-shm"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    async def test_personajes_crud_y_busquedas(self):
        """Prueba exhaustiva de personajes, busquedas difusas y cuotas."""
        # 1. Guardar personajes
        await guardar_personaje("pj1", "Elena Valkiria", "I", "https://example.com/elena.png", "#FFFFFF", "#000000", creator_id="u1")
        await guardar_personaje("pj2", "Arturo Pendragon", "D", "https://example.com/arturo.png", "#112233", "#FFFFFF", creator_id="u1")

        # 2. Obtener por tag
        p1 = await obtener_personaje("pj1")
        self.assertIsNotNone(p1)
        self.assertEqual(p1[0], "Elena Valkiria")
        self.assertEqual(p1[1], "I")

        # 3. Busquedas flexibles por nombre
        por_fuzzy = await buscar_personaje_por_nombre_db("arturo")
        self.assertIsNotNone(por_fuzzy)
        self.assertEqual(por_fuzzy[0], "pj2")
        self.assertEqual(por_fuzzy[1], "Arturo Pendragon")

        # 4. Modificar limites por guild
        limite_default = await obtener_limite_personajes("guild_1")
        self.assertEqual(limite_default, 3)
        await establecer_limite_personajes("guild_1", 5)
        limite_nuevo = await obtener_limite_personajes("guild_1")
        self.assertEqual(limite_nuevo, 5)

        # 5. Activar y desactivar cupos
        ok, _, _ = await activar_personaje("u1", "pj1", limite=5)
        self.assertTrue(ok)
        ok2, _, _ = await activar_personaje("u1", "pj2", limite=5)
        self.assertTrue(ok2)

        activos = await obtener_personajes_activos("u1")
        self.assertEqual(len(activos), 2)

        # Desactivar uno
        ok_des, _ = await desactivar_personaje("u1", "pj1")
        self.assertTrue(ok_des)
        activos_post = await obtener_personajes_activos("u1")
        self.assertEqual(len(activos_post), 1)
        reserva = await obtener_personajes_reserva("u1")
        self.assertEqual(len(reserva), 1)

    async def test_tupperbox_webhooks_y_modos(self):
        """Verifica almacenamiento y cache de webhooks y modo de captura por guild."""
        # Webhooks
        await guardar_tupperbox_webhook("g1", 99887766)
        wh = await obtener_tupperbox_webhook("g1")
        self.assertIsNotNone(wh)
        self.assertEqual(int(wh[0]), 99887766)

        # Modo de captura (TUPPER vs NORMAL)
        modo_def = await get_modo_captura("g1")
        self.assertEqual(modo_def, "TUPPER")
        await set_modo_captura("g1", "NORMAL")
        modo_act = await get_modo_captura("g1")
        self.assertEqual(modo_act, "NORMAL")

    async def test_inventario_y_transferencias(self):
        """Prueba catalogo de items, agregacion a inventarios y transferencia atomica."""
        # 1. Crear items en catalogo
        await crear_o_actualizar_item("pocion_vida", "Pocion de Vida", "🧪", "Consumible", "Restaura 50 HP", es_usable=1)
        await crear_o_actualizar_item("espada_hierro", "Espada de Hierro", "⚔️", "Arma", "Arma basica", es_usable=0)

        it = await obtener_item("pocion_vida")
        self.assertIsNotNone(it)
        self.assertEqual(it["nombre"], "Pocion de Vida")
        self.assertEqual(it["es_usable"], 1)

        # 2. Agregar a inventario de personaje
        await guardar_personaje("p_orig", "Origen", "I", "", creator_id="u_orig")
        await guardar_personaje("p_dest", "Destino", "D", "", creator_id="u_dest")

        await modificar_cantidad_inventario("p_orig", "pocion_vida", 5)
        await modificar_cantidad_inventario("p_orig", "espada_hierro", 1)

        inv_orig = await obtener_inventario_personaje("p_orig")
        self.assertEqual(len(inv_orig), 2)
        cant_pociones = next(i["cantidad"] for i in inv_orig if i["item_id"] == "pocion_vida")
        self.assertEqual(cant_pociones, 5)

        # 3. Transferencia atomica
        ok, msg = await transferir_item_atomico("p_orig", "p_dest", "pocion_vida", 3)
        self.assertTrue(ok)

        inv_orig_post = await obtener_inventario_personaje("p_orig")
        pociones_orig_post = next(i["cantidad"] for i in inv_orig_post if i["item_id"] == "pocion_vida")
        self.assertEqual(pociones_orig_post, 2)

        inv_dest = await obtener_inventario_personaje("p_dest")
        pociones_dest = next(i["cantidad"] for i in inv_dest if i["item_id"] == "pocion_vida")
        self.assertEqual(pociones_dest, 3)

        # 4. Transferencia rechazada por falta de stock
        ok_fail, _ = await transferir_item_atomico("p_orig", "p_dest", "pocion_vida", 10)
        self.assertFalse(ok_fail)

    async def test_sistema_de_crafteo(self):
        """Verifica creacion de recetas y fabricacion con consumo de ingredientes."""
        # 1. Crear materiales y producto
        await crear_o_actualizar_item("hierro", "Mineral de Hierro", "⛏️", "Material", "Material crudo")
        await crear_o_actualizar_item("madera", "Tronco de Madera", "🪵", "Material", "Material base")
        await crear_o_actualizar_item("hacha", "Hacha de Batalla", "🪓", "Arma", "Arma contundente")

        # 2. Crear receta (ingredientes como diccionario {item_id: cantidad})
        ingredientes_dict = {
            "hierro": 2,
            "madera": 1
        }
        await crear_receta("rec_hacha", "Forjar Hacha", "hacha", 1, ingredientes_dict, "Forja un hacha")

        rec = await obtener_receta("rec_hacha")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["resultado_nombre"], "Hacha de Batalla")

        # 3. Fabricar sin materiales -> Debe fallar
        await guardar_personaje("artesano", "Herrero", "I", "")
        ok_craf_fail, _, _ = await verificar_y_craftear("artesano", "rec_hacha", 1)
        self.assertFalse(ok_craf_fail)

        # 4. Proveer materiales y fabricar -> Debe tener exito
        await modificar_cantidad_inventario("artesano", "hierro", 4)
        await modificar_cantidad_inventario("artesano", "madera", 3)

        ok_craf, msg, _ = await verificar_y_craftear("artesano", "rec_hacha", 2)
        self.assertTrue(ok_craf)

        inv_artesano = await obtener_inventario_personaje("artesano")
        hachas = next((i["cantidad"] for i in inv_artesano if i["item_id"] == "hacha"), 0)
        hierro_restante = next((i["cantidad"] for i in inv_artesano if i["item_id"] == "hierro"), 0)
        madera_restante = next((i["cantidad"] for i in inv_artesano if i["item_id"] == "madera"), 0)

        self.assertEqual(hachas, 2)
        self.assertEqual(hierro_restante, 0)
        self.assertEqual(madera_restante, 1)


if __name__ == "__main__":
    unittest.main()

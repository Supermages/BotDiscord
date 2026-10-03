"""
Tests de integridad estructural y seguridad de Comandos y Cogs de EriduBot:
- Verifica importabilidad de todas las extensiones oficiales.
- Valida la existencia y firma del entrypoint asincrono `setup(bot)`.
- Comprueba que todos los Cogs se instancian y registran sus grupos de comandos.
- Audita las politicas de seguridad y permisos por defecto de comandos restringidos.
"""

import os
import sys
import importlib
import inspect
import unittest
from unittest.mock import MagicMock, AsyncMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import discord
from discord.ext import commands

from bot import EXTENSIONES
from cogs.chat_commands import ChatCommands
from cogs.character_commands import CharacterCommands
from cogs.inventory_commands import InventoryCommands
from cogs.crafting_commands import CraftingCommands
from cogs.admin_rpg_commands import AdminRPGCommands
from cogs.dice_commands import DiceCommands


class TestCogsIntegrity(unittest.IsolatedAsyncioTestCase):

    def test_extensiones_definidas_y_validas(self):
        """Verifica que la lista de extensiones del bot contenga los 6 cogs esperados."""
        esperadas = [
            "cogs.chat_commands",
            "cogs.character_commands",
            "cogs.inventory_commands",
            "cogs.crafting_commands",
            "cogs.admin_rpg_commands",
            "cogs.dice_commands"
        ]
        self.assertEqual(len(EXTENSIONES), 6)
        for ext in esperadas:
            self.assertIn(ext, EXTENSIONES, f"La extension {ext} no esta en EXTENSIONES")

    async def test_setup_entrypoints_y_add_cog(self):
        """Verifica que cada modulo de Cog tenga una funcion async setup(bot) funcional."""
        for ext_name in EXTENSIONES:
            mod = importlib.import_module(ext_name)
            self.assertTrue(hasattr(mod, "setup"), f"El modulo {ext_name} no define funcion setup")
            self.assertTrue(inspect.iscoroutinefunction(mod.setup), f"setup en {ext_name} debe ser asincrono")

            # Simular carga con un bot mock
            mock_bot = MagicMock(spec=commands.Bot)
            mock_bot.add_cog = AsyncMock()
            mock_bot.tree = MagicMock()

            await mod.setup(mock_bot)
            mock_bot.add_cog.assert_awaited_once()

    def test_seguridad_chat_commands(self):
        """Audita que el grupo /chat y comandos criticos tengan politicas de seguridad administrativas."""
        mock_bot = MagicMock(spec=commands.Bot)
        cog = ChatCommands(mock_bot)

        # 1. Grupo /chat debe requerir permisos de administrador
        self.assertEqual(cog.chat_group.name, "chat")
        perms = cog.chat_group.default_permissions
        self.assertIsNotNone(perms, "El grupo /chat debe tener default_permissions configurado")
        self.assertTrue(perms.administrator, "El grupo /chat debe exigir permisos de administrador")

        # 2. Subcomandos esperados
        subcomandos = [cmd.name for cmd in cog.chat_group.walk_commands()]
        self.assertIn("generar", subcomandos)
        self.assertIn("configuracion", subcomandos)
        self.assertIn("spam_ping", subcomandos)

    def test_seguridad_admin_rpg_commands(self):
        """Audita que /admin_rpg tenga default_permissions de administrador."""
        mock_bot = MagicMock(spec=commands.Bot)
        cog = AdminRPGCommands(mock_bot)

        self.assertEqual(cog.admin_rpg_group.name, "admin_rpg")
        perms = cog.admin_rpg_group.default_permissions
        self.assertIsNotNone(perms, "El grupo /admin_rpg debe tener default_permissions")
        self.assertTrue(perms.administrator, "El grupo /admin_rpg debe exigir administrator=True")

        subcomandos = [cmd.name for cmd in cog.admin_rpg_group.walk_commands()]
        self.assertIn("item_crear", subcomandos)
        self.assertIn("item_dar", subcomandos)
        self.assertIn("item_quitar", subcomandos)
        self.assertIn("receta_crear", subcomandos)

    def test_character_commands_structure(self):
        """Verifica la estructura y subcomandos de /pj."""
        mock_bot = MagicMock(spec=commands.Bot)
        cog = CharacterCommands(mock_bot)

        self.assertEqual(cog.pj_group.name, "pj")
        subcomandos = [cmd.name for cmd in cog.pj_group.walk_commands()]
        self.assertIn("panel", subcomandos)
        self.assertIn("lista", subcomandos)
        self.assertIn("editar", subcomandos)
        self.assertIn("importar", subcomandos)
        self.assertIn("vincular", subcomandos)

    def test_inventory_commands_structure(self):
        """Verifica la estructura y subcomandos de /inv."""
        mock_bot = MagicMock(spec=commands.Bot)
        cog = InventoryCommands(mock_bot)

        self.assertEqual(cog.inv_group.name, "inv")
        subcomandos = [cmd.name for cmd in cog.inv_group.walk_commands()]
        self.assertIn("ver", subcomandos)
        self.assertIn("usar", subcomandos)
        self.assertIn("transferir", subcomandos)

    def test_crafting_commands_structure(self):
        """Verifica la estructura y subcomandos de /craft."""
        mock_bot = MagicMock(spec=commands.Bot)
        cog = CraftingCommands(mock_bot)

        self.assertEqual(cog.craft_group.name, "craft")
        subcomandos = [cmd.name for cmd in cog.craft_group.walk_commands()]
        self.assertIn("recetas", subcomandos)
        self.assertIn("fabricar", subcomandos)

    def test_dice_commands_structure(self):
        """Verifica los comandos /roll y /dado."""
        mock_bot = MagicMock(spec=commands.Bot)
        cog = DiceCommands(mock_bot)

        # Verificar metodos de comando
        self.assertTrue(hasattr(cog, "roll"))
        self.assertTrue(hasattr(cog, "dado"))


if __name__ == "__main__":
    unittest.main()

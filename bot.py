import asyncio
import logging
import discord
from discord.ext import commands

from core.config import Config
from core.database import inicializar_base
from renderer.captura import iniciar_navegador, cerrar_navegador
from services.monitor_service import monitor_manager

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s]: %(message)s'
)

EXTENSIONES = [
    "cogs.chat_commands",
    "cogs.monitor_commands",
    "cogs.character_commands",
    "cogs.admin_commands"
]

class EriduBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # 1. Inicializar la base de datos y sus índices
        await inicializar_base()
        logging.info("[DB] Base de datos SQLite lista.")

        # 2. Inicializar la instancia compartida de Playwright Chromium
        await iniciar_navegador()
        logging.info("[Playwright] Motor de renderizado listo.")

        # 3. Cargar extensiones modulares (Cogs)
        for ext in EXTENSIONES:
            try:
                await self.load_extension(ext)
                logging.info(f"[Cogs] Cargado exitosamente: {ext}")
            except Exception as e:
                logging.error(f"[Cogs] Error cargando {ext}: {e}")

        # 4. Sincronizar comandos Slash con Discord
        logging.info("[Tree] Sincronizando comandos Slash...")
        await self.tree.sync()
        logging.info("[Tree] Comandos Slash sincronizados.")

    async def on_ready(self):
        logging.info(f"✅ Bot listo como {self.user} (ID: {self.user.id})")

    async def close(self):
        logging.info("Deteniendo el bot y liberando recursos...")
        monitor_manager.detener_todos()
        await cerrar_navegador()
        await super().close()

bot = EriduBot()

if __name__ == "__main__":
    bot.run(Config.DISCORD_TOKEN)
import asyncio
import logging
import discord
from discord.ext import commands

from core.config import Config
from core.database import inicializar_base
from renderer.captura import iniciar_navegador, cerrar_navegador
from services.monitor_service import monitor_manager
from services.hot_reload_service import hot_reload_manager
from services.inventory_service import es_admin

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s]: %(message)s'
)

EXTENSIONES = [
    "cogs.chat_commands",
    "cogs.character_commands",
    "cogs.inventory_commands",
    "cogs.crafting_commands",
    "cogs.admin_rpg_commands",
    "cogs.dice_commands"
]

class EriduBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self._web_runner = None

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
        try:
            await self.tree.sync()
            logging.info("[Tree] Comandos Slash sincronizados.")
        except Exception as e:
            logging.error(f"[Tree] Error sincronizando comandos Slash: {e}")

        # 5. Gestor global de errores para App Commands
        async def on_tree_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
            cmd_name = interaction.command.name if interaction.command else "desconocido"
            logging.error(f"[Tree Error] En /{cmd_name}: {error}", exc_info=error)
            msg = "⚠️ Ha ocurrido un error inesperado al ejecutar esta acción. Se ha registrado en la consola para su revisión."
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
            except Exception:
                pass

        self.tree.on_error = on_tree_error

        # 6. Inicializar Hot-Reloading en desarrollo
        if Config.AUTO_RELOAD:
            hot_reload_manager.set_bot(self)
            hot_reload_manager.start()

        # 7. Servidor web ligero para Healthchecks en la nube (Render, Koyeb, Fly, etc.)
        if Config.PORT:
            try:
                from aiohttp import web
                app = web.Application()
                async def handle_health(request):
                    return web.json_response({
                        "status": "online",
                        "bot": str(self.user),
                        "cogs": list(self.extensions.keys()),
                        "ping_ms": round(self.latency * 1000, 2)
                    })
                app.router.add_get("/", handle_health)
                app.router.add_get("/health", handle_health)
                self._web_runner = web.AppRunner(app)
                await self._web_runner.setup()
                site = web.TCPSite(self._web_runner, "0.0.0.0", int(Config.PORT))
                await site.start()
                logging.info(f"[Web] Healthcheck activo en http://0.0.0.0:{Config.PORT}")
            except Exception as e:
                logging.warning(f"[Web] No se pudo iniciar el healthcheck web: {e}")

    async def on_ready(self):
        logging.info(f"✅ Bot listo como {self.user} (ID: {self.user.id})")

    async def close(self):
        logging.info("Deteniendo el bot y liberando recursos...")
        if self._web_runner:
            await self._web_runner.cleanup()
        hot_reload_manager.stop()
        monitor_manager.detener_todos()
        await cerrar_navegador()
        await super().close()

bot = EriduBot()

# ========================================================
# COMANDOS CON PREFIJO PARA DESARROLLADORES (!reload, !sync)
# ========================================================
@bot.command(name="reload", hidden=True)
async def cmd_reload(ctx: commands.Context, modulo: str = "todos"):
    """Comando de desarrollo para recargar módulos en caliente sin reiniciar el bot."""
    if not es_admin(ctx.author):
        return await ctx.reply("❌ Solo los administradores pueden recargar módulos.", mention_author=False)

    if modulo.lower() in ("todos", "all"):
        ok, exitos, errores = await hot_reload_manager.reload_all()
        if ok:
            await ctx.reply(f"✅ Se han recargado **{len(exitos)}** extensiones exitosamente.", mention_author=False)
        else:
            err_str = "\n".join(errores[:5])
            await ctx.reply(f"⚠️ Recarga completada con errores ({len(exitos)} éxitos, {len(errores)} fallos):\n```{err_str}```", mention_author=False)
    else:
        ok, msg = await hot_reload_manager.reload_cog(modulo)
        emoji = "✅" if ok else "❌"
        await ctx.reply(f"{emoji} {msg}", mention_author=False)

@bot.command(name="sync", hidden=True)
async def cmd_sync(ctx: commands.Context, servidor: str = "este"):
    """Comando de desarrollo para forzar la sincronización del árbol de comandos."""
    if not es_admin(ctx.author):
        return await ctx.reply("❌ Solo los administradores pueden sincronizar comandos.", mention_author=False)

    guild_id = ctx.guild.id if servidor.lower() in ("este", "guild", "server") else None
    ok, msg = await hot_reload_manager.sync_tree(guild_id)
    emoji = "✅" if ok else "❌"
    await ctx.reply(f"{emoji} {msg}", mention_author=False)

if __name__ == "__main__":
    bot.run(Config.DISCORD_TOKEN)
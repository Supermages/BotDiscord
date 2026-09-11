import datetime
import logging
from datetime import timezone
import discord
from discord import app_commands
from discord.ext import commands
from core.permissions import requiere_admin
from services.monitor_service import monitor_manager

class MonitorCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="listarmonitores", description="Muestra todos los monitores activos.")
    @requiere_admin()
    async def listarmonitores(self, interaction: discord.Interaction):
        monitores = monitor_manager.obtener_monitores()
        if not monitores:
            embed = discord.Embed(
                title="📭 Monitores activos",
                description="Actualmente no hay ningún monitor activo.",
                color=0xAAAAAA
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        desc = ""
        ahora = datetime.datetime.now(timezone.utc)
        for canal_id, info in monitores.items():
            restante = max(0, (info["hasta"] - ahora).total_seconds() // 60)
            desc += f"• Canal <#{canal_id}> — {int(restante)} min restantes\n"

        embed = discord.Embed(
            title="📡 Monitores activos",
            description=desc,
            color=0x00B0F4
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logging.info("Se listaron los monitores activos")

    @app_commands.command(name="detenermonitor", description="Detiene el monitor en el canal actual.")
    @requiere_admin()
    async def detenermonitor(self, interaction: discord.Interaction):
        canal_id = interaction.channel.id
        detenido = monitor_manager.detener_monitor(canal_id)

        if detenido:
            embed = discord.Embed(
                title="🛑 Monitor detenido",
                description="El monitor de este canal ha sido detenido correctamente.",
                color=0xFF5733
            )
        else:
            embed = discord.Embed(
                title="⚠️ Sin monitor",
                description="Este canal no tiene un monitor activo actualmente.",
                color=0xCCCC00
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MonitorCommands(bot))

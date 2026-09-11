import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
from core.permissions import requiere_admin
from core.database import set_modo_captura

class AdminCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="configuracion", description="Configura el modo de captura del bot.")
    @app_commands.describe(modo="Elige qué mensajes debe capturar el bot")
    @app_commands.choices(modo=[
        app_commands.Choice(name="🎭 Solo Tupperbox (Por defecto)", value="TUPPER"),
        app_commands.Choice(name="📢 Todo el chat (Usuarios y Bots)", value="TODO")
    ])
    @requiere_admin()
    async def configuracion(self, interaction: discord.Interaction, modo: app_commands.Choice[str]):
        await set_modo_captura(interaction.guild_id, modo.value)
        
        texto = "🎭 **Solo Tupperbox**" if modo.value == "TUPPER" else "📢 **Todo el chat**"
        embed = discord.Embed(
            title="⚙️ Configuración Actualizada", 
            description=f"Ahora el bot capturará: {texto}",
            color=0x00FF00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="spam_ping", description="Envía un número específico de menciones a un usuario.")
    @app_commands.describe(
        usuario="El usuario al que quieres mencionar", 
        cantidad="Número de veces a enviar el ping (máximo 30000)"
    )
    async def spam_ping(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        limite_maximo = 30000

        if cantidad > limite_maximo:
            embed = discord.Embed(
                title="❌ Límite excedido", 
                description=f"Para evitar que Discord penalice al bot, el máximo de pings permitidos es **{limite_maximo}**.", 
                color=0xFF0000
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        await interaction.response.send_message(
            f"✅ Iniciando el envío de {cantidad} pings a {usuario.display_name}...", 
            ephemeral=True
        )
        logging.info(f"{interaction.user} ha iniciado {cantidad} pings hacia {usuario.name} en #{interaction.channel.name}")

        for _ in range(cantidad):
            try:
                await interaction.channel.send(f"{usuario.mention}")
                await asyncio.sleep(1.5)
            except discord.Forbidden:
                logging.error(f"El bot no tiene permisos para hablar en #{interaction.channel.name}")
                break
            except Exception as e:
                logging.error(f"Error enviando ping: {e}")
                break

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))

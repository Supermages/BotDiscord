import logging
import discord
from discord import app_commands
from discord.ext import commands
from core.permissions import requiere_admin
from core.database import buscar_personaje_por_nombre_db
from ui.views import EditPersonajeView

class CharacterCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="editarpersonaje", description="Edita visualmente las propiedades de un personaje.")
    @app_commands.describe(nombre="Nombre del personaje (no ID)")
    @requiere_admin()
    async def editarpersonaje(self, interaction: discord.Interaction, nombre: str):
        await interaction.response.defer(ephemeral=True)
        personaje = await buscar_personaje_por_nombre_db(nombre)

        if not personaje:
            embed = discord.Embed(
                title="❌ No encontrado",
                description=f"No se encontró el personaje llamado **{nombre}**.",
                color=0xFF0000
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        tupper_tag, nombre_real, lado, avatar_url, color, color_texto = personaje
        view = EditPersonajeView(interaction, tupper_tag, nombre_real, lado, color, color_texto, avatar_url)

        try:
            await view.send_preview()
            embed = discord.Embed(
                title="📩 Edición iniciada",
                description="Revisa tus mensajes privados para continuar con la edición.",
                color=0x00B0F4
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logging.info(f"Vista de edición enviada a {interaction.user.display_name}")
        except discord.Forbidden:
            await interaction.followup.send(
                content="📍 No pude enviarte DM. Aquí tienes la edición.",
                ephemeral=True,
                view=view
            )
            logging.warning(f"No se pudo enviar DM a {interaction.user.display_name}, se usó canal.")

async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterCommands(bot))

import discord
from discord import app_commands
from discord.ext import commands

from core.database import (
    buscar_personaje_por_nombre_db,
    listar_recetas,
    obtener_receta,
    normalizar_texto
)
from services.inventory_service import puede_gestionar_personaje
from services.crafting_service import verificar_y_craftear
from cogs.inventory_commands import autocomplete_mis_personajes_activos
from ui.inventory_views import RecipesView

async def autocomplete_recetas(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    recetas = await listar_recetas()
    curr_norm = normalizar_texto(current)
    filtradas = []
    for r in recetas:
        rid, rnom = r["receta_id"], r["nombre"]
        if not curr_norm or curr_norm in normalizar_texto(rnom) or curr_norm in normalizar_texto(rid):
            filtradas.append(app_commands.Choice(name=f"{r['resultado_emoji']} {rnom}"[:100], value=rid[:100]))
    return filtradas[:25]


class CraftingCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    craft_group = app_commands.Group(name="craft", description="Comandos del sistema de crafteo y recetas")

    @craft_group.command(name="recetas", description="Consulta el catálogo de recetas de crafteo disponibles en el servidor.")
    async def recetas(self, interaction: discord.Interaction):
        await interaction.response.defer()
        todas = await listar_recetas()

        if not todas:
            return await interaction.followup.send("📜 No hay recetas registradas en este momento.", ephemeral=True)

        view = RecipesView(todas, interaction.user.id)
        embed = view.generar_embed()
        await interaction.followup.send(embed=embed, view=view)

    @craft_group.command(name="fabricar", description="Fabrica un objeto utilizando materiales del inventario de tu personaje.")
    @app_commands.describe(
        personaje="Personaje cuyos materiales usarás para fabricar (debe ser tuyo)",
        receta="Fórmula o receta a fabricar",
        cantidad="Cantidad de veces a fabricar la receta"
    )
    @app_commands.autocomplete(personaje=autocomplete_mis_personajes_activos, receta=autocomplete_recetas)
    async def fabricar(self, interaction: discord.Interaction, personaje: str, receta: str, cantidad: int = 1):
        if personaje == "__sin_activos__":
            return await interaction.response.send_message(
                "📭 No tienes ningún personaje activo para fabricar recetas.\n"
                "Usa `/pj panel` o `/pj vincular` para activar un personaje de tu reserva personal primero.",
                ephemeral=True
            )

        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad a fabricar debe ser mayor a 0.", ephemeral=True)

        await interaction.response.defer()

        # 1. Validar personaje
        p_info = await buscar_personaje_por_nombre_db(personaje)
        if not p_info:
            return await interaction.followup.send(f"❌ Personaje '{personaje}' no encontrado.", ephemeral=True)

        # 2. Validar propiedad activa
        puede, motivo = puede_gestionar_personaje(interaction.user, p_info)
        if not puede:
            if motivo == "en_reserva_propia":
                return await interaction.followup.send(
                    f"📦 **{p_info[1]}** está en tu reserva personal pero no está activo.\n"
                    f"Usa `/pj vincular {p_info[1]}` o `/pj panel` para activarlo en tu cupo (hasta 3 personajes) antes de fabricar.",
                    ephemeral=True
                )
            if motivo == "sin_dueño":
                return await interaction.followup.send(
                    f"❌ El personaje **{p_info[1]}** no está vinculado a ningún jugador activo.",
                    ephemeral=True
                )
            return await interaction.followup.send(
                f"⛔ No tienes permiso para usar los materiales de **{p_info[1]}** porque no eres su dueño activo.", 
                ephemeral=True
            )

        # 3. Validar y ejecutar crafteo
        ok, msg, receta_data = await verificar_y_craftear(p_info[0], receta, cantidad)
        if not ok:
            return await interaction.followup.send(msg, ephemeral=True)

        embed = discord.Embed(
            title="🔨 ¡Fabricación Exitosa!",
            description=msg,
            color=0x2ECC71
        )
        embed.set_author(name=p_info[1], icon_url=p_info[3] or "https://cdn.discordapp.com/embed/avatars/0.png")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(CraftingCommands(bot))

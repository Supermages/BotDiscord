import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from services.dice_service import ejecutar_tirada, TiradaResultado
from core.database import buscar_personaje_por_nombre_db
from cogs.inventory_commands import autocomplete_mis_personajes_activos
from services.inventory_service import puede_gestionar_personaje

logger = logging.getLogger(__name__)

def parsear_color_hex(hex_str: Optional[str], default_color: int = 0x5865F2) -> int:
    """Convierte un código hexadecimal (#RRGGBB) a entero para discord.Color."""
    if not hex_str:
        return default_color
    clean = hex_str.strip().replace("#", "")
    try:
        return int(clean, 16)
    except ValueError:
        return default_color

def construir_embed_tirada(
    interaction: discord.Interaction,
    resultado: TiradaResultado,
    motivo: Optional[str] = None,
    personaje_info: Optional[tuple] = None
) -> discord.Embed:
    """Construye un Embed minimalista y compacto para la tirada de dados D&D."""
    
    # 1. Color sutil
    if resultado.es_critico:
        color = 0xF1C40F  # Oro para Nat 20
    elif resultado.es_pifia:
        color = 0xE74C3C  # Rojo para Nat 1
    elif personaje_info and len(personaje_info) >= 5 and personaje_info[4]:
        color = parsear_color_hex(personaje_info[4], 0x5865F2)
    else:
        color = 0x5865F2

    # 2. Título: motivo o fórmula
    if motivo:
        titulo = f"🎲 {motivo.strip()}"
    else:
        titulo = f"🎲 Tirada: `{resultado.formula}`"

    embed = discord.Embed(title=titulo, color=color)

    # 3. Autor minimalista (PJ o Usuario)
    if personaje_info:
        nombre_pj = personaje_info[1]
        avatar_pj = personaje_info[3] if len(personaje_info) >= 4 and personaje_info[3] else None
        embed.set_author(name=f"🛡️ {nombre_pj}", icon_url=avatar_pj)
    else:
        embed.set_author(
            name=f"🎲 {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )

    # 4. Cuerpo compacto
    lineas = []
    tag_modo = ""
    if resultado.modo == "ventaja":
        tag_modo = " `[Ventaja]`"
    elif resultado.modo == "desventaja":
        tag_modo = " `[Desventaja]`"

    lineas.append(f"**Dados:** `{resultado.desglose}`{tag_modo}")

    res_str = f"**Resultado:** **`{resultado.total}`**"
    if resultado.es_critico:
        res_str += " ✨ *(¡Nat 20!)*"
    elif resultado.es_pifia:
        res_str += " 💀 *(¡Nat 1!)*"
    lineas.append(res_str)

    embed.description = "\n".join(lineas)
    return embed

class DiceCommands(commands.Cog):
    """Cog encargado de tiradas de dados estilo D&D."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _procesar_tirada(
        self,
        interaction: discord.Interaction,
        tirada: str,
        modo: str,
        motivo: Optional[str],
        personaje: Optional[str],
        secreto: bool
    ):
        p_info = None
        # Si se seleccionó un personaje
        if personaje and personaje != "__sin_activos__":
            p_info = await buscar_personaje_por_nombre_db(personaje)
            if not p_info:
                return await interaction.response.send_message(
                    f"❌ Personaje '{personaje}' no encontrado.",
                    ephemeral=True
                )
            puede, motivo_rechazo = puede_gestionar_personaje(interaction.user, p_info)
            if not puede:
                if motivo_rechazo == "en_reserva_propia":
                    return await interaction.response.send_message(
                        f"📦 **{p_info[1]}** está en tu reserva personal pero no está activo.\n"
                        f"Usa `/pj vincular {p_info[1]}` o `/pj panel` para activarlo antes de tirar con él.",
                        ephemeral=True
                    )
                return await interaction.response.send_message(
                    f"⛔ No tienes permiso para realizar tiradas con **{p_info[1]}**.",
                    ephemeral=True
                )

        try:
            resultado = ejecutar_tirada(formula=tirada, modo=modo)
        except ValueError as ve:
            return await interaction.response.send_message(
                f"❌ {ve}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error procesando tirada de dados '{tirada}': {e}", exc_info=True)
            return await interaction.response.send_message(
                "❌ Ocurrió un error inesperado al procesar la tirada de dados.",
                ephemeral=True
            )

        embed = construir_embed_tirada(interaction, resultado, motivo=motivo, personaje_info=p_info)
        await interaction.response.send_message(embed=embed, ephemeral=secreto)

    # ---------------------------------------------------------
    # /roll
    # ---------------------------------------------------------
    @app_commands.command(name="roll", description="Lanza dados al estilo D&D (ej: 1d20+2, 2d6, d100).")
    @app_commands.describe(
        tirada="Fórmula de los dados a lanzar (por defecto 1d20, ej: 1d20+2, 2d6+3, d100)",
        modo="Modalidad de la tirada (Normal, con Ventaja o con Desventaja)",
        motivo="Motivo o acción de la tirada (ej: Ataque con arco, Salvación de Destreza, Sigilo)",
        personaje="Personaje activo a cuyo nombre se hace la tirada (opcional)",
        secreto="Si es True, la tirada solo será visible para ti (efímera)"
    )
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="🎲 Normal", value="normal"),
            app_commands.Choice(name="🟢 Ventaja (Mayor de 2 dados)", value="ventaja"),
            app_commands.Choice(name="🔴 Desventaja (Menor de 2 dados)", value="desventaja")
        ]
    )
    @app_commands.autocomplete(personaje=autocomplete_mis_personajes_activos)
    async def roll(
        self,
        interaction: discord.Interaction,
        tirada: str = "1d20",
        modo: str = "normal",
        motivo: Optional[str] = None,
        personaje: Optional[str] = None,
        secreto: bool = False
    ):
        await self._procesar_tirada(interaction, tirada, modo, motivo, personaje, secreto)

    # ---------------------------------------------------------
    # /dado (Alias de /roll)
    # ---------------------------------------------------------
    @app_commands.command(name="dado", description="Lanza dados al estilo D&D (ej: 1d20+2, 2d6, d100).")
    @app_commands.describe(
        tirada="Fórmula de los dados a lanzar (por defecto 1d20, ej: 1d20+2, 2d6+3, d100)",
        modo="Modalidad de la tirada (Normal, con Ventaja o con Desventaja)",
        motivo="Motivo o acción de la tirada (ej: Ataque con arco, Salvación de Destreza, Sigilo)",
        personaje="Personaje activo a cuyo nombre se hace la tirada (opcional)",
        secreto="Si es True, la tirada solo será visible para ti (efímera)"
    )
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="🎲 Normal", value="normal"),
            app_commands.Choice(name="🟢 Ventaja (Mayor de 2 dados)", value="ventaja"),
            app_commands.Choice(name="🔴 Desventaja (Menor de 2 dados)", value="desventaja")
        ]
    )
    @app_commands.autocomplete(personaje=autocomplete_mis_personajes_activos)
    async def dado(
        self,
        interaction: discord.Interaction,
        tirada: str = "1d20",
        modo: str = "normal",
        motivo: Optional[str] = None,
        personaje: Optional[str] = None,
        secreto: bool = False
    ):
        await self._procesar_tirada(interaction, tirada, modo, motivo, personaje, secreto)

async def setup(bot: commands.Bot):
    await bot.add_cog(DiceCommands(bot))

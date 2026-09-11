import discord
from discord import app_commands
from discord.ext import commands

from core.database import (
    buscar_personaje_por_nombre_db,
    listar_todos_personajes,
    obtener_inventario_personaje,
    obtener_personajes_activos,
    obtener_personajes_reserva,
    obtener_item,
    listar_items_catalogo,
    transferir_item_atomico,
    normalizar_texto
)
from services.inventory_service import puede_gestionar_personaje, consumir_item, es_admin
from ui.inventory_views import InventoryView, TransferConfirmView

async def autocomplete_personajes_todos(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocompletado de cualquier personaje registrado usando búsqueda normalizada."""
    todos = await listar_todos_personajes()
    curr_norm = normalizar_texto(current)
    filtrados = []
    for p in todos:
        tag, nombre = p[0], p[1]
        if not curr_norm or curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(tag):
            filtrados.append(app_commands.Choice(name=nombre[:100], value=tag[:100]))
    return filtrados[:25]

async def autocomplete_mis_personajes_activos(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """
    Autocompletado que devuelve EXCLUSIVAMENTE los personajes activos del usuario que ejecuta el comando.
    (Incluso para administradores, para evitar saturación de personajes ajenos).
    """
    activos = await obtener_personajes_activos(str(interaction.user.id))
    curr_norm = normalizar_texto(current)
    filtrados = []
    for p in activos:
        tag, nombre = p["tupper_tag"], p["nombre"]
        if not curr_norm or curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(tag):
            filtrados.append(app_commands.Choice(name=f"🛡️ {nombre}"[:100], value=tag[:100]))
    return filtrados[:25]

async def autocomplete_mis_personajes_reserva(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocompletado que devuelve los personajes en reserva del usuario para activar."""
    reserva = await obtener_personajes_reserva(str(interaction.user.id))
    curr_norm = normalizar_texto(current)
    filtrados = []
    for p in reserva:
        tag, nombre = p["tupper_tag"], p["nombre"]
        if not curr_norm or curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(tag):
            filtrados.append(app_commands.Choice(name=f"📦 {nombre}"[:100], value=tag[:100]))
    return filtrados[:25]

async def autocomplete_items(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocompletado de ítems del catálogo usando búsqueda normalizada."""
    todos = await listar_items_catalogo()
    curr_norm = normalizar_texto(current)
    filtrados = []
    for it in todos:
        iid, nombre, emoji = it["item_id"], it["nombre"], it["emoji"]
        if not curr_norm or curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(iid):
            filtrados.append(app_commands.Choice(name=f"{emoji} {nombre}"[:100], value=iid[:100]))
    return filtrados[:25]


class InventoryCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    inv_group = app_commands.Group(name="inv", description="Comandos del sistema de inventario")

    # ---------------------------------------------------------
    # /inv ver [personaje: opcional]
    # ---------------------------------------------------------
    @inv_group.command(name="ver", description="Muestra el inventario interactivo de un personaje.")
    @app_commands.describe(personaje="Nombre o tag del personaje (opcional si tienes uno activo)")
    @app_commands.autocomplete(personaje=autocomplete_mis_personajes_activos)
    async def ver(self, interaction: discord.Interaction, personaje: str = None):
        await interaction.response.defer()

        target_pj = None
        if not personaje:
            activos = await obtener_personajes_activos(str(interaction.user.id))
            if len(activos) == 1:
                target_pj = activos[0]["tupper_tag"]
            elif len(activos) > 1:
                target_pj = activos[0]["tupper_tag"]
            else:
                return await interaction.followup.send(
                    "📭 No tienes ningún personaje activo. Usa `/pj panel` o `/pj vincular` para activar uno.",
                    ephemeral=True
                )
        else:
            target_pj = personaje

        personaje_info = await buscar_personaje_por_nombre_db(target_pj)
        if not personaje_info:
            return await interaction.followup.send(
                f"❌ Personaje '{target_pj}' no encontrado.",
                ephemeral=True
            )

        tupper_tag = personaje_info[0]
        nombre = personaje_info[1]
        avatar_url = personaje_info[3] or "https://cdn.discordapp.com/embed/avatars/0.png"

        items = await obtener_inventario_personaje(tupper_tag)
        view = InventoryView(interaction, tupper_tag, nombre, avatar_url, items)
        await interaction.followup.send(embed=view.generar_embed(), view=view)

    # ---------------------------------------------------------
    # /inv transferir
    # ---------------------------------------------------------
    @inv_group.command(name="transferir", description="Transfiere objetos entre personajes con confirmación interactiva.")
    @app_commands.describe(
        de_personaje="Personaje origen (debe ser tuyo)",
        a_personaje="Personaje destino",
        item="Objeto a transferir",
        cantidad="Cantidad de unidades"
    )
    @app_commands.autocomplete(
        de_personaje=autocomplete_mis_personajes_activos,
        a_personaje=autocomplete_personajes_todos,
        item=autocomplete_items
    )
    async def transferir(
        self, 
        interaction: discord.Interaction, 
        de_personaje: str, 
        a_personaje: str, 
        item: str, 
        cantidad: int = 1
    ):
        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        if de_personaje.strip().lower() == a_personaje.strip().lower():
            return await interaction.response.send_message("❌ El personaje origen y destino no pueden ser el mismo.", ephemeral=True)

        p_origen = await buscar_personaje_por_nombre_db(de_personaje)
        if not p_origen:
            return await interaction.response.send_message(f"❌ Personaje origen '{de_personaje}' no encontrado.", ephemeral=True)

        p_destino = await buscar_personaje_por_nombre_db(a_personaje)
        if not p_destino:
            return await interaction.response.send_message(f"❌ Personaje destino '{a_personaje}' no encontrado.", ephemeral=True)

        puede, motivo = puede_gestionar_personaje(interaction.user, p_origen)
        if not puede:
            return await interaction.response.send_message(
                f"⛔ No tienes permiso para gestionar a **{p_origen[1]}**. Solo su dueño activo o un admin pueden mover sus ítems.",
                ephemeral=True
            )

        it_data = await obtener_item(item)
        if not it_data:
            return await interaction.response.send_message(f"❌ El ítem '{item}' no existe en el catálogo maestro.", ephemeral=True)

        inv_origen = await obtener_inventario_personaje(p_origen[0])
        stock = 0
        for it in inv_origen:
            if it["item_id"].lower() == it_data["item_id"].lower():
                stock = it["cantidad"]
                break

        if stock < cantidad:
            return await interaction.response.send_message(
                f"❌ Stock insuficiente. **{p_origen[1]}** solo tiene **x{stock}** de {it_data['emoji']} **{it_data['nombre']}**.",
                ephemeral=True
            )

        embed_confirm = discord.Embed(
            title="📦 Confirmación de Transferencia",
            description=(
                f"¿Estás seguro de que deseas realizar la siguiente transferencia?\n\n"
                f"• **De:** 🛡️ **{p_origen[1]}**\n"
                f"• **A:** 🛡️ **{p_destino[1]}**\n"
                f"• **Objeto:** {it_data['emoji']} **{it_data['nombre']}** x{cantidad}\n\n"
                f"*Esta acción deducirá los ítems inmediatamente de la bolsa de {p_origen[1]}.*"
            ),
            color=0xE67E22
        )
        if p_origen[3]:
            embed_confirm.set_thumbnail(url=p_origen[3])

        async def callback_confirmar():
            ok, msg = await transferir_item_atomico(p_origen[0], p_destino[0], it_data["item_id"], cantidad)
            if ok:
                embed_exito = discord.Embed(
                    title="✅ Transferencia Exitosa",
                    description=(
                        f"Se han transferido **x{cantidad}** de {it_data['emoji']} **{it_data['nombre']}** "
                        f"de **{p_origen[1]}** a **{p_destino[1]}**."
                    ),
                    color=0x2ECC71
                )
                await interaction.edit_original_response(embed=embed_exito, view=None)
            else:
                embed_err = discord.Embed(title="❌ Error en la Transferencia", description=msg, color=0xE74C3C)
                await interaction.edit_original_response(embed=embed_err, view=None)

        async def callback_cancelar():
            embed_cancel = discord.Embed(
                title="🚫 Transferencia Cancelada",
                description="La transferencia ha sido cancelada por el usuario. No se ha modificado ningún inventario.",
                color=0x95A5A6
            )
            await interaction.edit_original_response(embed=embed_cancel, view=None)

        view = TransferConfirmView(interaction.user.id, callback_confirmar, callback_cancelar)
        await interaction.response.send_message(embed=embed_confirm, view=view)

    # ---------------------------------------------------------
    # /inv usar
    # ---------------------------------------------------------
    @inv_group.command(name="usar", description="Consume un ítem usable del inventario de tu personaje.")
    @app_commands.describe(
        personaje="Personaje que usará el ítem (debe ser tuyo)",
        item="Ítem a usar",
        cantidad="Cantidad a consumir"
    )
    @app_commands.autocomplete(
        personaje=autocomplete_mis_personajes_activos,
        item=autocomplete_items
    )
    async def usar(self, interaction: discord.Interaction, personaje: str, item: str, cantidad: int = 1):
        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        p_info = await buscar_personaje_por_nombre_db(personaje)
        if not p_info:
            return await interaction.response.send_message(f"❌ Personaje '{personaje}' no encontrado.", ephemeral=True)

        puede, motivo = puede_gestionar_personaje(interaction.user, p_info)
        if not puede:
            return await interaction.response.send_message(f"⛔ No eres el dueño activo de **{p_info[1]}**.", ephemeral=True)

        ok, msg, it_data = await consumir_item(p_info[0], item, cantidad)
        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

        embed = discord.Embed(
            title=f"✨ {p_info[1]} usó {it_data['emoji']} {it_data['nombre']}",
            description=msg,
            color=0x9B59B6
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCommands(bot))

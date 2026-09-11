import discord
from discord import app_commands
from discord.ext import commands

from core.database import (
    buscar_personaje_por_nombre_db,
    listar_todos_personajes,
    obtener_inventario_personaje,
    obtener_personajes_por_owner,
    vincular_owner_personaje,
    obtener_item,
    listar_items_catalogo,
    transferir_item_atomico
)
from services.inventory_service import puede_gestionar_personaje, consumir_item, es_admin
from ui.inventory_views import InventoryView, TransferConfirmView

async def autocomplete_personajes(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocompletado de personajes por nombre."""
    todos = await listar_todos_personajes()
    filtrados = [
        app_commands.Choice(name=p[1], value=p[0])
        for p in todos
        if current.lower() in p[1].lower() or current.lower() in p[0].lower()
    ]
    return filtrados[:25]

async def autocomplete_mis_personajes(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocompletado de personajes que le pertenecen al usuario que ejecuta el comando (o todos si es admin)."""
    if es_admin(interaction.user):
        return await autocomplete_personajes(interaction, current)
    mis = await obtener_personajes_por_owner(str(interaction.user.id))
    filtrados = [
        app_commands.Choice(name=p["nombre"], value=p["tupper_tag"])
        for p in mis
        if current.lower() in p["nombre"].lower() or current.lower() in p["tupper_tag"].lower()
    ]
    return filtrados[:25]

async def autocomplete_items(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocompletado de ítems registrados en el catálogo."""
    todos = await listar_items_catalogo()
    filtrados = [
        app_commands.Choice(name=f"{it['emoji']} {it['nombre']}", value=it["item_id"])
        for it in todos
        if current.lower() in it["nombre"].lower() or current.lower() in it["item_id"].lower()
    ]
    return filtrados[:25]


class InventoryCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="inventario", description="Muestra el inventario interactivo de un personaje.")
    @app_commands.describe(personaje="Nombre o tag del personaje a consultar")
    @app_commands.autocomplete(personaje=autocomplete_personajes)
    async def inventario(self, interaction: discord.Interaction, personaje: str = None):
        await interaction.response.defer()

        # Si no especifica personaje, buscar si el usuario tiene personajes vinculados
        personaje_info = None
        if not personaje:
            mis = await obtener_personajes_por_owner(str(interaction.user.id))
            if mis:
                personaje_info = (
                    mis[0]["tupper_tag"], mis[0]["nombre"], mis[0]["lado"],
                    mis[0]["avatar_url"], mis[0]["color"], mis[0]["color_texto"], mis[0]["owner_id"]
                )
            else:
                return await interaction.followup.send(
                    "⚠️ No especificaste ningún personaje y no tienes ninguno vinculado. "
                    "Usa `/inventario personaje: [Nombre]` o reclama uno con `/vincular_personaje`.",
                    ephemeral=True
                )
        else:
            personaje_info = await buscar_personaje_por_nombre_db(personaje)

        if not personaje_info:
            return await interaction.followup.send(
                f"❌ No se encontró ningún personaje llamado **{personaje}**.", 
                ephemeral=True
            )

        tupper_tag, nombre, _, avatar_url, _, _, owner_id = personaje_info
        items = await obtener_inventario_personaje(tupper_tag)

        view = InventoryView(
            items=items,
            personaje_nombre=nombre,
            avatar_url=avatar_url,
            autor_id=interaction.user.id
        )
        embed = view.generar_embed()
        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg

    @app_commands.command(name="transferir", description="Transfiere un ítem de tu personaje a otro personaje.")
    @app_commands.describe(
        de_personaje="Personaje desde el cual enviarás el ítem (debes ser su dueño)",
        a_personaje="Personaje destinatario que recibirá el ítem",
        item="Ítem a transferir",
        cantidad="Cantidad de unidades a transferir"
    )
    @app_commands.autocomplete(de_personaje=autocomplete_mis_personajes, a_personaje=autocomplete_personajes, item=autocomplete_items)
    async def transferir(self, interaction: discord.Interaction, de_personaje: str, a_personaje: str, item: str, cantidad: int = 1):
        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        # 1. Validar personaje origen
        p_origen = await buscar_personaje_por_nombre_db(de_personaje)
        if not p_origen:
            return await interaction.response.send_message(f"❌ El personaje de origen '{de_personaje}' no existe.", ephemeral=True)

        # 2. Validar permisos de propiedad del personaje origen
        puede, motivo = puede_gestionar_personaje(interaction.user, p_origen)
        if not puede:
            if motivo == "sin_dueño":
                return await interaction.response.send_message(
                    f"⚠️ El personaje **{p_origen[1]}** no tiene dueño registrado. Puedes reclamarlo primero con `/vincular_personaje personaje: {p_origen[1]}`.", 
                    ephemeral=True
                )
            return await interaction.response.send_message(
                f"⛔ No tienes permiso para transferir objetos de **{p_origen[1]}** porque pertenece a otro jugador.", 
                ephemeral=True
            )

        # 3. Validar personaje destino
        p_destino = await buscar_personaje_por_nombre_db(a_personaje)
        if not p_destino:
            return await interaction.response.send_message(f"❌ El personaje de destino '{a_personaje}' no existe.", ephemeral=True)

        if p_origen[0] == p_destino[0]:
            return await interaction.response.send_message("❌ No puedes transferir objetos al mismo personaje.", ephemeral=True)

        # 4. Validar ítem y stock
        item_data = await obtener_item(item)
        nombre_item = item_data["nombre"] if item_data else item
        emoji_item = item_data["emoji"] if item_data else "📦"

        inv_origen = await obtener_inventario_personaje(p_origen[0])
        disponible = 0
        for it in inv_origen:
            if it["item_id"].lower() == item.lower():
                disponible = it["cantidad"]
                break

        if disponible < cantidad:
            return await interaction.response.send_message(
                f"❌ Stock insuficiente. **{p_origen[1]}** solo tiene x{disponible} de {emoji_item} **{nombre_item}**.", 
                ephemeral=True
            )

        # 5. Confirmación interactiva
        view = TransferConfirmView(interaction.user.id)
        embed = discord.Embed(
            title="🔄 Confirmar Transferencia",
            description=(
                f"¿Estás seguro de que deseas realizar la siguiente transferencia?\n\n"
                f"• **De:** {p_origen[1]}\n"
                f"• **Para:** {p_destino[1]}\n"
                f"• **Ítem:** {emoji_item} **{nombre_item}** x{cantidad}\n"
            ),
            color=0xF1C40F
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if view.confirmado:
            ok, msg = await transferir_item_atomico(p_origen[0], p_destino[0], item, cantidad)
            if ok:
                embed_exito = discord.Embed(
                    title="✅ Transferencia Completada",
                    description=f"Se han transferido **x{cantidad}** de {emoji_item} **{nombre_item}** de **{p_origen[1]}** a **{p_destino[1]}**.",
                    color=0x2ECC71
                )
                await interaction.edit_original_response(embed=embed_exito, view=None)
            else:
                await interaction.edit_original_response(content=f"❌ Error en la transferencia: {msg}", embed=None, view=None)

    @app_commands.command(name="usar_item", description="Usa o consume un objeto del inventario de tu personaje.")
    @app_commands.describe(
        personaje="Personaje que usará el ítem",
        item="Ítem a utilizar",
        cantidad="Cantidad de unidades a consumir"
    )
    @app_commands.autocomplete(personaje=autocomplete_mis_personajes, item=autocomplete_items)
    async def usar_item(self, interaction: discord.Interaction, personaje: str, item: str, cantidad: int = 1):
        p_info = await buscar_personaje_por_nombre_db(personaje)
        if not p_info:
            return await interaction.response.send_message(f"❌ Personaje '{personaje}' no encontrado.", ephemeral=True)

        puede, motivo = puede_gestionar_personaje(interaction.user, p_info)
        if not puede:
            return await interaction.response.send_message(f"⛔ No eres el dueño de **{p_info[1]}**.", ephemeral=True)

        ok, msg, it_data = await consumir_item(p_info[0], item, cantidad)
        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

        embed = discord.Embed(
            title=f"✨ {p_info[1]} usó {it_data['emoji']} {it_data['nombre']}",
            description=msg,
            color=0x9B59B6
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="vincular_personaje", description="Reclama la propiedad de un personaje que no tiene dueño registrado.")
    @app_commands.describe(personaje="Personaje a vincular a tu cuenta")
    @app_commands.autocomplete(personaje=autocomplete_personajes)
    async def vincular_personaje(self, interaction: discord.Interaction, personaje: str):
        p_info = await buscar_personaje_por_nombre_db(personaje)
        if not p_info:
            return await interaction.response.send_message(f"❌ Personaje '{personaje}' no encontrado.", ephemeral=True)

        duenio_actual = p_info[6]
        if duenio_actual:
            if str(duenio_actual) == str(interaction.user.id):
                return await interaction.response.send_message(f"ℹ️ **{p_info[1]}** ya está vinculado a tu cuenta.", ephemeral=True)
            return await interaction.response.send_message(
                f"⛔ **{p_info[1]}** ya pertenece a otro usuario (<@{duenio_actual}>). Si crees que es un error, pide ayuda a un Bot Admin.", 
                ephemeral=True
            )

        await vincular_owner_personaje(p_info[0], str(interaction.user.id))
        embed = discord.Embed(
            title="🔗 Personaje Vinculado",
            description=f"¡Has vinculado exitosamente a **{p_info[1]}** a tu cuenta de Discord! Ahora tienes control sobre sus transferencias e inventario.",
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="mis_personajes", description="Muestra los personajes que tienes vinculados a tu cuenta.")
    async def mis_personajes(self, interaction: discord.Interaction):
        mis = await obtener_personajes_por_owner(str(interaction.user.id))
        if not mis:
            return await interaction.response.send_message(
                "📭 No tienes ningún personaje vinculado todavía. Puedes reclamar uno usando `/vincular_personaje`.", 
                ephemeral=True
            )

        nombres = [f"• **{p['nombre']}** (`{p['tupper_tag']}`)" for p in mis]
        embed = discord.Embed(
            title="👤 Tus Personajes Vinculados",
            description="\n".join(nombres),
            color=0x3498DB
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCommands(bot))

import discord
from discord import app_commands
from discord.ext import commands

from core.database import (
    buscar_personaje_por_nombre_db,
    listar_todos_personajes,
    obtener_inventario_personaje,
    obtener_personajes_activos,
    obtener_personajes_reserva,
    obtener_personajes_vinculados_con_owner,
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
    Si el usuario no tiene ningún personaje activo, retorna una opción de aviso guiando a /pj panel o /pj vincular.
    """
    activos = await obtener_personajes_activos(str(interaction.user.id))
    if not activos:
        return [
            app_commands.Choice(
                name="⚠️ Sin personajes activos (Usa /pj panel o /pj vincular)",
                value="__sin_activos__"
            )
        ]

    curr_norm = normalizar_texto(current)
    filtrados = []
    for p in activos:
        tag, nombre = p["tupper_tag"], p["nombre"]
        if not curr_norm or curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(tag):
            filtrados.append(app_commands.Choice(name=f"🛡️ {nombre}"[:100], value=tag[:100]))
    return filtrados[:25]

async def autocomplete_personajes_admin_rpg(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """
    Autocompletado para comandos de administración RPG (item_dar, item_quitar).
    - Muestra prioritariamente personajes activos/vinculados con el nombre de su dueño: '🛡️ {nombre} (@{owner})'.
    - Si el admin escribe texto de búsqueda, busca entre los vinculados y, si queda espacio (< 25),
      permite encontrar personajes no vinculados o de reserva: '📦 {nombre} (Sin vincular)'.
    """
    vinculados = await obtener_personajes_vinculados_con_owner()
    curr_norm = normalizar_texto(current)
    filtrados = []
    guild = interaction.guild

    # 1. Filtrar vinculados primero
    for p in vinculados:
        tag, nombre, owner_id = p["tupper_tag"], p["nombre"], p.get("owner_id")
        owner_label = ""
        if guild and owner_id:
            try:
                member = guild.get_member(int(owner_id))
                if member:
                    owner_label = f"@{member.display_name}"
                else:
                    owner_label = f"ID: {owner_id}"
            except Exception:
                owner_label = f"ID: {owner_id}"
        elif owner_id:
            owner_label = f"ID: {owner_id}"

        label_full = f"🛡️ {nombre} ({owner_label})" if owner_label else f"🛡️ {nombre}"

        if not curr_norm or curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(tag) or (owner_id and curr_norm in str(owner_id)):
            filtrados.append(app_commands.Choice(name=label_full[:100], value=tag[:100]))

    # 2. Si el admin ha escrito un texto de búsqueda y aún hay cupo (< 25), buscar en todos los personajes
    if curr_norm and len(filtrados) < 25:
        tags_ya_incluidos = {p["tupper_tag"] for p in vinculados}
        todos = await listar_todos_personajes()
        for p in todos:
            tag, nombre = p[0], p[1]
            if tag in tags_ya_incluidos:
                continue
            if curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(tag):
                filtrados.append(app_commands.Choice(name=f"📦 {nombre} (Sin vincular)"[:100], value=tag[:100]))
                if len(filtrados) >= 25:
                    break

    return filtrados[:25]

async def autocomplete_mis_personajes_reserva(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocompletado que devuelve los personajes en reserva del usuario para activar."""
    reserva = await obtener_personajes_reserva(str(interaction.user.id))
    if not reserva:
        return [
            app_commands.Choice(
                name="⚠️ Sin personajes en reserva (Usa /pj importar)",
                value="__sin_reserva__"
            )
        ]

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

async def autocomplete_mis_items_usables(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """
    Autocompletado para /inv usar:
    Filtra y muestra exclusivamente ítems que sean consumibles/usables y que
    el personaje seleccionado (o el activo del usuario) tenga en stock en su inventario.
    """
    personaje_nombre = interaction.namespace.personaje
    target_tag = None

    if personaje_nombre and personaje_nombre != "__sin_activos__":
        p_info = await buscar_personaje_por_nombre_db(personaje_nombre)
        if p_info:
            target_tag = p_info[0]

    if not target_tag:
        activos = await obtener_personajes_activos(str(interaction.user.id))
        if activos:
            target_tag = activos[0]["tupper_tag"]

    curr_norm = normalizar_texto(current)
    choices = []

    if target_tag:
        inv = await obtener_inventario_personaje(target_tag)
        for it in inv:
            es_usable = bool(it.get("es_usable")) or bool(it.get("script_id")) or bool(it.get("script_uso"))
            if it.get("cantidad", 0) > 0 and es_usable:
                label = f"{it.get('emoji', '📦')} {it['nombre']} (Stock: x{it['cantidad']})"
                if not curr_norm or curr_norm in normalizar_texto(it["nombre"]) or curr_norm in normalizar_texto(it["item_id"]):
                    choices.append(app_commands.Choice(name=label[:100], value=it["item_id"][:100]))
                if len(choices) >= 25:
                    break

    if not choices:
        todos = await listar_items_catalogo()
        for it in todos:
            es_usable = bool(it.get("es_usable")) or bool(it.get("script_id")) or bool(it.get("script_uso"))
            if es_usable:
                label = f"{it.get('emoji', '📦')} {it['nombre']} (Usable)"
                if not curr_norm or curr_norm in normalizar_texto(it["nombre"]) or curr_norm in normalizar_texto(it["item_id"]):
                    choices.append(app_commands.Choice(name=label[:100], value=it["item_id"][:100]))
                if len(choices) >= 25:
                    break

    return choices



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

        if personaje == "__sin_activos__":
            return await interaction.followup.send(
                "📭 No tienes ningún personaje activo actualmente.\n"
                "• Usa `/pj panel` o `/pj vincular` para activar un personaje de tu reserva.\n"
                "• O escribe el nombre de cualquier personaje para ver su inventario (ej: `/inv ver personaje: Apolo`).",
                ephemeral=True
            )

        target_pj = None
        if not personaje:
            activos = await obtener_personajes_activos(str(interaction.user.id))
            if len(activos) >= 1:
                target_pj = activos[0]["tupper_tag"]
            else:
                return await interaction.followup.send(
                    "📭 No tienes ningún personaje activo actualmente.\n"
                    "• Usa `/pj panel` o `/pj vincular` para activar uno de tu reserva.\n"
                    "• O especifica el nombre en el comando: `/inv ver personaje: <nombre>`.",
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
        owner_id = personaje_info[6] if len(personaje_info) > 6 else None
        creator_id = personaje_info[7] if len(personaje_info) > 7 else None

        if not owner_id:
            if creator_id and str(creator_id) == str(interaction.user.id):
                return await interaction.followup.send(
                    f"📦 **{nombre}** está en tu reserva personal pero no está activo actualmente.\n"
                    f"Usa `/pj vincular {nombre}` o `/pj panel` para activarlo en tu cupo antes de ver su inventario.",
                    ephemeral=True
                )
            return await interaction.followup.send(
                f"❌ El personaje **{nombre}** no está vinculado a ningún jugador activo actualmente (está inactivo o en reserva).",
                ephemeral=True
            )

        items = await obtener_inventario_personaje(tupper_tag)
        view = InventoryView(
            items=items,
            personaje_nombre=nombre,
            avatar_url=avatar_url,
            autor_id=interaction.user.id
        )
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
        a_personaje=autocomplete_personajes_admin_rpg,
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
        if de_personaje == "__sin_activos__":
            return await interaction.response.send_message(
                "📭 No tienes ningún personaje activo desde el cual transferir ítems.\n"
                "Usa `/pj panel` o `/pj vincular` para activar un personaje de tu reserva personal primero.",
                ephemeral=True
            )

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
            if motivo == "en_reserva_propia":
                return await interaction.response.send_message(
                    f"📦 **{p_origen[1]}** está en tu reserva personal pero no está activo.\n"
                    f"Usa `/pj vincular {p_origen[1]}` o `/pj panel` para activarlo en tu cupo (hasta 3 personajes).",
                    ephemeral=True
                )
            if motivo == "sin_dueño":
                return await interaction.response.send_message(
                    f"❌ El personaje origen **{p_origen[1]}** no está vinculado a ningún jugador activo.",
                    ephemeral=True
                )
            return await interaction.response.send_message(
                f"⛔ No tienes permiso para gestionar a **{p_origen[1]}**. Solo su dueño activo o un admin pueden mover sus ítems.",
                ephemeral=True
            )

        owner_dest = p_destino[6] if len(p_destino) > 6 else None
        creator_dest = p_destino[7] if len(p_destino) > 7 else None
        if not owner_dest:
            if creator_dest and str(creator_dest) == str(interaction.user.id):
                return await interaction.response.send_message(
                    f"📦 El personaje destino **{p_destino[1]}** está en tu reserva pero no está activo.\n"
                    f"Usa `/pj vincular {p_destino[1]}` o `/pj panel` para activarlo en tu cupo antes de transferirle objetos.",
                    ephemeral=True
                )
            return await interaction.response.send_message(
                f"❌ El personaje destino **{p_destino[1]}** no está vinculado a ningún jugador activo. Solo se pueden transferir objetos a personajes activos en el rol.",
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
        item=autocomplete_mis_items_usables
    )
    async def usar(self, interaction: discord.Interaction, personaje: str, item: str, cantidad: int = 1):
        if personaje == "__sin_activos__":
            return await interaction.response.send_message(
                "📭 No tienes ningún personaje activo para consumir ítems.\n"
                "Usa `/pj panel` o `/pj vincular` para activar un personaje de tu reserva personal primero.",
                ephemeral=True
            )

        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        p_info = await buscar_personaje_por_nombre_db(personaje)
        if not p_info:
            return await interaction.response.send_message(f"❌ Personaje '{personaje}' no encontrado.", ephemeral=True)

        puede, motivo = puede_gestionar_personaje(interaction.user, p_info)
        if not puede:
            if motivo == "en_reserva_propia":
                return await interaction.response.send_message(
                    f"📦 **{p_info[1]}** está en tu reserva personal pero no está activo.\n"
                    f"Usa `/pj vincular {p_info[1]}` o `/pj panel` para activarlo en tu cupo (hasta 3 personajes) y poder usar sus ítems.",
                    ephemeral=True
                )
            if motivo == "sin_dueño":
                return await interaction.response.send_message(
                    f"❌ El personaje **{p_info[1]}** no está vinculado a ningún jugador activo.",
                    ephemeral=True
                )
            return await interaction.response.send_message(f"⛔ No eres el dueño activo de **{p_info[1]}**.", ephemeral=True)

        ok, msg, it_data, items_mostrados = await consumir_item(
            tupper_tag=p_info[0],
            item_id=item,
            cantidad=cantidad,
            user_id=str(interaction.user.id)
        )
        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

        embed = discord.Embed(
            title=f"✨ {p_info[1]} usó {it_data['emoji']} {it_data['nombre']}",
            description=msg,
            color=0x9B59B6
        )
        if p_info[3]:
            embed.set_author(name=p_info[1], icon_url=p_info[3])

        # Si el script ejecutó display_item(), añadir tarjeta visual
        for d_it in items_mostrados:
            desc = f"*{d_it.get('descripcion') or 'Sin descripción'}*"
            embed.add_field(
                name=f"🎁 Obtenido: {d_it.get('emoji', '📦')} {d_it.get('nombre')}",
                value=f"• Categoría: `{d_it.get('categoria', 'Otros')}`\n{desc}",
                inline=False
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCommands(bot))

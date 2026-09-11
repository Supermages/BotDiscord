import re
import discord
from discord import app_commands
from discord.ext import commands

from core.permissions import requiere_admin
from core.database import (
    crear_o_actualizar_item,
    eliminar_item_catalogo,
    obtener_item,
    buscar_personaje_por_nombre_db,
    modificar_cantidad_inventario,
    crear_receta,
    eliminar_receta,
    vincular_owner_personaje,
    listar_items_catalogo,
    establecer_limite_personajes,
    obtener_limite_personajes
)
from cogs.inventory_commands import (
    autocomplete_personajes_todos, 
    autocomplete_personajes_admin_rpg, 
    autocomplete_items
)
from cogs.crafting_commands import autocomplete_recetas

class AdminRPGCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    admin_rpg_group = app_commands.Group(name="admin_rpg", description="Comandos de administración del sistema RPG")

    # ---------------------------------------------------------
    # /admin_rpg item_crear
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="item_crear", description="Crea o actualiza un ítem en el catálogo maestro.")
    @app_commands.describe(
        id="Identificador único (slug sin espacios, ej: pocion_leve, ticket_arma_s)",
        nombre="Nombre mostrado del objeto",
        emoji="Emoji o icono identificativo (ej: 🧪, 🎟️, ⚔️)",
        categoria="Categoría del objeto (Consumible, Material, Arma, Ticket, Especial)",
        descripcion="Descripción breve del objeto",
        es_usable="¿Se puede consumir directamente con /inv usar?",
        mensaje_uso="Mensaje mostrado al consumirlo (opcional)"
    )
    @app_commands.choices(categoria=[
        app_commands.Choice(name="🧪 Consumible", value="Consumible"),
        app_commands.Choice(name="🌿 Material", value="Material"),
        app_commands.Choice(name="⚔️ Arma / Equipo", value="Arma"),
        app_commands.Choice(name="🎟️ Ticket", value="Ticket"),
        app_commands.Choice(name="⭐ Especial", value="Especial")
    ])
    @requiere_admin()
    async def item_crear(
        self, 
        interaction: discord.Interaction, 
        id: str, 
        nombre: str, 
        emoji: str = "📦", 
        categoria: app_commands.Choice[str] = None, 
        descripcion: str = "", 
        es_usable: bool = False, 
        mensaje_uso: str = ""
    ):
        cat_str = categoria.value if categoria else "Material"
        clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', id.strip().lower())

        await crear_o_actualizar_item(
            item_id=clean_id,
            nombre=nombre,
            emoji=emoji,
            categoria=cat_str,
            descripcion=descripcion,
            es_usable=1 if es_usable else 0,
            mensaje_uso=mensaje_uso
        )

        embed = discord.Embed(
            title="📦 Ítem Registrado en Catálogo",
            description=(
                f"• **ID:** `{clean_id}`\n"
                f"• **Nombre:** {emoji} **{nombre}**\n"
                f"• **Categoría:** `{cat_str}`\n"
                f"• **Es Usable:** {'Sí' if es_usable else 'No'}\n"
                f"• **Descripción:** *{descripcion or 'Sin descripción'}*"
            ),
            color=0x2ECC71
        )
        if mensaje_uso:
            embed.add_field(name="Mensaje de Uso", value=f"> {mensaje_uso}", inline=False)

        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------
    # /admin_rpg item_dar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="item_dar", description="Entrega objetos al inventario de un personaje.")
    @app_commands.describe(
        personaje="Personaje destinatario",
        item="Ítem a entregar",
        cantidad="Cantidad de unidades a añadir"
    )
    @app_commands.autocomplete(personaje=autocomplete_personajes_admin_rpg, item=autocomplete_items)
    @requiere_admin()
    async def item_dar(self, interaction: discord.Interaction, personaje: str, item: str, cantidad: int = 1):
        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        p_info = await buscar_personaje_por_nombre_db(personaje)
        if not p_info:
            return await interaction.response.send_message(f"❌ Personaje '{personaje}' no encontrado.", ephemeral=True)

        it_data = await obtener_item(item)
        nombre_it = it_data["nombre"] if it_data else item
        emoji_it = it_data["emoji"] if it_data else "📦"

        nueva_cantidad = await modificar_cantidad_inventario(p_info[0], item, cantidad)

        embed = discord.Embed(
            title="🎁 Entrega de Ítems Realizada",
            description=f"Se han entregado **x{cantidad}** de {emoji_it} **{nombre_it}** a **{p_info[1]}**.\nTotal actual en bolsa: **x{nueva_cantidad}**.",
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------
    # /admin_rpg item_quitar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="item_quitar", description="Retira objetos del inventario de un personaje.")
    @app_commands.describe(
        personaje="Personaje al que quitar el ítem",
        item="Ítem a retirar",
        cantidad="Cantidad de unidades a restar"
    )
    @app_commands.autocomplete(personaje=autocomplete_personajes_admin_rpg, item=autocomplete_items)
    @requiere_admin()
    async def item_quitar(self, interaction: discord.Interaction, personaje: str, item: str, cantidad: int = 1):
        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        p_info = await buscar_personaje_por_nombre_db(personaje)
        if not p_info:
            return await interaction.response.send_message(f"❌ Personaje '{personaje}' no encontrado.", ephemeral=True)

        it_data = await obtener_item(item)
        nombre_it = it_data["nombre"] if it_data else item
        emoji_it = it_data["emoji"] if it_data else "📦"

        nueva_cantidad = await modificar_cantidad_inventario(p_info[0], item, -cantidad)

        embed = discord.Embed(
            title="🗑️ Retirada de Ítems Realizada",
            description=f"Se han retirado **x{cantidad}** de {emoji_it} **{nombre_it}** a **{p_info[1]}**.\nTotal restante en bolsa: **x{nueva_cantidad}**.",
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------
    # /admin_rpg receta_crear
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="receta_crear", description="Crea una receta de crafteo. Ingredientes en formato 'id:cant,id2:cant'.")
    @app_commands.describe(
        id="Identificador único de la receta (ej: pocion_media)",
        nombre="Nombre de la receta",
        resultado_item="Ítem que produce la receta",
        resultado_cantidad="Cantidad producida por crafteo",
        ingredientes_texto="Ingredientes y cantidades requeridas (ej: espada_hierro:1,lingote_hierro:2)",
        descripcion="Descripción o notas de la receta"
    )
    @app_commands.autocomplete(resultado_item=autocomplete_items)
    @requiere_admin()
    async def receta_crear(
        self, 
        interaction: discord.Interaction, 
        id: str, 
        nombre: str, 
        resultado_item: str, 
        ingredientes_texto: str, 
        resultado_cantidad: int = 1, 
        descripcion: str = ""
    ):
        if resultado_cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad de resultado debe ser mayor a 0.", ephemeral=True)

        ingredientes = {}
        partes = [p.strip() for p in ingredientes_texto.split(",") if p.strip()]

        if not partes:
            return await interaction.response.send_message(
                "❌ Debes indicar al menos un ingrediente en formato `item_id:cantidad` (ej: `espada:1,hierro:2`).", 
                ephemeral=True
            )

        for p in partes:
            if ":" not in p:
                return await interaction.response.send_message(f"❌ Formato inválido en '{p}'. Debe ser `id:cantidad`.", ephemeral=True)
            sub_id, sub_cant = p.split(":", 1)
            try:
                cant_int = int(sub_cant.strip())
                if cant_int <= 0:
                    raise ValueError()
                ingredientes[sub_id.strip().lower()] = cant_int
            except ValueError:
                return await interaction.response.send_message(f"❌ Cantidad inválida en '{p}'. Debe ser un número positivo.", ephemeral=True)

        clean_resultado = resultado_item.strip().lower()

        # Validación especial: el ítem puede ser ingrediente de sí mismo (upgrade), pero no el único
        if clean_resultado in ingredientes and len(ingredientes) == 1:
            return await interaction.response.send_message(
                f"❌ La receta no puede requerir únicamente el mismo ítem que produce (`{clean_resultado}`). "
                "Debe incluir materiales adicionales para su mejora o transformación.",
                ephemeral=True
            )

        clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', id.strip().lower())
        await crear_receta(
            receta_id=clean_id,
            nombre=nombre,
            resultado_item_id=resultado_item,
            resultado_cantidad=resultado_cantidad,
            ingredientes=ingredientes,
            descripcion=descripcion
        )

        ings_desc = "\n".join([f"• `{k}` x{v}" for k, v in ingredientes.items()])
        embed = discord.Embed(
            title="📜 Receta Registrada con Éxito",
            description=(
                f"• **ID:** `{clean_id}`\n"
                f"• **Nombre:** **{nombre}**\n"
                f"• **Resultado:** `{resultado_item}` x{resultado_cantidad}\n\n"
                f"**Ingredientes Requeridos:**\n{ings_desc}"
            ),
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------
    # /admin_rpg receta_borrar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="receta_borrar", description="Elimina una receta del catálogo.")
    @app_commands.describe(receta="ID de la receta a eliminar")
    @app_commands.autocomplete(receta=autocomplete_recetas)
    @requiere_admin()
    async def receta_borrar(self, interaction: discord.Interaction, receta: str):
        ok = await eliminar_receta(receta)
        if ok:
            await interaction.response.send_message(f"🗑️ Receta `{receta}` eliminada del catálogo.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ No se encontró la receta `{receta}`.", ephemeral=True)

    # ---------------------------------------------------------
    # /admin_rpg vincular_admin
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="vincular_admin", description="Asigna o cambia forzosamente el dueño de un personaje.")
    @app_commands.describe(
        personaje="Personaje a vincular",
        usuario="Nuevo usuario dueño del personaje"
    )
    @app_commands.autocomplete(personaje=autocomplete_personajes_todos)
    @requiere_admin()
    async def vincular_admin(self, interaction: discord.Interaction, personaje: str, usuario: discord.Member):
        p_info = await buscar_personaje_por_nombre_db(personaje)
        if not p_info:
            return await interaction.response.send_message(f"❌ Personaje '{personaje}' no encontrado.", ephemeral=True)

        await vincular_owner_personaje(p_info[0], str(usuario.id))
        embed = discord.Embed(
            title="👑 Reasignación de Personaje",
            description=f"El personaje **{p_info[1]}** ha sido asignado al usuario {usuario.mention}.",
            color=0x9B59B6
        )
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------
    # /admin_rpg limite_personajes
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="limite_personajes", description="Configura el cupo máximo de personajes activos por usuario.")
    @app_commands.describe(cantidad="Número máximo de personajes activos (ej: 3, 5)")
    @requiere_admin()
    async def limite_personajes(self, interaction: discord.Interaction, cantidad: int):
        if cantidad <= 0 or cantidad > 25:
            return await interaction.response.send_message("❌ El límite debe estar entre 1 y 25.", ephemeral=True)

        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        await establecer_limite_personajes(guild_id, cantidad)
        embed = discord.Embed(
            title="⚙️ Límite de Personajes Actualizado",
            description=f"El límite de personajes activos por usuario en este servidor se ha fijado en **{cantidad}**.",
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminRPGCommands(bot))

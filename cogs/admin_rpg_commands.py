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
    obtener_limite_personajes,
    actualizar_script_item,
    editar_item_catalogo,
    crear_o_actualizar_script,
    obtener_script,
    listar_scripts,
    eliminar_script,
    asignar_script_item
)
from cogs.inventory_commands import (
    autocomplete_personajes_todos, 
    autocomplete_personajes_admin_rpg, 
    autocomplete_items
)
from cogs.crafting_commands import autocomplete_recetas
from services.lua_service import lua_engine
from services.hot_reload_service import hot_reload_manager

async def autocomplete_scripts(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    scripts = await listar_scripts()
    cur = current.strip().lower()
    choices = []
    for s in scripts:
        label = f"📜 {s['nombre']} ({s['script_id']})"
        if not cur or cur in s['nombre'].lower() or cur in s['script_id'].lower():
            choices.append(app_commands.Choice(name=label[:100], value=s['script_id']))
        if len(choices) >= 25:
            break
    return choices

async def autocomplete_scripts_asignar(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    scripts = await listar_scripts()
    cur = current.strip().lower()
    choices = []
    if not cur or any(w in cur for w in ("ningun", "desasig", "quit", "quitar", "borr")):
        choices.append(app_commands.Choice(name="❌ Desasignar / Ninguno", value="ninguno"))
    for s in scripts:
        label = f"📜 {s['nombre']} ({s['script_id']})"
        if not cur or cur in s['nombre'].lower() or cur in s['script_id'].lower():
            choices.append(app_commands.Choice(name=label[:100], value=s['script_id']))
        if len(choices) >= 25:
            break
    return choices

async def autocomplete_cogs_recargables(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    curr_norm = current.lower().strip()
    choices = [app_commands.Choice(name="🔄 Todos los Cogs y Módulos", value="todos")]
    bot = interaction.client
    for ext in list(bot.extensions.keys()):
        short_name = ext.replace("cogs.", "")
        display = f"📦 {short_name} ({ext})"
        if not curr_norm or curr_norm in short_name.lower() or curr_norm in ext.lower():
            choices.append(app_commands.Choice(name=display[:100], value=ext[:100]))
            if len(choices) >= 25:
                break
    return choices

class SharedScriptModal(discord.ui.Modal):
    def __init__(self, script_id: str, nombre: str, descripcion: str = "", current_codigo: str = "", es_nuevo: bool = False):
        super().__init__(title=f"Script: {nombre[:35]}")
        self.script_id = script_id
        self.nombre = nombre
        self.descripcion = descripcion
        self.es_nuevo = es_nuevo

        self.codigo_input = discord.ui.TextInput(
            label="Código Lua Compartido",
            style=discord.TextStyle.paragraph,
            placeholder="-- Escribe aquí la plantilla Lua reutilizable...\nreply('¡Has consumido ' .. item .. '!')",
            default=current_codigo or "",
            required=True,
            max_length=4000
        )
        self.add_item(self.codigo_input)

    async def on_submit(self, interaction: discord.Interaction):
        codigo = self.codigo_input.value.strip()
        valido, msg_val = lua_engine.validar_sintaxis(codigo)
        if not valido:
            embed = discord.Embed(
                title="❌ Error de Sintaxis Lua",
                description=f"El script compartido **{self.nombre}** contiene errores y no se ha guardado:\n```text\n{msg_val}\n```",
                color=0xE74C3C
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await crear_o_actualizar_script(self.script_id, self.nombre, self.descripcion, codigo)
        embed = discord.Embed(
            title="📜 Script Compartido Guardado" if not self.es_nuevo else "✨ Script Compartido Creado",
            description=(
                f"• **ID:** `{self.script_id}`\n"
                f"• **Nombre:** **{self.nombre}**\n"
                f"• **Descripción:** *{self.descripcion or 'Sin descripción'}*"
            ),
            color=0x2ECC71
        )
        preview = codigo[:800] + ("..." if len(codigo) > 800 else "")
        embed.add_field(name="Vista Previa", value=f"```lua\n{preview}\n```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ItemEditarModal(discord.ui.Modal):
    def __init__(self, item_data: dict):
        super().__init__(title=f"Editar: {item_data.get('nombre', '')[:35]}")
        self.item_id = item_data["item_id"]

        self.input_nombre = discord.ui.TextInput(
            label="Nombre visible",
            default=item_data.get("nombre", ""),
            max_length=100,
            required=True
        )
        self.input_emoji = discord.ui.TextInput(
            label="Emoji / Icono",
            default=item_data.get("emoji", "📦"),
            max_length=20,
            required=True
        )
        self.input_categoria = discord.ui.TextInput(
            label="Categoría (Consumible/Material/Arma...)",
            default=item_data.get("categoria", "Material"),
            max_length=50,
            required=True
        )
        self.input_descripcion = discord.ui.TextInput(
            label="Descripción",
            style=discord.TextStyle.paragraph,
            default=item_data.get("descripcion", ""),
            required=False,
            max_length=1000
        )
        self.input_mensaje_uso = discord.ui.TextInput(
            label="Mensaje al consumirlo (/inv usar)",
            style=discord.TextStyle.paragraph,
            default=item_data.get("mensaje_uso", ""),
            required=False,
            max_length=1000
        )

        self.add_item(self.input_nombre)
        self.add_item(self.input_emoji)
        self.add_item(self.input_categoria)
        self.add_item(self.input_descripcion)
        self.add_item(self.input_mensaje_uso)

    async def on_submit(self, interaction: discord.Interaction):
        cat_val = self.input_categoria.value.strip() or "Material"
        cat_val = cat_val.capitalize()

        ok, msg, item_up = await editar_item_catalogo(
            item_id=self.item_id,
            nombre=self.input_nombre.value.strip(),
            emoji=self.input_emoji.value.strip() or "📦",
            categoria=cat_val,
            descripcion=self.input_descripcion.value.strip(),
            mensaje_uso=self.input_mensaje_uso.value.strip()
        )

        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

        embed = discord.Embed(
            title="✏️ Ítem Modificado con Éxito",
            description=(
                f"• **ID:** `{item_up['item_id']}`\n"
                f"• **Nombre:** {item_up['emoji']} **{item_up['nombre']}**\n"
                f"• **Categoría:** `{item_up['categoria']}`\n"
                f"• **Es Usable:** {'Sí' if item_up['es_usable'] else 'No'}\n"
                f"• **Descripción:** *{item_up['descripcion'] or 'Sin descripción'}*"
            ),
            color=0x3498DB
        )
        if item_up.get("mensaje_uso"):
            embed.add_field(name="Mensaje de Uso", value=f"> {item_up['mensaje_uso']}", inline=False)

        await interaction.response.send_message(embed=embed)

class ItemScriptModal(discord.ui.Modal):
    def __init__(self, item_id: str, item_nombre: str, current_script: str = ""):
        super().__init__(title=f"Script: {item_nombre[:35]}")
        self.item_id = item_id
        self.item_nombre = item_nombre
        self.script_input = discord.ui.TextInput(
            label="Código Lua de Uso",
            style=discord.TextStyle.paragraph,
            placeholder="-- Ingrese el código Lua aquí...\nreply('¡Has usado ' .. item .. '!')",
            default=current_script or "",
            required=False,
            max_length=4000
        )
        self.add_item(self.script_input)

    async def on_submit(self, interaction: discord.Interaction):
        codigo = self.script_input.value.strip()
        if not codigo:
            # Eliminar script
            await actualizar_script_item(self.item_id, "")
            embed = discord.Embed(
                title="📜 Script Eliminado",
                description=f"Se ha eliminado el script personalizado del ítem **{self.item_nombre}** (`{self.item_id}`). Volverá a usar la lógica de consumo estándar.",
                color=0xE67E22
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Validar sintaxis Lua
        valido, msg_validacion = lua_engine.validar_sintaxis(codigo)
        if not valido:
            embed = discord.Embed(
                title="❌ Error de Sintaxis Lua",
                description=(
                    f"El script para **{self.item_nombre}** contiene errores de sintaxis y no se ha guardado:\n"
                    f"```text\n{msg_validacion}\n```"
                ),
                color=0xE74C3C
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Guardar en base de datos
        await actualizar_script_item(self.item_id, codigo)
        embed = discord.Embed(
            title="✅ Script Lua Guardado",
            description=f"El script de uso para el ítem **{self.item_nombre}** (`{self.item_id}`) ha sido validado y guardado correctamente.",
            color=0x2ECC71
        )
        preview = codigo[:800] + ("..." if len(codigo) > 800 else "")
        embed.add_field(name="Vista Previa", value=f"```lua\n{preview}\n```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class AdminRPGCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    admin_rpg_group = app_commands.Group(
        name="admin_rpg", 
        description="Comandos de administración del sistema RPG",
        default_permissions=discord.Permissions(administrator=True)
    )

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
    # /admin_rpg item_editar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="item_editar", description="Modifica las propiedades de un ítem existente en el catálogo.")
    @app_commands.describe(
        item="Ítem a editar",
        nombre="Nuevo nombre visible (dejar vacío para no cambiar o para abrir ventana modal)",
        emoji="Nuevo emoji o icono (ej: 🧪, ⚔️)",
        categoria="Nueva categoría del objeto",
        descripcion="Nueva descripción del objeto",
        es_usable="¿Se puede consumir directamente con /inv usar?",
        mensaje_uso="Nuevo mensaje mostrado al consumirlo",
        nuevo_id="Nuevo identificador slug (opcional, actualiza inventarios y recetas)"
    )
    @app_commands.choices(categoria=[
        app_commands.Choice(name="🧪 Consumible", value="Consumible"),
        app_commands.Choice(name="🌿 Material", value="Material"),
        app_commands.Choice(name="⚔️ Arma / Equipo", value="Arma"),
        app_commands.Choice(name="🎟️ Ticket", value="Ticket"),
        app_commands.Choice(name="⭐ Especial", value="Especial")
    ])
    @app_commands.autocomplete(item=autocomplete_items)
    @requiere_admin()
    async def item_editar(
        self,
        interaction: discord.Interaction,
        item: str,
        nombre: str = None,
        emoji: str = None,
        categoria: app_commands.Choice[str] = None,
        descripcion: str = None,
        es_usable: bool = None,
        mensaje_uso: str = None,
        nuevo_id: str = None
    ):
        it_data = await obtener_item(item)
        if not it_data:
            return await interaction.response.send_message(f"❌ Ítem '{item}' no encontrado en el catálogo.", ephemeral=True)

        # Si no se envió ningún parámetro opcional en el comando, abrir ventana Modal interactiva
        if (
            nombre is None and 
            emoji is None and 
            categoria is None and 
            descripcion is None and 
            es_usable is None and 
            mensaje_uso is None and 
            nuevo_id is None
        ):
            modal = ItemEditarModal(it_data)
            return await interaction.response.send_modal(modal)

        # Si se enviaron parámetros específicos en el comando, aplicar directamente
        cat_str = categoria.value if categoria else None
        usable_val = (1 if es_usable else 0) if es_usable is not None else None

        ok, msg, item_up = await editar_item_catalogo(
            item_id=it_data["item_id"],
            nuevo_id=nuevo_id,
            nombre=nombre,
            emoji=emoji,
            categoria=cat_str,
            descripcion=descripcion,
            es_usable=usable_val,
            mensaje_uso=mensaje_uso
        )

        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

        embed = discord.Embed(
            title="✏️ Ítem Modificado con Éxito",
            description=(
                f"• **ID:** `{item_up['item_id']}`\n"
                f"• **Nombre:** {item_up['emoji']} **{item_up['nombre']}**\n"
                f"• **Categoría:** `{item_up['categoria']}`\n"
                f"• **Es Usable:** {'Sí' if item_up['es_usable'] else 'No'}\n"
                f"• **Descripción:** *{item_up['descripcion'] or 'Sin descripción'}*"
            ),
            color=0x3498DB
        )
        if item_up.get("mensaje_uso"):
            embed.add_field(name="Mensaje de Uso", value=f"> {item_up['mensaje_uso']}", inline=False)

        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------
    # /admin_rpg item_borrar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="item_borrar", description="Elimina un ítem del catálogo maestro.")
    @app_commands.describe(item="Ítem a eliminar")
    @app_commands.autocomplete(item=autocomplete_items)
    @requiere_admin()
    async def item_borrar(self, interaction: discord.Interaction, item: str):
        it_data = await obtener_item(item)
        if not it_data:
            return await interaction.response.send_message(f"❌ Ítem '{item}' no encontrado en el catálogo.", ephemeral=True)

        ok = await eliminar_item_catalogo(it_data["item_id"])
        if ok:
            embed = discord.Embed(
                title="🗑️ Ítem Eliminado del Catálogo",
                description=f"El ítem {it_data.get('emoji', '📦')} **{it_data['nombre']}** (`{it_data['item_id']}`) ha sido eliminado del catálogo.",
                color=0xE74C3C
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"❌ No se pudo eliminar el ítem `{item}`.", ephemeral=True)

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

    # ---------------------------------------------------------
    # /admin_rpg item_script
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="item_script", description="Abre un editor para programar el script Lua de uso de un ítem.")
    @app_commands.describe(item="Ítem al que editar o asignar el script Lua")
    @app_commands.autocomplete(item=autocomplete_items)
    @requiere_admin()
    async def item_script(self, interaction: discord.Interaction, item: str):
        it_data = await obtener_item(item)
        if not it_data:
            return await interaction.response.send_message(f"❌ Ítem '{item}' no encontrado en el catálogo.", ephemeral=True)

        current_script = it_data.get("script_uso") or ""
        modal = ItemScriptModal(it_data["item_id"], it_data["nombre"], current_script)
        await interaction.response.send_modal(modal)

    # ---------------------------------------------------------
    # /admin_rpg script_probar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="script_probar", description="Prueba la ejecución de un script Lua de un ítem con un personaje.")
    @app_commands.describe(
        item="Ítem con script a probar",
        personaje="Personaje sobre el que ejecutar la prueba",
        cantidad="Cantidad de ítems a simular en el uso"
    )
    @app_commands.autocomplete(item=autocomplete_items, personaje=autocomplete_personajes_admin_rpg)
    @requiere_admin()
    async def script_probar(self, interaction: discord.Interaction, item: str, personaje: str, cantidad: int = 1):
        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        it_data = await obtener_item(item)
        if not it_data:
            return await interaction.response.send_message(f"❌ Ítem '{item}' no encontrado.", ephemeral=True)

        # Resolver script (específico o compartido)
        script_especifico = (it_data.get("script_uso") or "").strip()
        shared_id = it_data.get("script_id")
        shared_data = await obtener_script(shared_id) if shared_id else None

        script = script_especifico
        origen_str = "Específico del Ítem"
        if not script and shared_data and shared_data.get("codigo"):
            script = shared_data["codigo"].strip()
            origen_str = f"Compartido: {shared_data['nombre']}"

        if not script:
            return await interaction.response.send_message(f"⚠️ El ítem **{it_data['nombre']}** (`{it_data['item_id']}`) no tiene ningún script (ni específico ni compartido).", ephemeral=True)

        p_info = await buscar_personaje_por_nombre_db(personaje)
        if not p_info:
            return await interaction.response.send_message(f"❌ Personaje '{personaje}' no encontrado.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        ok, msg_resultado, items_mostrados = lua_engine.ejecutar_script(
            script=script,
            char_input=p_info[1],
            item_input=it_data["item_id"],
            cantidad=cantidad,
            user_id=str(interaction.user.id)
        )

        embed = discord.Embed(
            title=f"🧪 Prueba de Script: {it_data.get('emoji', '📦')} {it_data['nombre']}",
            description=f"**Personaje:** {p_info[1]} | **Cantidad simulada:** {cantidad}\n**Origen:** `{origen_str}`\n**Resultado:** {'✅ Éxito' if ok else '❌ Fallo / Abortado'}",
            color=0x2ECC71 if ok else 0xE74C3C
        )
        embed.add_field(name="Salida (reply)", value=msg_resultado[:1024] or "*Sin salida*", inline=False)
        if items_mostrados:
            embed.add_field(name="Ítems Mostrados (display_item)", value=", ".join([f"`{i}`" for i in items_mostrados]), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # /admin_rpg item_info
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="item_info", description="Muestra la información técnica detallada y los scripts de un ítem.")
    @app_commands.describe(item="Ítem a inspeccionar")
    @app_commands.autocomplete(item=autocomplete_items)
    @requiere_admin()
    async def item_info(self, interaction: discord.Interaction, item: str):
        it_data = await obtener_item(item)
        if not it_data:
            return await interaction.response.send_message(f"❌ Ítem '{item}' no encontrado.", ephemeral=True)

        embed = discord.Embed(
            title=f"{it_data.get('emoji', '📦')} {it_data.get('nombre', item)}",
            description=it_data.get("descripcion") or "*Sin descripción.*",
            color=0x3498DB
        )
        embed.add_field(name="ID Catálogo", value=f"`{it_data['item_id']}`", inline=True)
        embed.add_field(name="Categoría", value=f"`{it_data.get('categoria', 'Material')}`", inline=True)
        embed.add_field(name="Es Usable", value="✅ Sí" if it_data.get("es_usable") else "❌ No", inline=True)
        if it_data.get("mensaje_uso"):
            embed.add_field(name="Mensaje de Uso", value=f"> {it_data['mensaje_uso']}", inline=False)

        # Estado de scripts
        script_especifico = (it_data.get("script_uso") or "").strip()
        shared_id = it_data.get("script_id")
        shared_data = await obtener_script(shared_id) if shared_id else None

        info_script = []
        if script_especifico:
            info_script.append(f"⭐ **Script Específico (Prioritario):** Activo ({len(script_especifico)} caracteres)")
        if shared_data:
            info_script.append(f"🔗 **Script Compartido:** 📜 **{shared_data['nombre']}** (`{shared_data['script_id']}`)")
        if not script_especifico and not shared_data:
            info_script.append("❌ *Ninguno (consumo estándar)*")

        embed.add_field(name="Configuración de Scripts", value="\n".join(info_script), inline=False)

        # Mostrar preview del script que realmente se ejecutaría
        script_activo = script_especifico or (shared_data.get("codigo") if shared_data else "")
        if script_activo:
            origen = "Específico del Ítem" if script_especifico else f"Compartido: {shared_data['nombre']}"
            preview = script_activo if len(script_activo) <= 900 else script_activo[:900] + "\n-- [Truncado...]"
            embed.add_field(name=f"Código Activo ({origen})", value=f"```lua\n{preview}\n```", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # /admin_rpg item_asignar_script
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="item_asignar_script", description="Asigna o desvincula un script compartido de la biblioteca a un ítem.")
    @app_commands.describe(
        item="Ítem al que asignar el script",
        script="Script compartido a vincular (o elegir 'Desasignar')"
    )
    @app_commands.autocomplete(item=autocomplete_items, script=autocomplete_scripts_asignar)
    @requiere_admin()
    async def item_asignar_script(self, interaction: discord.Interaction, item: str, script: str):
        it_data = await obtener_item(item)
        if not it_data:
            return await interaction.response.send_message(f"❌ Ítem '{item}' no encontrado en el catálogo.", ephemeral=True)

        sid = None if script.strip().lower() in ("ninguno", "none", "") else script.strip().lower()
        if sid:
            s_data = await obtener_script(sid)
            if not s_data:
                return await interaction.response.send_message(f"❌ El script compartido '{script}' no existe en la biblioteca.", ephemeral=True)
            ok, msg = await asignar_script_item(it_data["item_id"], s_data["script_id"])
            if ok:
                embed = discord.Embed(
                    title="🔗 Script Compartido Asignado",
                    description=(
                        f"Se ha asignado el script compartido 📜 **{s_data['nombre']}** (`{s_data['script_id']}`) "
                        f"al ítem {it_data.get('emoji', '📦')} **{it_data['nombre']}** (`{it_data['item_id']}`)."
                    ),
                    color=0x2ECC71
                )
                if it_data.get("script_uso"):
                    embed.add_field(
                        name="⚠️ Aviso de Prioridad",
                        value="Este ítem también tiene un script específico propio configurado. El script específico tendrá prioridad sobre el script compartido salvo que lo vacíes.",
                        inline=False
                    )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        else:
            ok, msg = await asignar_script_item(it_data["item_id"], None)
            embed = discord.Embed(
                title="🔓 Script Desasignado",
                description=f"Se ha retirado el script compartido del ítem {it_data.get('emoji', '📦')} **{it_data['nombre']}**.",
                color=0xE67E22
            )
            await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------
    # /admin_rpg script_crear
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="script_crear", description="Crea un script Lua compartido en la biblioteca reutilizable.")
    @app_commands.describe(
        id="Identificador único del script (slug sin espacios, ej: pocion_base, cofre_gacha)",
        nombre="Nombre representativo del script",
        descripcion="Descripción breve de lo que hace el script (opcional)"
    )
    @requiere_admin()
    async def script_crear(self, interaction: discord.Interaction, id: str, nombre: str, descripcion: str = ""):
        clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', id.strip().lower())
        existente = await obtener_script(clean_id)
        if existente:
            return await interaction.response.send_message(f"❌ Ya existe un script compartido con el ID `{clean_id}`.", ephemeral=True)

        modal = SharedScriptModal(clean_id, nombre, descripcion, current_codigo="", es_nuevo=True)
        await interaction.response.send_modal(modal)

    # ---------------------------------------------------------
    # /admin_rpg script_editar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="script_editar", description="Edita el código Lua o información de un script compartido.")
    @app_commands.describe(script="Script compartido a editar")
    @app_commands.autocomplete(script=autocomplete_scripts)
    @requiere_admin()
    async def script_editar(self, interaction: discord.Interaction, script: str):
        s_data = await obtener_script(script)
        if not s_data:
            return await interaction.response.send_message(f"❌ Script compartido '{script}' no encontrado.", ephemeral=True)

        modal = SharedScriptModal(s_data["script_id"], s_data["nombre"], s_data.get("descripcion", ""), current_codigo=s_data.get("codigo", ""), es_nuevo=False)
        await interaction.response.send_modal(modal)

    # ---------------------------------------------------------
    # /admin_rpg script_listar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="script_listar", description="Lista todos los scripts Lua compartidos en la biblioteca.")
    @requiere_admin()
    async def script_listar(self, interaction: discord.Interaction):
        scripts = await listar_scripts()
        if not scripts:
            return await interaction.response.send_message("ℹ️ No hay scripts compartidos registrados en la biblioteca.", ephemeral=True)

        embed = discord.Embed(
            title="📜 Biblioteca de Scripts Lua Compartidos",
            description=f"Total de plantillas registradas: **{len(scripts)}**",
            color=0x9B59B6
        )
        for s in scripts[:25]:
            desc = s.get("descripcion") or "Sin descripción"
            code_len = len(s.get("codigo", ""))
            embed.add_field(
                name=f"• {s['nombre']} (`{s['script_id']}`)",
                value=f"*{desc}*\n📏 Tamaño: `{code_len}` caracteres",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # /admin_rpg script_ver
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="script_ver", description="Muestra el código Lua completo de un script compartido.")
    @app_commands.describe(script="Script compartido a inspeccionar")
    @app_commands.autocomplete(script=autocomplete_scripts)
    @requiere_admin()
    async def script_ver(self, interaction: discord.Interaction, script: str):
        s_data = await obtener_script(script)
        if not s_data:
            return await interaction.response.send_message(f"❌ Script compartido '{script}' no encontrado.", ephemeral=True)

        embed = discord.Embed(
            title=f"📜 Script: {s_data['nombre']}",
            description=f"**ID:** `{s_data['script_id']}`\n**Descripción:** *{s_data.get('descripcion') or 'Sin descripción'}*",
            color=0x3498DB
        )
        codigo = s_data.get("codigo", "")
        preview = codigo if len(codigo) <= 1000 else codigo[:1000] + "\n-- [Truncado...]"
        embed.add_field(name="Código Lua", value=f"```lua\n{preview}\n```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # /admin_rpg script_borrar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="script_borrar", description="Elimina un script compartido de la biblioteca.")
    @app_commands.describe(script="Script compartido a eliminar")
    @app_commands.autocomplete(script=autocomplete_scripts)
    @requiere_admin()
    async def script_borrar(self, interaction: discord.Interaction, script: str):
        s_data = await obtener_script(script)
        if not s_data:
            return await interaction.response.send_message(f"❌ Script compartido '{script}' no encontrado.", ephemeral=True)

        ok = await eliminar_script(s_data["script_id"])
        if ok:
            embed = discord.Embed(
                title="🗑️ Script Compartido Eliminado",
                description=f"El script **{s_data['nombre']}** (`{s_data['script_id']}`) fue eliminado. Los ítems asociados volverán al consumo estándar.",
                color=0xE74C3C
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Error al eliminar el script `{script}`.", ephemeral=True)

    # ---------------------------------------------------------
    # /admin_rpg recargar
    # ---------------------------------------------------------
    @admin_rpg_group.command(name="recargar", description="Recarga módulos y Cogs en caliente sin reiniciar el bot.")
    @app_commands.describe(
        modulo="Extensión o módulo a recargar (o 'todos')",
        sincronizar_arbol="Sincronizar el árbol de comandos Slash con Discord (por defecto: False)"
    )
    @app_commands.autocomplete(modulo=autocomplete_cogs_recargables)
    @requiere_admin()
    async def recargar(self, interaction: discord.Interaction, modulo: str = "todos", sincronizar_arbol: bool = False):
        await interaction.response.defer(ephemeral=True)

        if modulo.lower() in ("todos", "all"):
            ok, exitos, errores = await hot_reload_manager.reload_all()
            embed = discord.Embed(
                title="🔄 Recarga en Caliente Completada" if ok else "⚠️ Recarga Parcial con Advertencias",
                color=0x2ECC71 if ok else 0xE67E22
            )
            embed.add_field(name=f"✅ Exitosas ({len(exitos)})", value="\n".join([f"• `{e}`" for e in exitos]) or "*Ninguna*", inline=False)
            if errores:
                embed.add_field(name=f"❌ Errores ({len(errores)})", value="\n".join([f"• {e}" for e in errores[:5]])[:1024], inline=False)
        else:
            ok, msg = await hot_reload_manager.reload_cog(modulo)
            embed = discord.Embed(
                title="✅ Módulo Recargado" if ok else "❌ Error al Recargar",
                description=msg,
                color=0x2ECC71 if ok else 0xE74C3C
            )

        if sincronizar_arbol:
            s_ok, s_msg = await hot_reload_manager.sync_tree(interaction.guild_id)
            embed.add_field(name="⚡ Sincronización de Comandos", value=f"{'✅' if s_ok else '❌'} {s_msg}", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminRPGCommands(bot))

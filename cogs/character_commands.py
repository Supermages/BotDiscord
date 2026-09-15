import json
import logging
import discord
from discord import app_commands
from discord.ext import commands
from core.permissions import requiere_admin
from core.database import (
    buscar_personaje_por_nombre_db,
    auto_vincular_o_crear_personaje,
    importar_tuppers_batch,
    obtener_personajes_activos,
    obtener_personajes_reserva,
    obtener_limite_personajes,
    activar_personaje,
    desactivar_personaje,
    actualizar_personaje,
    normalizar_texto,
    listar_todos_personajes
)
from services.inventory_service import es_admin
from services.tupper_service import tupper_matcher
from ui.views import EditPersonajeView
from ui.character_views import CharacterPanelView
from cogs.inventory_commands import (
    autocomplete_mis_personajes_activos,
    autocomplete_mis_personajes_reserva,
    autocomplete_personajes_todos
)

async def autocomplete_personajes_editables(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocompletado para /pj editar: admins ven todos, usuarios normales ven sus activos y reserva."""
    user_id = str(interaction.user.id)
    curr_norm = normalizar_texto(current)
    choices = []

    if es_admin(interaction.user):
        todos = await listar_todos_personajes()
        for p in todos:
            tag, nombre = p[0], p[1]
            if not curr_norm or curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(tag):
                choices.append(app_commands.Choice(name=f"🛡️ {nombre}"[:100], value=tag[:100]))
                if len(choices) >= 25:
                    break
        return choices

    # Usuario normal: activos + reserva
    activos = await obtener_personajes_activos(user_id)
    reserva = await obtener_personajes_reserva(user_id)

    tags_vistos = set()
    for p in activos:
        tag, nombre = p["tupper_tag"], p["nombre"]
        tags_vistos.add(tag)
        if not curr_norm or curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(tag):
            choices.append(app_commands.Choice(name=f"🛡️ {nombre} (Activo)"[:100], value=tag[:100]))
            if len(choices) >= 25:
                return choices

    for p in reserva:
        tag, nombre = p["tupper_tag"], p["nombre"]
        if tag in tags_vistos:
            continue
        if not curr_norm or curr_norm in normalizar_texto(nombre) or curr_norm in normalizar_texto(tag):
            choices.append(app_commands.Choice(name=f"📦 {nombre} (Reserva)"[:100], value=tag[:100]))
            if len(choices) >= 25:
                return choices

    return choices

class CharacterCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    pj_group = app_commands.Group(name="pj", description="Comandos de gestión de personajes y Tupperbox")

    # ==========================================
    # DETECCIÓN PASIVA EN TIEMPO REAL
    # ==========================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Escucha mensajes en tiempo real para correlacionar automáticamente
        los mensajes enviados por usuarios con los webhooks de Tupperbox,
        guardando los personajes en la reserva del usuario silenciosamente.
        """
        if self.bot.user and message.author.id == self.bot.user.id:
            return

        # 1. Si es mensaje humano
        if not message.author.bot and not message.webhook_id:
            tupper_matcher.registrar_mensaje_humano(
                channel_id=message.channel.id,
                user_id=message.author.id,
                content=message.content
            )
            return

        # 2. Si es mensaje de Webhook
        if message.webhook_id:
            user_id = tupper_matcher.buscar_coincidencia(
                channel_id=message.channel.id,
                webhook_content=message.content
            )

            if user_id:
                tupper_name = message.author.name
                avatar_url = str(message.author.display_avatar.url)
                
                try:
                    exito, estado = await auto_vincular_o_crear_personaje(
                        tupper_name=tupper_name,
                        avatar_url=avatar_url,
                        user_id=str(user_id)
                    )
                    if exito and estado in ("creado_en_reserva", "guardado_en_reserva"):
                        logging.info(
                            f"[🎭 Auto-Tupper] Personaje '{tupper_name}' guardado en reserva para el usuario {user_id}."
                        )
                except Exception as e:
                    logging.error(f"Error en auto-vinculación de Tupperbox para '{tupper_name}': {e}")

    # ==========================================
    # /pj panel
    # ==========================================
    @pj_group.command(name="panel", description="Abre el panel interactivo para activar y desactivar personajes de tu cupo.")
    async def panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        view = CharacterPanelView(interaction.user, guild_id=guild_id)
        await view.cargar_datos()
        await interaction.followup.send(embed=view.generar_embed(), view=view, ephemeral=True)

    # ==========================================
    # /pj lista
    # ==========================================
    @pj_group.command(name="lista", description="Muestra el resumen de tus personajes activos y en reserva.")
    async def lista(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        limite = await obtener_limite_personajes(guild_id)
        activos = await obtener_personajes_activos(str(interaction.user.id))
        reserva = await obtener_personajes_reserva(str(interaction.user.id))

        embed = discord.Embed(
            title="👤 Tus Personajes de Rol",
            description=f"Panel de personajes de {interaction.user.mention} (Cupo: `{len(activos)}/{limite}`).",
            color=0x3498DB
        )

        if activos:
            lista_act = "\n".join([f"• 🛡️ **{p['nombre']}** (`{p['tupper_tag']}`)" for p in activos])
            embed.add_field(name=f"✅ Activos en Juego ({len(activos)}/{limite})", value=lista_act, inline=False)
        else:
            embed.add_field(
                name=f"⚠️ Sin Personajes Activos (0/{limite})", 
                value="No tienes personajes activos. Usa `/pj panel` o `/pj vincular` para activar uno de tu reserva.", 
                inline=False
            )

        if reserva:
            muestra = [f"`{p['nombre']}`" for p in reserva[:15]]
            extra = f" y {len(reserva) - 15} más..." if len(reserva) > 15 else ""
            embed.add_field(
                name=f"📦 En Reserva ({len(reserva)})",
                value=", ".join(muestra) + extra,
                inline=False
            )
        else:
            embed.add_field(
                name="📦 En Reserva (0)",
                value="No tienes personajes en reserva. Puedes importarlos con `/pj importar`.",
                inline=False
            )

        embed.set_footer(text="Usa /pj panel para activar o desactivar con menús desplegables.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # /pj vincular
    # ==========================================
    @pj_group.command(name="vincular", description="Activa un personaje de tu reserva personal.")
    @app_commands.describe(personaje="Personaje de tu reserva a activar")
    @app_commands.autocomplete(personaje=autocomplete_mis_personajes_reserva)
    async def vincular(self, interaction: discord.Interaction, personaje: str):
        if personaje == "__sin_reserva__":
            return await interaction.response.send_message(
                "📭 No tienes ningún personaje en reserva.\n"
                "Puedes importar tus personajes con `/pj importar` o escribiendo con ellos mediante Tupperbox.",
                ephemeral=True
            )

        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        limite = await obtener_limite_personajes(guild_id)
        
        ok, msg, pj_dict = await activar_personaje(str(interaction.user.id), personaje, limite)
        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

        embed = discord.Embed(
            title="🔗 Personaje Activado",
            description=f"¡Has activado a **{pj_dict['nombre']}** exitosamente! Ya puedes consultar su inventario con `/inv ver` y fabricar con `/craft fabricar`.",
            color=0x2ECC71
        )
        if pj_dict.get("avatar_url"):
            embed.set_thumbnail(url=pj_dict["avatar_url"])
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # /pj desvincular
    # ==========================================
    @pj_group.command(name="desvincular", description="Pasa un personaje activo a tu reserva para liberar cupo.")
    @app_commands.describe(personaje="Personaje activo a pasar a reserva")
    @app_commands.autocomplete(personaje=autocomplete_mis_personajes_activos)
    async def desvincular(self, interaction: discord.Interaction, personaje: str):
        if personaje == "__sin_activos__":
            return await interaction.response.send_message(
                "📭 No tienes ningún personaje activo para desvincular.\n"
                "Usa `/pj panel` o `/pj vincular` para activar uno de tu reserva primero.",
                ephemeral=True
            )

        ok, msg = await desactivar_personaje(str(interaction.user.id), personaje)
        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

        embed = discord.Embed(
            title="📦 Personaje Pasado a Reserva",
            description=msg,
            color=0x95A5A6
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # /pj importar
    # ==========================================
    @pj_group.command(name="importar", description="Importa tus personajes de Tupperbox (tul!export) a tu reserva personal.")
    @app_commands.describe(archivo="Archivo tuppers.json generado por Tupperbox")
    async def importar(self, interaction: discord.Interaction, archivo: discord.Attachment):
        await interaction.response.defer(ephemeral=True)

        if not archivo.filename.lower().endswith(".json"):
            return await interaction.followup.send(
                "❌ El archivo debe ser un documento `.json` (obtenido mediante `tul!export` de Tupperbox).",
                ephemeral=True
            )

        try:
            contenido_bytes = await archivo.read()
            datos_json = json.loads(contenido_bytes.decode("utf-8", errors="replace"))
        except Exception as e:
            return await interaction.followup.send(
                f"❌ Error al leer o procesar el archivo JSON: `{e}`",
                ephemeral=True
            )

        tuppers = datos_json.get("tuppers")
        if not isinstance(tuppers, list):
            return await interaction.followup.send(
                "❌ El formato del archivo no coincide con una exportación válida de Tupperbox (no se encontró la lista 'tuppers').",
                ephemeral=True
            )

        if not tuppers:
            return await interaction.followup.send(
                "⚠️ El archivo no contiene ningún personaje registrado en Tupperbox.",
                ephemeral=True
            )

        # Importar a la reserva del usuario
        res = await importar_tuppers_batch(str(interaction.user.id), tuppers)

        creados = res["creados"]
        actualizados = res["actualizados"]
        conflictos = res["conflictos"]

        color = 0x2ECC71 if not conflictos else 0xE67E22
        embed = discord.Embed(
            title="🎭 Importación a Reserva de Tupperbox",
            description=(
                f"Se han procesado **{len(tuppers)}** personajes para tu cuenta ({interaction.user.mention}).\n"
                f"*Todos tus personajes se han guardado en tu reserva. Usa `/pj panel` para activar los que quieras jugar.*"
            ),
            color=color
        )

        if creados:
            muestra = ", ".join(f"`{c}`" for c in creados[:15])
            extra = f" y {len(creados) - 15} más..." if len(creados) > 15 else ""
            embed.add_field(
                name=f"✅ Nuevos en Reserva ({len(creados)})",
                value=f"{muestra}{extra}",
                inline=False
            )

        if actualizados:
            muestra = ", ".join(f"`{a}`" for a in actualizados[:15])
            extra = f" y {len(actualizados) - 15} más..." if len(actualizados) > 15 else ""
            embed.add_field(
                name=f"🔄 Actualizados en Reserva ({len(actualizados)})",
                value=f"{muestra}{extra}",
                inline=False
            )

        if conflictos:
            muestra = ", ".join(f"`{conf}`" for conf in conflictos[:10])
            extra = f" y {len(conflictos) - 10} más..." if len(conflictos) > 10 else ""
            embed.add_field(
                name=f"⚠️ Omitidos por Conflicto ({len(conflictos)})",
                value=f"Estos personajes ya están registrados a nombre de otro usuario:\n{muestra}{extra}",
                inline=False
            )

        embed.set_footer(text="Abre el panel con /pj panel para activar tus personajes.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # /pj guia
    # ==========================================
    @pj_group.command(name="guia", description="Muestra la guía completa para sincronizar personajes de Tupperbox con EriduBot.")
    async def guia(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Guía de Integración con Tupperbox & EriduBot",
            description=(
                "EriduBot te permite gestionar el **inventario, crafteo y transferencias** "
                "de tus personajes de rol. Tienes un cupo de personajes activos y una reserva ilimitada."
            ),
            color=0x3498DB
        )

        embed.add_field(
            name="🚀 Paso 1: Importa tus personajes",
            value=(
                "**1.** En cualquier canal, escribe con Tupperbox: `tul!export` (o `/export`).\n"
                "**2.** Descarga el archivo `tuppers.json` que te envía Tupperbox.\n"
                "**3.** Usa el comando `/pj importar` y sube ese archivo."
            ),
            inline=False
        )

        embed.add_field(
            name="🎮 Paso 2: Activa tus personajes activos (Cupo máx. 3)",
            value=(
                "Usa `/pj panel` para abrir el menú interactivo con menús desplegables, o escribe `/pj vincular [personaje]`.\n"
                "Puedes cambiar de personaje cuando quieras pasando los que no uses a la reserva con `/pj desvincular` sin perder ningún ítem."
            ),
            inline=False
        )

        embed.add_field(
            name="🎒 Comandos Esenciales",
            value=(
                "• `/inv ver`: Consulta el cofre de ítems de tu personaje activo.\n"
                "• `/inv transferir`: Mueve materiales a otro personaje con confirmación.\n"
                "• `/craft recetas`: Revisa las fórmulas del servidor.\n"
                "• `/craft fabricar`: Forja armas y pociones con tus materiales."
            ),
            inline=False
        )

        embed.set_footer(text="EriduBot • Rol e Inventario")
        await interaction.response.send_message(embed=embed, ephemeral=False)

    # ==========================================
    # /pj editar
    # ==========================================
    @pj_group.command(name="editar", description="Edita las propiedades de un personaje (nombre, foto, colores, lado).")
    @app_commands.describe(
        personaje="Nombre o tag del personaje a editar",
        nombre="Nuevo nombre visible del personaje (opcional)",
        avatar="Nueva URL de imagen/avatar (opcional)",
        color_fondo="Color HEX de la burbuja de chat (#RRGGBB) (opcional)",
        color_texto="Color HEX del texto (#RRGGBB) (opcional)",
        lado="Lado de aparición en el chat (opcional)"
    )
    @app_commands.choices(lado=[
        app_commands.Choice(name="Izquierda (I)", value="I"),
        app_commands.Choice(name="Derecha (D)", value="D")
    ])
    @app_commands.autocomplete(personaje=autocomplete_personajes_editables)
    async def editar(
        self,
        interaction: discord.Interaction,
        personaje: str,
        nombre: str | None = None,
        avatar: str | None = None,
        color_fondo: str | None = None,
        color_texto: str | None = None,
        lado: str | None = None
    ):
        await interaction.response.defer(ephemeral=True)
        p_info = await buscar_personaje_por_nombre_db(personaje)

        if not p_info:
            return await interaction.followup.send(f"❌ No se encontró el personaje llamado **{personaje}**.", ephemeral=True)

        tupper_tag, nombre_real, lado_actual, avatar_url, color, color_texto_actual, owner_id, creator_id = p_info[:8]
        user_id_str = str(interaction.user.id)

        # Verificación de permisos: Admin, o creador/dueño
        es_admin_user = es_admin(interaction.user)
        es_propietario = (creator_id == user_id_str) or (owner_id == user_id_str)

        if not (es_admin_user or es_propietario):
            return await interaction.followup.send(
                "❌ No tienes permiso para editar este personaje. Solo su creador o un administrador pueden editarlo.",
                ephemeral=True
            )

        # Si se pasó algún argumento directamente por comando:
        tiene_args_directos = any(arg is not None for arg in (nombre, avatar, color_fondo, color_texto, lado))

        if tiene_args_directos:
            cambios = []

            # Validación de nombre
            nuevo_nombre = None
            if nombre is not None:
                n_clean = nombre.strip()
                if not n_clean:
                    return await interaction.followup.send("❌ El nombre no puede estar vacío.", ephemeral=True)
                nuevo_nombre = n_clean
                cambios.append(f"• **Nombre:** {nombre_real} ➔ **{nuevo_nombre}**")

            # Validación de avatar
            nuevo_avatar = None
            if avatar is not None:
                a_clean = avatar.strip()
                if not (a_clean.startswith("http://") or a_clean.startswith("https://")):
                    return await interaction.followup.send("❌ La URL del avatar debe comenzar con `http://` o `https://`.", ephemeral=True)
                nuevo_avatar = a_clean
                cambios.append("• **Avatar:** Actualizado con nueva URL")

            # Validación de color de fondo
            nuevo_color_fondo = None
            if color_fondo is not None:
                c_clean = color_fondo.strip().upper()
                if not c_clean.startswith("#") or len(c_clean) != 7:
                    return await interaction.followup.send("❌ Color de fondo inválido. Usa formato HEX como `#RRGGBB`.", ephemeral=True)
                nuevo_color_fondo = c_clean
                cambios.append(f"• **Color Fondo:** `{nuevo_color_fondo}`")

            # Validación de color de texto
            nuevo_color_texto = None
            if color_texto is not None:
                ct_clean = color_texto.strip().upper()
                if not ct_clean.startswith("#") or len(ct_clean) != 7:
                    return await interaction.followup.send("❌ Color de texto inválido. Usa formato HEX como `#RRGGBB`.", ephemeral=True)
                nuevo_color_texto = ct_clean
                cambios.append(f"• **Color Texto:** `{nuevo_color_texto}`")

            # Validación de lado
            nuevo_lado = None
            if lado is not None:
                nuevo_lado = lado
                lado_nombre = "⬅️ Izquierda (I)" if nuevo_lado == "I" else "➡️ Derecha (D)"
                cambios.append(f"• **Lado:** {lado_nombre}")

            await actualizar_personaje(
                tupper_tag,
                nombre=nuevo_nombre,
                avatar_url=nuevo_avatar,
                lado=nuevo_lado,
                color=nuevo_color_fondo,
                color_texto=nuevo_color_texto
            )

            color_embed = 0x2ECC71
            if nuevo_color_fondo:
                try:
                    color_embed = int(nuevo_color_fondo.replace("#", ""), 16)
                except Exception:
                    pass

            embed = discord.Embed(
                title="✅ Personaje Actualizado",
                description=f"Se han aplicado los siguientes cambios a **{nuevo_nombre or nombre_real}** (`{tupper_tag}`):\n\n" + "\n".join(cambios),
                color=color_embed
            )
            thumb = nuevo_avatar or avatar_url
            if thumb and thumb.startswith("http"):
                embed.set_thumbnail(url=thumb)

            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Si no se pasó ningún argumento directo, abrir menú interactivo
        view = EditPersonajeView(interaction, tupper_tag, nombre_real, lado_actual, color, color_texto_actual, avatar_url)
        await view.send_preview()


async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterCommands(bot))

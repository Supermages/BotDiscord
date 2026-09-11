import json
import logging
import discord
from discord import app_commands
from discord.ext import commands
from core.permissions import requiere_admin
from core.database import (
    buscar_personaje_por_nombre_db,
    auto_vincular_o_crear_personaje,
    importar_tuppers_batch
)
from services.tupper_service import tupper_matcher
from ui.views import EditPersonajeView

class CharacterCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # DETECCIÓN PASIVA EN TIEMPO REAL
    # ==========================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Escucha mensajes en tiempo real para correlacionar automáticamente
        los mensajes enviados por usuarios con los webhooks generados por Tupperbox.
        """
        # Ignorar mensajes del propio bot
        if self.bot.user and message.author.id == self.bot.user.id:
            return

        # 1. Si es un mensaje de un usuario humano (no bot y sin webhook)
        if not message.author.bot and not message.webhook_id:
            tupper_matcher.registrar_mensaje_humano(
                channel_id=message.channel.id,
                user_id=message.author.id,
                content=message.content
            )
            return

        # 2. Si es un mensaje de Webhook (Tupperbox envía vía webhook)
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
                    if exito and estado in ("creado", "vinculado"):
                        logging.info(
                            f"[🎭 Auto-Tupper] Personaje '{tupper_name}' {estado} exitosamente para el usuario {user_id}."
                        )
                except Exception as e:
                    logging.error(f"Error en auto-vinculación de Tupperbox para '{tupper_name}': {e}")

    # ==========================================
    # COMANDO: /importar_tuppers
    # ==========================================
    @app_commands.command(
        name="importar_tuppers",
        description="Importa masivamente tus personajes de Tupperbox usando el archivo JSON de 'tul!export'."
    )
    @app_commands.describe(archivo="Archivo tuppers.json generado por Tupperbox")
    async def importar_tuppers(self, interaction: discord.Interaction, archivo: discord.Attachment):
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

        # Importar a la base de datos
        res = await importar_tuppers_batch(str(interaction.user.id), tuppers)

        creados = res["creados"]
        actualizados = res["actualizados"]
        conflictos = res["conflictos"]

        color = 0x2ECC71 if not conflictos else 0xE67E22
        embed = discord.Embed(
            title="🎭 Importación de Personajes de Tupperbox",
            description=f"Se han procesado **{len(tuppers)}** personajes para tu cuenta ({interaction.user.mention}).",
            color=color
        )

        if creados:
            muestra = ", ".join(f"`{c}`" for c in creados[:15])
            extra = f" y {len(creados) - 15} más..." if len(creados) > 15 else ""
            embed.add_field(
                name=f"✅ Nuevos Registrados ({len(creados)})",
                value=f"{muestra}{extra}",
                inline=False
            )

        if actualizados:
            muestra = ", ".join(f"`{a}`" for a in actualizados[:15])
            extra = f" y {len(actualizados) - 15} más..." if len(actualizados) > 15 else ""
            embed.add_field(
                name=f"🔄 Actualizados / Vinculados ({len(actualizados)})",
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

        embed.set_footer(text="¡Listo! Ya puedes usar /inventario, /craftear y /transferir con tus personajes.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # COMANDO: /guia_personajes
    # ==========================================
    @app_commands.command(
        name="guia_personajes",
        description="Muestra la guía para exportar de Tupperbox e integrar tus personajes con EriduBot."
    )
    async def guia_personajes(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Guía de Integración con Tupperbox & EriduBot",
            description=(
                "EriduBot te permite gestionar el **inventario, crafteo y transferencias** "
                "de cada uno de tus personajes de rol de forma individual. Aquí tienes las formas de vincularlos:"
            ),
            color=0x3498DB
        )

        embed.add_field(
            name="🚀 Método 1: Importación Rápida con Archivo (Recomendado)",
            value=(
                "**1.** Escribe en cualquier canal el comando de Tupperbox: `tul!export` (o `/export`).\n"
                "**2.** Tupperbox te enviará un archivo llamado `tuppers.json`. Descárgalo.\n"
                "**3.** Usa el comando `/importar_tuppers` en EriduBot y arrastra ese archivo.\n"
                "*(En 1 segundo todos tus personajes quedan guardados con su foto y vinculados a ti)*."
            ),
            inline=False
        )

        embed.add_field(
            name="⚡ Método 2: Detección Automática Pasiva",
            value=(
                "Si no tienes el archivo o creas un personaje nuevo en Tupperbox, **simplemente habla con él "
                "en cualquier canal de rol**. EriduBot detectará tu autoría en tiempo real y guardará el personaje "
                "automáticamente sin que tengas que hacer nada."
            ),
            inline=False
        )

        embed.add_field(
            name="🔗 Método 3: Reclamo Manual",
            value=(
                "Si un personaje ya existe en la base de datos pero no tiene dueño, usa:\n"
                "`/vincular_personaje [nombre]` para asignártelo directamente."
            ),
            inline=False
        )

        embed.add_field(
            name="🎒 Comandos Esenciales de Rol",
            value=(
                "• `/mis_personajes`: Consulta los personajes que te pertenecen.\n"
                "• `/inventario [personaje]`: Abre el cofre de ítems de tu personaje.\n"
                "• `/transferir [de] [a] [item] [cant]`: Pasa materiales a otro personaje.\n"
                "• `/recetas` y `/craftear`: Consulta fórmulas y forja nuevos objetos."
            ),
            inline=False
        )

        embed.set_footer(text="EriduBot • Sistema de Rol e Inventario")
        await interaction.response.send_message(embed=embed, ephemeral=False)

    # ==========================================
    # COMANDO: /editarpersonaje (Admin)
    # ==========================================
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

        tupper_tag, nombre_real, lado, avatar_url, color, color_texto, owner_id = personaje
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

import asyncio
import datetime
from datetime import timezone
import discord
from discord import app_commands
from discord.ext import commands

from core.config import Config
from core.permissions import requiere_admin
from core.database import set_modo_captura
from ui.views import LadoView
from services import chat_service
from services.monitor_service import monitor_manager


async def pedir_lado_interactivo(
    interaction: discord.Interaction,
    tupper_tag: str,
    personaje_nombre: str,
    avatar_url: str,
) -> str:
    """Pregunta el lado de un personaje nuevo con LadoView y espera respuesta (máx. 60 s).

    Devuelve el lado elegido, o 'I' si no responde o si falla la interacción,
    para no bloquear el render. La persistencia la hace el service.
    """
    try:
        view = LadoView(interaction.user.id, tupper_tag, personaje_nombre, avatar_url)
        aviso = await interaction.followup.send(
            f"📢 **{personaje_nombre}** nuevo. ¿Lado?",
            view=view,
            ephemeral=True
        )
        await view.wait()
        try:
            await aviso.delete()
        except Exception:
            pass
        return view.lado or "I"
    except Exception:
        return "I"


class ChatCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    chat_group = app_commands.Group(
        name="chat", 
        description="Comandos de captura y renderizado de chat",
        default_permissions=discord.Permissions(administrator=True)
    )

    # ---------------------------------------------------------
    # /chat generar (adaptador fino: la orquestación vive en chat_service)
    # ---------------------------------------------------------
    @chat_group.command(name="generar", description="Genera un chat segmentado en varias imágenes.")
    @app_commands.describe(
        cantidad="Cantidad total de mensajes", 
        title="Título del chat", 
        duracion="Duración monitor en minutos (0 para no monitorear)"
    )
    @requiere_admin()
    async def generar(self, interaction: discord.Interaction, cantidad: int = 20, title: str = "chat", duracion: int = 5):
        channel = interaction.channel

        if monitor_manager.esta_activo(channel.id):
            monitor_manager.detener_monitor(channel.id)
            await channel.send("🔄 Se ha detenido el monitor anterior para iniciar el nuevo.", delete_after=5)

        if cantidad > Config.MAX_MENSAJES_TOTAL:
            return await interaction.response.send_message(
                f"❌ **Límite excedido.** El máximo permitido es **{Config.MAX_MENSAJES_TOTAL}** mensajes.", 
                ephemeral=True
            )

        await interaction.response.defer()

        async def resolver_lado(tupper_tag: str, personaje_nombre: str, avatar_url: str) -> str:
            return await pedir_lado_interactivo(interaction, tupper_tag, personaje_nombre, avatar_url)

        async def publicar(contenido: str, archivos: list) -> discord.Message:
            return await interaction.followup.send(content=contenido, files=archivos)

        try:
            await chat_service.generar_chat(
                channel=channel,
                solicitante=interaction.user,
                bot_user_id=self.bot.user.id,
                cantidad=cantidad,
                titulo=title,
                duracion_monitor=duracion,
                resolver_lado=resolver_lado,
                publicar=publicar,
            )
        except chat_service.ChatServiceError as e:
            await interaction.followup.send(e.mensaje)

    # ---------------------------------------------------------
    # /chat forzar (adaptador fino: la orquestación vive en chat_service)
    # ---------------------------------------------------------
    @chat_group.command(name="forzar", description="Fuerza la actualización del chat renderizado.")
    @requiere_admin()
    async def forzar(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            cambios = await chat_service.forzar_actualizacion(
                interaction.channel, interaction.user, self.bot.user.id
            )
        except chat_service.ChatJsonInexistente:
            return await interaction.followup.send(embed=discord.Embed(
                title="❌ Error",
                description="No se ha generado un chat para este canal.",
                color=0xFF0000
            ))
        except chat_service.SinMensajeOriginal:
            return await interaction.followup.send(embed=discord.Embed(
                title="❌ Error",
                description="No se encontró el mensaje original para actualizar.",
                color=0xFF0000
            ))
        except chat_service.MensajeOriginalNoEncontrado as e:
            return await interaction.followup.send(e.mensaje)
        except chat_service.ActualizacionRechazada as e:
            return await interaction.followup.send(embed=discord.Embed(
                title="❌ Error",
                description=e.mensaje,
                color=0xFF0000
            ))
        except chat_service.ErrorInesperado as e:
            return await interaction.followup.send(embed=discord.Embed(
                title="❌ Error",
                description=e.mensaje,
                color=0xFF0000
            ))

        if cambios:
            await interaction.followup.send(embed=discord.Embed(title="✅ ¡Actualizado!", color=0x00B0F4))
        else:
            await interaction.followup.send(embed=discord.Embed(
                title="⚠️ Sin cambios",
                description="No hubo nuevos mensajes.",
                color=0xFFFF00
            ))

    # ---------------------------------------------------------
    # /chat monitores
    # ---------------------------------------------------------
    @chat_group.command(name="monitores", description="Muestra todos los canales con monitores de chat activos.")
    @requiere_admin()
    async def monitores(self, interaction: discord.Interaction):
        monitores = monitor_manager.obtener_monitores()
        if not monitores:
            embed = discord.Embed(
                title="📭 Monitores activos",
                description="Actualmente no hay ningún monitor activo.",
                color=0xAAAAAA
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        desc = ""
        ahora = datetime.datetime.now(timezone.utc)
        for canal_id, info in monitores.items():
            restante = max(0, (info["hasta"] - ahora).total_seconds() // 60)
            desc += f"• Canal <#{canal_id}> — {int(restante)} min restantes\n"

        embed = discord.Embed(
            title="📡 Monitores activos",
            description=desc,
            color=0x00B0F4
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # /chat detener
    # ---------------------------------------------------------
    @chat_group.command(name="detener", description="Detiene el monitor de auto-actualización en el canal actual.")
    @requiere_admin()
    async def detener(self, interaction: discord.Interaction):
        canal_id = interaction.channel.id
        detenido = monitor_manager.detener_monitor(canal_id)

        if detenido:
            embed = discord.Embed(
                title="🛑 Monitor detenido",
                description="El monitor de este canal ha sido detenido correctamente.",
                color=0xFF5733
            )
        else:
            embed = discord.Embed(
                title="⚠️ Sin monitor",
                description="Este canal no tiene un monitor activo actualmente.",
                color=0xCCCC00
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # /chat configuracion
    # ---------------------------------------------------------
    @chat_group.command(name="configuracion", description="Configura el modo de captura del chat (Tupperbox o Todo).")
    @app_commands.describe(modo="Elige qué mensajes debe capturar el bot")
    @app_commands.choices(modo=[
        app_commands.Choice(name="🎭 Solo Tupperbox (Por defecto)", value="TUPPER"),
        app_commands.Choice(name="📢 Todo el chat (Usuarios y Bots)", value="TODO")
    ])
    @requiere_admin()
    async def configuracion(self, interaction: discord.Interaction, modo: app_commands.Choice[str]):
        await set_modo_captura(interaction.guild_id, modo.value)
        
        texto = "🎭 **Solo Tupperbox**" if modo.value == "TUPPER" else "📢 **Todo el chat**"
        embed = discord.Embed(
            title="⚙️ Configuración Actualizada", 
            description=f"Ahora el bot capturará: {texto}",
            color=0x00FF00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # /chat spam_ping
    # ---------------------------------------------------------
    @chat_group.command(name="spam_ping", description="Envía un número de menciones consecutivas a un usuario.")
    @app_commands.describe(
        usuario="El usuario al que quieres mencionar", 
        cantidad="Número de veces que enviar el ping (máximo 30000)"
    )
    @requiere_admin()
    async def spam_ping(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        limite_maximo = 30000
        if cantidad > limite_maximo:
            embed = discord.Embed(
                title="❌ Límite excedido", 
                description=f"Para evitar que Discord penalice al bot, el máximo de pings permitidos es **{limite_maximo}**.", 
                color=0xFF0000
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor que 0.", ephemeral=True)

        await interaction.response.send_message(
            f"✅ Iniciando el envío de {cantidad} pings a {usuario.display_name}...", 
            ephemeral=True
        )

        for _ in range(cantidad):
            try:
                await interaction.channel.send(f"{usuario.mention}")
                await asyncio.sleep(1.5)
            except discord.Forbidden:
                break


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCommands(bot))

import os
import json
import re
import asyncio
import datetime
import logging
from datetime import timezone
import discord
from discord import app_commands
from discord.ext import commands

from core.config import Config
from core.permissions import requiere_admin
from core.formatters import limpiar_formato_discord
from core.database import obtener_personaje, guardar_personaje, get_modo_captura, set_modo_captura
from ui.views import LadoView
from services.tupper_service import detectar_tupperbox_id
from services.chat_sync_service import procesar_adjuntos_mensaje, actualizar_chat_logica
from services.image_service import generar_imagenes_por_lotes, generar_imagen_segmentada
from services.monitor_service import monitor_manager

class ChatCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    chat_group = app_commands.Group(name="chat", description="Comandos de captura y renderizado de chat")

    # ---------------------------------------------------------
    # /chat generar
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
        modo_captura = await get_modo_captura(interaction.guild_id)
        mensajes_a_procesar = []

        logging.info(f"GenerarChat: Iniciando en #{channel.name}. Modo: {modo_captura} | Cantidad: {cantidad}")

        if modo_captura == 'TUPPER':
            tupperbox_id = await detectar_tupperbox_id(channel)
            if not tupperbox_id:
                return await interaction.followup.send("❌ No se detectó Tupperbox y el modo es 'Solo Tupper'.")

            async for msg in channel.history(limit=Config.SEARCH_LIMIT):
                if msg.webhook_id and msg.author.id == tupperbox_id:
                    mensajes_a_procesar.append(msg)
                    if len(mensajes_a_procesar) >= cantidad:
                        break
        else:
            async for msg in channel.history(limit=Config.SEARCH_LIMIT):
                if msg.author.id != self.bot.user.id and not msg.content.startswith("/"):
                    mensajes_a_procesar.append(msg)
                    if len(mensajes_a_procesar) >= cantidad:
                        break

        mensajes_a_procesar.reverse()

        mensajes_json = []
        for msg in mensajes_a_procesar:
            tupper_tag = msg.author.name
            personaje_nombre = tupper_tag.split(" - ")[0] if " - " in tupper_tag else tupper_tag
            avatar_url = str(msg.author.display_avatar.url)

            personaje = await obtener_personaje(tupper_tag)
            if not personaje:
                if modo_captura == 'TUPPER' or msg.author.id == interaction.user.id:
                    try:
                        view = LadoView(interaction.user.id, tupper_tag, personaje_nombre, avatar_url)
                        aviso = await interaction.followup.send(
                            f"📢 **{personaje_nombre}** nuevo. ¿Lado?", 
                            view=view, 
                            ephemeral=True
                        )
                        await view.wait()
                        lado = view.lado or "I"
                        await guardar_personaje(tupper_tag, personaje_nombre, lado, avatar_url, "#FFFFFF", "#000000")
                        try:
                            await aviso.delete()
                        except:
                            pass
                    except:
                        lado = "I"
                        await guardar_personaje(tupper_tag, personaje_nombre, lado, avatar_url)
                else:
                    await guardar_personaje(tupper_tag, personaje_nombre, "I", avatar_url)

            adjuntos = procesar_adjuntos_mensaje(msg)
            mensajes_json.append({
                "Personaje": tupper_tag,
                "Mensaje": limpiar_formato_discord(msg.content),
                "Adjuntos": adjuntos
            })

        timestamp = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        titulo_real = title if title != "chat" else channel.name
        last_id = mensajes_a_procesar[0].id if mensajes_a_procesar else None

        chat_json = {
            "Chat": {
                "titulo": titulo_real,
                "timestamp": timestamp,
                "id": f"chat_{channel.id}_{timestamp}",
                "mensajes": mensajes_json,
                "canal_id": channel.id,
                "mensaje_id": None,
                "duracion_monitor": duracion,
                "last_processed_message_id": last_id
            }
        }

        json_path = os.path.join(Config.EXPORT_FOLDER, f"chat_{channel.id}.json")
        async with monitor_manager.file_lock:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(chat_json, f, indent=4, ensure_ascii=False)

        try:
            rutas = await generar_imagenes_por_lotes(chat_json, channel.id)
            archivos = [discord.File(ruta) for ruta in rutas]

            msg = await interaction.followup.send(
                content=f"📸 Chat renderizado: **{titulo_real}** ({len(mensajes_json)} mensajes)", 
                files=archivos
            )

            for ruta in rutas:
                if os.path.exists(ruta):
                    os.remove(ruta)

            chat_json["Chat"]["mensaje_id"] = msg.id
            async with monitor_manager.file_lock:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(chat_json, f, indent=4, ensure_ascii=False)

            if duracion > 0:
                monitor_manager.registrar_monitor(
                    channel=channel, 
                    message_id=msg.id, 
                    duracion_minutos=duracion, 
                    solicitante=interaction.user, 
                    bot_user_id=self.bot.user.id
                )

        except Exception as e:
            logging.error(f"Error generando imágenes: {e}")
            await interaction.followup.send("❌ Hubo un error generando las imágenes.")

    # ---------------------------------------------------------
    # /chat forzar
    # ---------------------------------------------------------
    @chat_group.command(name="forzar", description="Fuerza la actualización del chat renderizado.")
    @requiere_admin()
    async def forzar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        json_filename = os.path.join(Config.EXPORT_FOLDER, f"chat_{interaction.channel.id}.json")

        if not os.path.exists(json_filename):
            embed = discord.Embed(title="❌ Error", description="No se ha generado un chat para este canal.", color=0xFF0000)
            return await interaction.followup.send(embed=embed)

        async with monitor_manager.file_lock:
            with open(json_filename, "r", encoding="utf-8") as f:
                chat_json = json.load(f)

        mensaje_id = chat_json["Chat"].get("mensaje_id")
        if not mensaje_id:
            return await interaction.followup.send(embed=discord.Embed(
                title="❌ Error",
                description="No se encontró el mensaje original para actualizar.",
                color=0xFF0000
            ))

        cambios = await actualizar_chat_logica(interaction.channel, chat_json, interaction.user, self.bot.user.id)
        if cambios:
            async with monitor_manager.file_lock:
                with open(json_filename, "w", encoding="utf-8") as f:
                    json.dump(chat_json, f, indent=4, ensure_ascii=False)

            final_path = await generar_imagen_segmentada(chat_json, interaction.channel.id)

            try:
                msg = await interaction.channel.fetch_message(mensaje_id)
                await msg.edit(content="✅ (Actualizado manual)", attachments=[discord.File(final_path)])
                if os.path.exists(final_path):
                    os.remove(final_path)
            except discord.NotFound:
                return await interaction.followup.send("❌ No se encontró el mensaje original.")

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
        cantidad="Número de veces a enviar el ping (máximo 30000)"
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
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

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

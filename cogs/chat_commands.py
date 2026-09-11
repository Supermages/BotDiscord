import os
import json
import re
import datetime
import logging
from datetime import timezone
import discord
from discord import app_commands
from discord.ext import commands

from core.config import Config
from core.permissions import requiere_admin
from core.formatters import limpiar_formato_discord
from core.database import obtener_personaje, guardar_personaje, get_modo_captura
from ui.views import LadoView
from services.tupper_service import detectar_tupperbox_id
from services.chat_sync_service import procesar_adjuntos_mensaje, actualizar_chat_logica
from services.image_service import generar_imagenes_por_lotes, generar_imagen_segmentada
from services.monitor_service import monitor_manager

class ChatCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="generarchat", description="Genera un chat segmentado en varias imágenes.")
    @app_commands.describe(
        cantidad="Cantidad total de mensajes", 
        title="Título del chat", 
        duracion="Duración monitor en minutos (0 para no monitorear)"
    )
    @requiere_admin()
    async def generarchat(self, interaction: discord.Interaction, cantidad: int = 20, title: str = "chat", duracion: int = 5):
        channel = interaction.channel

        # Detener monitor previo si ya existía en este canal
        if monitor_manager.esta_activo(channel.id):
            monitor_manager.detener_monitor(channel.id)
            await channel.send("🔄 Se ha detenido el monitor anterior para iniciar el nuevo.", delete_after=5)

        # Validación de límites
        if cantidad > Config.MAX_MENSAJES_TOTAL:
            return await interaction.response.send_message(
                f"❌ **Límite excedido.** El máximo permitido es **{Config.MAX_MENSAJES_TOTAL}** mensajes.", 
                ephemeral=True
            )

        await interaction.response.defer()
        modo_captura = await get_modo_captura(interaction.guild_id)
        mensajes_a_procesar = []

        logging.info(f"GenerarChat: Iniciando en #{channel.name}. Modo: {modo_captura} | Cantidad: {cantidad}")

        # Selección de mensajes según el modo
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
                if msg.author.id == self.bot.user.id or msg.content.startswith("!"):
                    continue
                mensajes_a_procesar.append(msg)
                if len(mensajes_a_procesar) >= cantidad:
                    break

        logging.info(f"GenerarChat: Se procesarán {len(mensajes_a_procesar)} mensajes.")

        # Procesamiento y guardado de personajes
        mensajes_json = []
        for msg in reversed(mensajes_a_procesar):
            personaje_nombre = msg.author.display_name
            tupper_tag = re.sub(r'[^a-zA-Z0-9_]', '_', str(msg.author.name))
            avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.discordapp.com/embed/avatars/0.png"

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
                "fecha": timestamp,
                "ultimo_id": last_id,
                "mensajes": mensajes_json
            }
        }

        json_filename = os.path.join(Config.EXPORT_FOLDER, f"chat_{channel.id}.json")
        async with monitor_manager.file_lock:
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(chat_json, f, indent=4, ensure_ascii=False)

        # Generación de imágenes
        try:
            rutas_imagenes = await generar_imagenes_por_lotes(channel.id, chat_json, titulo_real)
            archivos_discord = [discord.File(path) for path in rutas_imagenes]

            msg = await interaction.followup.send(
                content=f"✅ Chat generado en **{len(rutas_imagenes)} partes**:",
                files=archivos_discord
            )

            for path in rutas_imagenes:
                if os.path.exists(path):
                    os.remove(path)

            # Registrar monitor si duration > 0
            if duracion > 0:
                chat_json["Chat"]["mensaje_id"] = msg.id
                async with monitor_manager.file_lock:
                    with open(json_filename, "w", encoding="utf-8") as f:
                        json.dump(chat_json, f, indent=4, ensure_ascii=False)

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

    @app_commands.command(name="forzaractualizacion", description="Fuerza la actualización del chat (detecta nuevos mensajes)")
    @requiere_admin()
    async def forzaractualizacion(self, interaction: discord.Interaction):
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

async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCommands(bot))

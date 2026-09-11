import discord
import datetime
import logging
import re
from datetime import timezone
from core.database import obtener_personaje, guardar_personaje, get_modo_captura
from core.formatters import limpiar_formato_discord
from services.tupper_service import detectar_tupperbox_id

def procesar_adjuntos_mensaje(msg: discord.Message) -> list:
    """Extrae y formatea adjuntos, stickers y embeds multimedia de un mensaje de Discord."""
    adjuntos = []

    # 1. Archivos e imágenes adjuntas
    if msg.attachments:
        for a in msg.attachments:
            es_imagen = bool(a.content_type and "image" in a.content_type)
            adjuntos.append({
                "url": a.url,
                "filename": a.filename,
                "tipo": "imagen" if es_imagen else "archivo"
            })

    # 2. Stickers de Discord (ignora Lottie/vectorial por compatibilidad HTML)
    if msg.stickers:
        for sticker in msg.stickers:
            if sticker.format != discord.StickerFormatType.lottie:
                adjuntos.append({
                    "url": sticker.url,
                    "filename": "sticker.png",
                    "tipo": "sticker"
                })

    # 3. Embeds (como GIFs de Tenor o Giphy)
    if msg.embeds:
        for embed in msg.embeds:
            if embed.image and embed.image.url:
                adjuntos.append({
                    "url": embed.image.url,
                    "filename": "image.png",
                    "tipo": "imagen"
                })
            elif embed.thumbnail and embed.thumbnail.url:
                adjuntos.append({
                    "url": embed.thumbnail.url,
                    "filename": "thumbnail.png",
                    "tipo": "imagen"
                })

    return adjuntos

async def actualizar_chat_logica(channel: discord.TextChannel, chat_json: dict, solicitante=None, bot_user_id: int = None) -> bool:
    """
    Escanea el canal en busca de nuevos mensajes desde el último mensaje guardado
    y los agrega al chat_json si cumplen las reglas del modo activo.
    """
    mensajes_guardados = chat_json["Chat"]["mensajes"]
    mensajes_guardados_contenido = set(m["Mensaje"] for m in mensajes_guardados)
    nuevos_mensajes = []
    last_id = chat_json["Chat"].get("ultimo_id")

    # 1. Modo de captura
    try:
        modo_captura = await get_modo_captura(channel.guild.id)
    except Exception as e:
        logging.warning(f"Error obteniendo modo de captura: {e}. Usando 'TUPPER'.")
        modo_captura = 'TUPPER'

    tupperbox_id = None
    if modo_captura == 'TUPPER':
        tupperbox_id = await detectar_tupperbox_id(channel)
        if not tupperbox_id:
            logging.warning(f"Monitor: No se detectó ID de Tupperbox en #{channel.name} (Modo estricto).")
            return False

    # 2. Iterador de historial
    if last_id:
        iterator = channel.history(after=discord.Object(id=last_id))
    else:
        iterator = channel.history(limit=100)

    async for msg in iterator:
        procesar = False

        if modo_captura == 'TUPPER':
            if msg.webhook_id and msg.author.id == tupperbox_id:
                procesar = True
        else:
            if (bot_user_id is None or msg.author.id != bot_user_id) and not msg.content.startswith("!"):
                procesar = True

        contenido_limpio = limpiar_formato_discord(msg.content)

        if procesar and contenido_limpio not in mensajes_guardados_contenido:
            personaje_nombre = msg.author.display_name
            tupper_tag = re.sub(r'[^a-zA-Z0-9_]', '_', str(msg.author.name))
            avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.discordapp.com/embed/avatars/0.png"

            # Buscar o autoregistrar personaje en DB
            personaje = await obtener_personaje(tupper_tag)
            if not personaje:
                lado = "I"
                color, color_texto = "#FFFFFF", "#000000"
                await guardar_personaje(tupper_tag, personaje_nombre, lado, avatar_url, color, color_texto)

            adjuntos = procesar_adjuntos_mensaje(msg)

            nuevos_mensajes.append({
                "Personaje": tupper_tag,
                "Mensaje": contenido_limpio,
                "Adjuntos": adjuntos
            })

            chat_json["Chat"]["ultimo_id"] = msg.id

    if nuevos_mensajes:
        logging.info(f"Monitor: Se encontraron {len(nuevos_mensajes)} mensajes nuevos en #{channel.name}")
        if last_id:
            chat_json["Chat"]["mensajes"].extend(nuevos_mensajes)
        else:
            chat_json["Chat"]["mensajes"].extend(reversed(nuevos_mensajes))

        chat_json["Chat"]["fecha"] = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        return True

    return False

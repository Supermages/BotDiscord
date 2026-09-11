import discord
import logging
from core.database import obtener_tupperbox_webhook, guardar_tupperbox_webhook
from core.config import Config

async def detectar_tupperbox_id(channel: discord.TextChannel) -> int | None:
    """
    Detecta el ID del webhook de Tupperbox para el servidor.
    1. Revisa la base de datos (con caché en memoria).
    2. Si no existe, revisa si se configuró TUPPER_WEBHOOK_ID en .env.
    3. Si no, escanea el historial buscando un webhook con múltiples nombres de autor.
    """
    guild_id = str(channel.guild.id)

    # 1. Base de datos
    try:
        datos = await obtener_tupperbox_webhook(guild_id)
        if datos:
            return int(datos[0])
    except Exception as e:
        logging.error(f"Error leyendo caché de webhooks: {e}")

    # 2. Configuración estática en .env si existe
    if Config.TUPPER_WEBHOOK_ID:
        try:
            bot_id = int(Config.TUPPER_WEBHOOK_ID)
            await guardar_tupperbox_webhook(guild_id, bot_id)
            return bot_id
        except ValueError:
            pass

    # 3. Escaneo heurístico en el historial
    logging.info(f"Escaneando historial en #{channel.name} para buscar Tupperbox...")
    ids_nombres = {}

    try:
        async for msg in channel.history(limit=200):
            if not msg.webhook_id:
                continue

            key = msg.author.id
            nombre = msg.author.name

            if key not in ids_nombres:
                ids_nombres[key] = set()
            ids_nombres[key].add(nombre)

        for bot_id, nombres in ids_nombres.items():
            # Si un mismo webhook ID usa más de un nombre, es Tupperbox
            if len(nombres) > 1:
                logging.info(f"[🎭] Detectado Tupperbox ID: {bot_id}. Guardando en base de datos...")
                await guardar_tupperbox_webhook(guild_id, str(bot_id))
                return bot_id

    except discord.DiscordException as e:
        logging.error(f"Error al escanear historial en #{channel.name}: {e}")

    logging.warning(f"[⚠️] No se detectó ningún ID de Tupperbox en #{channel.name}")
    return None

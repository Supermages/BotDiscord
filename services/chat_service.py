"""
Servicio de orquestación del flujo de chat de EriduBot.

Concentra la lógica de negocio reutilizable detrás de /chat generar y
/chat forzar (y reutilizable por el monitor): escanear historial → asegurar
personajes → construir el JSON del chat → renderizar por lotes → publicar.

Decisiones de diseño:
- Sin lógica de presentación: los embeds y mensajes de error se formatean en
  el cog; este módulo solo publica el mensaje final del chat porque su id
  alimenta al monitor.
- Sin UI de Discord: la espera interactiva del lado de un personaje nuevo
  (LadoView) se inyecta como callback asíncrono (`resolver_lado`) y la
  publicación como callback (`publicar`).
- Los fallos se comunican con excepciones tipadas (subclases de
  ChatServiceError) que llevan el mensaje exacto de usuario.
"""

import os
import json
import datetime
import logging
from datetime import timezone
from typing import Awaitable, Callable, Optional

import discord

from core.config import Config
from core.formatters import limpiar_formato_discord
from core.database import obtener_personaje, guardar_personaje, get_modo_captura
from services.tupper_service import detectar_tupperbox_id
from services.chat_sync_service import (
    normalizar_tupper_tag,
    procesar_adjuntos_mensaje,
    actualizar_chat_logica,
)
from services.image_service import generar_imagenes_por_lotes, generar_imagen_segmentada
from services.monitor_service import monitor_manager

# Callback asíncrono que resuelve el lado ("I"/"D") de un personaje nuevo de
# forma interactiva. Recibe (tupper_tag, personaje_nombre, avatar_url) y
# devuelve el lado elegido (o None para usar el por defecto).
ResolverLado = Callable[[str, str, str], Awaitable[Optional[str]]]

# Callback asíncrono que publica el mensaje renderizado y devuelve el mensaje
# enviado (el cog lo implementa con interaction.followup.send).
PublicarChat = Callable[[str, list[discord.File]], Awaitable[discord.Message]]


# ---------------------------------------------------------------------------
# Errores tipados (mensaje listo para mostrar al usuario)
# ---------------------------------------------------------------------------

class ChatServiceError(Exception):
    """Error del flujo de chat con mensaje de usuario."""

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class TupperboxNoDetectado(ChatServiceError):
    """Modo 'Solo Tupper' activo y no se detectó el webhook de Tupperbox."""


class ErrorRenderizado(ChatServiceError):
    """Fallo generando o publicando las imágenes del chat."""


class ChatJsonInexistente(ChatServiceError):
    """El canal no tiene un chat generado (JSON) todavía."""


class SinMensajeOriginal(ChatServiceError):
    """El JSON del chat no registra el mensaje original a actualizar."""


class MensajeOriginalNoEncontrado(ChatServiceError):
    """El mensaje original fue borrado de Discord."""


class ActualizacionRechazada(ChatServiceError):
    """Discord rechazó la edición del mensaje renderizado."""


class ErrorInesperado(ChatServiceError):
    """Fallo no previsto durante la actualización."""


# ---------------------------------------------------------------------------
# Helpers de persistencia
# ---------------------------------------------------------------------------

def ruta_chat_json(canal_id: int) -> str:
    """Ruta del JSON persistente del chat de un canal."""
    return os.path.join(Config.EXPORT_FOLDER, f"chat_{canal_id}.json")


def guardar_json_disco(json_path: str, chat_json: dict) -> None:
    """Escribe el JSON del chat en disco (llamar bajo monitor_manager.file_lock)."""
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chat_json, f, indent=4, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Flujo de /chat generar
# ---------------------------------------------------------------------------

async def recolectar_mensajes(
    channel: discord.TextChannel,
    modo_captura: str,
    cantidad: int,
    bot_user_id: int,
    tupperbox_id: Optional[int] = None,
) -> list:
    """
    Escanea el historial del canal y devuelve hasta `cantidad` mensajes
    válidos según el modo de captura, en orden cronológico (más viejo primero).

    - 'TUPPER': solo mensajes de webhook cuyo autor sea el ID de Tupperbox.
    - cualquier otro ('TODO'): todos menos los del propio bot y los comandos "/".
    """
    mensajes = []
    if modo_captura == 'TUPPER':
        async for msg in channel.history(limit=Config.SEARCH_LIMIT):
            if msg.webhook_id and msg.author.id == tupperbox_id:
                mensajes.append(msg)
                if len(mensajes) >= cantidad:
                    break
    else:
        async for msg in channel.history(limit=Config.SEARCH_LIMIT):
            if msg.author.id != bot_user_id and not msg.content.startswith("/"):
                mensajes.append(msg)
                if len(mensajes) >= cantidad:
                    break
    mensajes.reverse()
    return mensajes


async def asegurar_personaje(
    nombre_crudo: str,
    tupper_tag: str,
    personaje_nombre: str,
    avatar_url: str,
    preguntar_lado: bool = False,
    resolver_lado: Optional[ResolverLado] = None,
) -> None:
    """
    Garantiza que el personaje exista en DB antes de renderizar.

    Orden de resolución:
    1. Tag normalizado (identidad canónica desde la unificación de tupper_tag).
    2. Legado: personaje guardado con el tag SIN normalizar por chats antiguos
       → se crea la fila normalizada copiando sus datos (lado, colores, owner,
       creator) una única vez.
    3. Personaje nuevo: se registra con lado 'I' o el que decida el callback
       interactivo `resolver_lado` (que ya degrada a 'I' ante fallos).
    """
    personaje = await obtener_personaje(tupper_tag)
    if personaje:
        return

    if nombre_crudo != tupper_tag:
        legado = await obtener_personaje(nombre_crudo)
        if legado:
            await guardar_personaje(
                tupper_tag,
                legado[0] or personaje_nombre,
                legado[1] or "I",
                legado[2] or avatar_url,
                legado[3] or "#FFFFFF",
                legado[4] or "#000000",
                owner_id=legado[5],
                creator_id=legado[6],
            )
            return

    lado = "I"
    if preguntar_lado and resolver_lado is not None:
        try:
            lado = (await resolver_lado(tupper_tag, personaje_nombre, avatar_url)) or "I"
        except Exception as e:
            logging.warning(f"ChatService: fallback a lado 'I' para '{tupper_tag}': {e}")
            lado = "I"

    await guardar_personaje(tupper_tag, personaje_nombre, lado, avatar_url)


async def construir_mensajes_json(
    mensajes: list,
    modo_captura: str,
    usuario_id: int,
    resolver_lado: Optional[ResolverLado] = None,
) -> list:
    """Convierte mensajes de Discord al formato JSON del chat, registrando personajes nuevos."""
    mensajes_json = []
    for msg in mensajes:
        # El tag se normaliza SIEMPRE en el punto de persistencia (mismo
        # criterio que chat_sync_service); el nombre visible sale del crudo.
        nombre_crudo = str(msg.author.name)
        tupper_tag = normalizar_tupper_tag(nombre_crudo)
        personaje_nombre = nombre_crudo.split(" - ")[0] if " - " in nombre_crudo else nombre_crudo
        avatar_url = str(msg.author.display_avatar.url)

        # En modo TUPPER se pregunta por todos; en modo TODO, solo por el autor del comando
        preguntar_lado = modo_captura == 'TUPPER' or msg.author.id == usuario_id
        await asegurar_personaje(
            nombre_crudo,
            tupper_tag,
            personaje_nombre,
            avatar_url,
            preguntar_lado=preguntar_lado,
            resolver_lado=resolver_lado,
        )

        mensajes_json.append({
            "Personaje": tupper_tag,
            "Mensaje": limpiar_formato_discord(msg.content),
            "Adjuntos": procesar_adjuntos_mensaje(msg),
        })
    return mensajes_json


async def generar_chat(
    *,
    channel: discord.TextChannel,
    solicitante: discord.User,
    bot_user_id: int,
    cantidad: int = 20,
    titulo: str = "chat",
    duracion_monitor: int = 5,
    resolver_lado: Optional[ResolverLado] = None,
    publicar: PublicarChat,
) -> dict:
    """
    Orquestación completa de /chat generar: escanea el historial del canal,
    asegura personajes, persiste el JSON, renderiza por lotes, publica el
    resultado y registra el monitor si duracion_monitor > 0.

    Lanza TupperboxNoDetectado o ErrorRenderizado (el cog los traduce a los
    mensajes de usuario). Devuelve el chat_json final.
    """
    modo_captura = await get_modo_captura(channel.guild.id)

    logging.info(f"GenerarChat: Iniciando en #{channel.name}. Modo: {modo_captura} | Cantidad: {cantidad}")

    tupperbox_id = None
    if modo_captura == 'TUPPER':
        tupperbox_id = await detectar_tupperbox_id(channel)
        if not tupperbox_id:
            raise TupperboxNoDetectado("❌ No se detectó Tupperbox y el modo es 'Solo Tupper'.")

    mensajes_a_procesar = await recolectar_mensajes(channel, modo_captura, cantidad, bot_user_id, tupperbox_id)
    mensajes_json = await construir_mensajes_json(
        mensajes_a_procesar, modo_captura, solicitante.id, resolver_lado
    )

    timestamp = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    titulo_real = titulo if titulo != "chat" else channel.name

    chat_json = {
        "Chat": {
            "titulo": titulo_real,
            "fecha": timestamp,  # clave canónica leída por image_service y chat_sync_service
            "id": f"chat_{channel.id}_{timestamp}",
            "mensajes": mensajes_json,
            "canal_id": channel.id,
            "mensaje_id": None,
            "duracion_monitor": duracion_monitor,
            "ultimo_id": mensajes_a_procesar[0].id if mensajes_a_procesar else None,
        }
    }

    json_path = ruta_chat_json(channel.id)
    async with monitor_manager.file_lock:
        guardar_json_disco(json_path, chat_json)

    try:
        rutas = await generar_imagenes_por_lotes(channel.id, chat_json, titulo_real)
        archivos = [discord.File(ruta) for ruta in rutas]
        msg = await publicar(
            f"📸 Chat renderizado: **{titulo_real}** ({len(mensajes_json)} mensajes)",
            archivos,
        )
        for ruta in rutas:
            if os.path.exists(ruta):
                os.remove(ruta)
    except ChatServiceError:
        raise
    except Exception as e:
        logging.error(f"Error generando imágenes: {e}")
        raise ErrorRenderizado("❌ Hubo un error generando las imágenes.") from e

    chat_json["Chat"]["mensaje_id"] = msg.id
    async with monitor_manager.file_lock:
        guardar_json_disco(json_path, chat_json)

    if duracion_monitor > 0:
        monitor_manager.registrar_monitor(
            channel=channel,
            message_id=msg.id,
            duracion_minutos=duracion_monitor,
            solicitante=solicitante,
            bot_user_id=bot_user_id,
        )

    return chat_json


# ---------------------------------------------------------------------------
# Flujo de /chat forzar
# ---------------------------------------------------------------------------

async def forzar_actualizacion(
    channel: discord.TextChannel,
    solicitante: discord.User,
    bot_user_id: int,
) -> bool:
    """
    Orquestación de /chat forzar: recarga el JSON del canal, incorpora los
    mensajes nuevos (actualizar_chat_logica), persiste, re-renderiza la última
    parte y edita el mensaje original.

    Devuelve True si se actualizó, False si no hubo cambios. Lanza
    ChatJsonInexistente, SinMensajeOriginal, MensajeOriginalNoEncontrado,
    ActualizacionRechazada o ErrorInesperado (el cog los traduce a embeds).
    """
    json_path = ruta_chat_json(channel.id)
    if not os.path.exists(json_path):
        raise ChatJsonInexistente("No se ha generado un chat para este canal.")

    async with monitor_manager.file_lock:
        with open(json_path, "r", encoding="utf-8") as f:
            chat_json = json.load(f)

    mensaje_id = chat_json["Chat"].get("mensaje_id")
    if not mensaje_id:
        raise SinMensajeOriginal("No se encontró el mensaje original para actualizar.")

    cambios = await actualizar_chat_logica(channel, chat_json, solicitante, bot_user_id)
    if not cambios:
        return False

    async with monitor_manager.file_lock:
        guardar_json_disco(json_path, chat_json)

    final_path = None
    try:
        final_path = await generar_imagen_segmentada(chat_json, channel.id)
        try:
            msg = await channel.fetch_message(mensaje_id)
            await msg.edit(content="✅ (Actualizado manual)", attachments=[discord.File(final_path)])
        except discord.NotFound:
            raise MensajeOriginalNoEncontrado("❌ No se encontró el mensaje original.") from None
    except MensajeOriginalNoEncontrado:
        raise
    except (discord.HTTPException, discord.DiscordException) as e:
        logging.error(f"ForzarChat: Discord rechazó la actualización en #{channel.name}: {e}", exc_info=True)
        raise ActualizacionRechazada(
            "Discord rechazó la actualización del chat (mensaje inválido o sin permisos)."
        ) from e
    except Exception as e:
        logging.error(f"ForzarChat: Error inesperado actualizando el chat: {e}", exc_info=True)
        raise ErrorInesperado("Hubo un error inesperado actualizando el chat renderizado.") from e
    finally:
        # Limpieza del PNG temporal tanto en éxito como en fallo
        if final_path and os.path.exists(final_path):
            try:
                os.remove(final_path)
            except OSError:
                pass

    return True

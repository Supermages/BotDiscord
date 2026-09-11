import os
import json
import asyncio
import datetime
import logging
from datetime import timezone
import discord
from core.config import Config
from services.chat_sync_service import actualizar_chat_logica
from services.image_service import generar_imagenes_por_lotes

class MonitorManager:
    """Gestiona el ciclo de vida de los monitores de canales en segundo plano."""
    def __init__(self):
        self.active_monitors = {}
        self.file_lock = asyncio.Lock()

    def esta_activo(self, canal_id: int) -> bool:
        return canal_id in self.active_monitors

    def obtener_monitores(self) -> dict:
        return self.active_monitors

    def detener_monitor(self, canal_id: int) -> bool:
        """Detiene y cancela la tarea del monitor en un canal específico."""
        monitor = self.active_monitors.pop(canal_id, None)
        if monitor:
            monitor["tarea"].cancel()
            logging.info(f"[MonitorManager] Monitor detenido en canal {canal_id}")
            return True
        return False

    def detener_todos(self):
        """Detiene todas las tareas activas (útil al apagar el bot)."""
        for canal_id, info in list(self.active_monitors.items()):
            info["tarea"].cancel()
        self.active_monitors.clear()
        logging.info("[MonitorManager] Todos los monitores han sido detenidos.")

    def registrar_monitor(self, channel: discord.TextChannel, message_id: int, duracion_minutos: int, solicitante: discord.User, bot_user_id: int):
        """Cancela un monitor previo en el canal si existe, e inicia uno nuevo."""
        if channel.id in self.active_monitors:
            self.detener_monitor(channel.id)

        hasta = datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=duracion_minutos)
        task = asyncio.create_task(
            self._monitor_loop(channel, message_id, hasta, solicitante, bot_user_id)
        )
        self.active_monitors[channel.id] = {
            "tarea": task,
            "hasta": hasta,
            "solicitante": solicitante
        }

    async def _monitor_loop(self, channel: discord.TextChannel, message_id: int, hasta: datetime.datetime, solicitante: discord.User, bot_user_id: int):
        """Bucle en segundo plano que revisa periódicamente nuevos mensajes en el canal."""
        logging.info(f"Monitor iniciado en #{channel.name} hasta {hasta.strftime('%H:%M:%S UTC')}")
        json_filename = os.path.join(Config.EXPORT_FOLDER, f"chat_{channel.id}.json")

        try:
            async with self.file_lock:
                if not os.path.exists(json_filename):
                    logging.warning(f"Monitor: No se encontró el archivo JSON {json_filename}")
                    return
                with open(json_filename, "r", encoding="utf-8") as f:
                    chat_json = json.load(f)

            while datetime.datetime.now(timezone.utc) < hasta:
                cambios = await actualizar_chat_logica(channel, chat_json, solicitante, bot_user_id)

                if cambios:
                    if len(chat_json["Chat"]["mensajes"]) > Config.MAX_MENSAJES_TOTAL:
                        chat_json["Chat"]["mensajes"] = chat_json["Chat"]["mensajes"][-Config.MAX_MENSAJES_TOTAL:]
                        logging.info(f"Monitor: Recortando historial a {Config.MAX_MENSAJES_TOTAL} mensajes.")

                    async with self.file_lock:
                        with open(json_filename, "w", encoding="utf-8") as f:
                            json.dump(chat_json, f, indent=4, ensure_ascii=False)

                    try:
                        rutas_imagenes = await generar_imagenes_por_lotes(channel.id, chat_json, chat_json["Chat"]["titulo"])
                        archivos_discord = [discord.File(path) for path in rutas_imagenes]

                        mensaje = await channel.fetch_message(message_id)
                        await mensaje.edit(
                            content=f"✅ (Actualizado {datetime.datetime.now().strftime('%H:%M')}) - {len(rutas_imagenes)} partes",
                            attachments=archivos_discord
                        )

                        for path in rutas_imagenes:
                            if os.path.exists(path):
                                os.remove(path)

                    except discord.NotFound:
                        logging.warning("El mensaje del monitor fue borrado de Discord. Deteniendo monitor.")
                        break
                    except Exception as e:
                        logging.error(f"Error en ciclo monitor #{channel.name}: {e}")

                await asyncio.sleep(60)

        except asyncio.CancelledError:
            logging.info(f"Tarea monitor cancelada en #{channel.name}")
        finally:
            self.active_monitors.pop(channel.id, None)
            logging.info(f"Monitor finalizado en #{channel.name}")

# Instancia global del gestor de monitores
monitor_manager = MonitorManager()

import os
import logging
from core.config import Config
from renderer.captura import generar_captura

async def generar_imagenes_por_lotes(channel_id, chat_json, titulo_base):
    """
    Divide los mensajes del chat en lotes de tamaño Config.MENSAJES_POR_IMAGEN
    y genera una captura para cada segmento.
    """
    mensajes = chat_json["Chat"]["mensajes"]
    chunk_size = Config.MENSAJES_POR_IMAGEN
    chunks = [mensajes[i:i + chunk_size] for i in range(0, len(mensajes), chunk_size)]
    
    rutas_archivos = []
    
    for i, chunk in enumerate(chunks):
        parte_json = {
            "Chat": {
                "titulo": f"{titulo_base} (Parte {i+1}/{len(chunks)})",
                "fecha": chat_json["Chat"]["fecha"],
                "mensajes": chunk
            }
        }
        
        temp_path = await generar_captura(parte_json)
        final_path = os.path.join(Config.EXPORT_FOLDER, f"chat_{channel_id}_part{i+1}.png")
        
        if os.path.exists(final_path):
            os.remove(final_path)
            
        os.replace(temp_path, final_path)
        rutas_archivos.append(final_path)
        
    return rutas_archivos

async def generar_imagen_segmentada(chat_json, canal_id):
    """
    Genera la imagen de la última parte actualizada para actualizaciones rápidas.
    """
    chunk_size = Config.MENSAJES_POR_IMAGEN
    mensajes = chat_json["Chat"]["mensajes"]
    partes = [mensajes[i:i + chunk_size] for i in range(0, len(mensajes), chunk_size)]

    if not partes:
        raise ValueError("No hay mensajes para generar imagen")

    if len(partes) > 1:
        primera_parte = {
            "Chat": {
                "titulo": chat_json["Chat"]["titulo"] + " (parte 1)",
                "fecha": chat_json["Chat"]["fecha"],
                "mensajes": partes[0]
            }
        }
        imagen_path_1 = await generar_captura(primera_parte)
        static_path = os.path.join(Config.EXPORT_FOLDER, f"chat_{canal_id}_parte1.png")
        os.replace(imagen_path_1, static_path)
        logging.info(f"[📸] Imagen estática guardada en {static_path}")

    ultima_parte = {
        "Chat": {
            "titulo": chat_json["Chat"]["titulo"] + f" (actualizado parte {len(partes)})",
            "fecha": chat_json["Chat"]["fecha"],
            "mensajes": partes[-1]
        }
    }

    imagen_path = await generar_captura(ultima_parte)
    final_path = os.path.join(Config.EXPORT_FOLDER, f"chat_{canal_id}.png")
    os.replace(imagen_path, final_path)
    return final_path

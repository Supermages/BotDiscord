import os
import logging
from core.config import Config
from renderer.captura import generar_captura

def dividir_en_lotes_inteligentes(mensajes: list, max_por_lote: int, peso_maximo: float = 14.0) -> list:
    """
    Divide los mensajes de forma adaptativa. Los mensajes largos o con imágenes
    ocupan más peso visual, evitando que una imagen resultante sea excesivamente alta.
    """
    chunks = []
    chunk_actual = []
    peso_actual = 0.0

    for msg in mensajes:
        texto = msg.get("Mensaje", "")
        adjuntos = msg.get("Adjuntos", [])

        # Peso base para un mensaje corto
        peso = 1.0

        # Mensajes extensos (rol, párrafos) añaden peso por altura
        if len(texto) > 120:
            peso += min(4.0, len(texto) / 100.0)

        # Imágenes, stickers o GIFs añaden peso vertical sustancial
        if adjuntos:
            peso += len(adjuntos) * 2.5

        # Si superamos el peso máximo o el límite por lote, cerramos lote (siempre que ya tengamos al menos 2 mensajes)
        if (peso_actual + peso > peso_maximo or len(chunk_actual) >= max_por_lote) and len(chunk_actual) >= 2:
            chunks.append(chunk_actual)
            chunk_actual = [msg]
            peso_actual = peso
        else:
            chunk_actual.append(msg)
            peso_actual += peso

    if chunk_actual:
        chunks.append(chunk_actual)

    return chunks

async def generar_imagenes_por_lotes(channel_id, chat_json, titulo_base):
    """
    Genera capturas segmentadas utilizando división inteligente por peso visual.
    """
    mensajes = chat_json["Chat"]["mensajes"]
    max_chunk = Config.MENSAJES_POR_IMAGEN
    chunks = dividir_en_lotes_inteligentes(mensajes, max_por_lote=max_chunk)
    
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
    max_chunk = Config.MENSAJES_POR_IMAGEN
    mensajes = chat_json["Chat"]["mensajes"]
    partes = dividir_en_lotes_inteligentes(mensajes, max_por_lote=max_chunk)

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

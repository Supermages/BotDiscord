import re

def limpiar_formato_discord(texto: str) -> str:
    """
    Procesa emojis personalizados de Discord a etiquetas <img> y
    elimina sintaxis pesada de Markdown para el renderizado en HTML.
    """
    if not texto:
        return ""

    # 1. Procesar Emojis Personalizados (<:nombre:ID> y <a:nombre:ID>)
    def reemplazo_emoji(match):
        animado, nombre, id_emoji = match.groups()
        ext = "gif" if animado else "png"
        url = f"https://cdn.discordapp.com/emojis/{id_emoji}.{ext}"
        return f'<img src="{url}" alt=":{nombre}:" style="width: 22px; height: 22px; vertical-align: middle; object-fit: contain;">'

    texto = re.sub(r'<(a?):(\w+):(\d+)>', reemplazo_emoji, texto)

    # 2. Limpieza de Markdown estándar
    texto = re.sub(r'```.*?```', '', texto, flags=re.DOTALL)
    texto = re.sub(r'`([^`]*)`', r'\1', texto)
    texto = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', texto)
    texto = re.sub(r'\*\*([^*]+)\*\*', r'\1', texto)
    texto = re.sub(r'\*([^*]+)\*', r'\1', texto)
    texto = re.sub(r'__([^_]+)__', r'\1', texto)
    texto = re.sub(r'~~([^~]+)~~', r'\1', texto)
    texto = re.sub(r'\|\|([^|]+)\|\|', r'\1', texto)
    
    return texto.strip()

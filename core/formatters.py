import re

def limpiar_formato_discord(texto: str) -> str:
    """
    Procesa emojis personalizados de Discord, encabezados (#, ##, ###),
    citas, formato de texto enriquecido (negrita, cursiva, tachado) y
    elimina enlaces de GIFs (Tenor/Giphy) que ya se muestran visualmente.
    """
    if not texto:
        return ""

    # 1. Eliminar URLs de Tenor / Giphy que Discord embebe automáticamente
    texto = re.sub(r'https?://(?:www\.)?tenor\.com/view/[^\s]+', '', texto)
    texto = re.sub(r'https?://(?:media\.)?giphy\.com/gifs/[^\s]+', '', texto)

    # 2. Procesar Emojis Personalizados de Discord (<:nombre:ID> y <a:nombre:ID>)
    def reemplazo_emoji(match):
        animado, nombre, id_emoji = match.groups()
        ext = "gif" if animado else "png"
        url = f"https://cdn.discordapp.com/emojis/{id_emoji}.{ext}"
        return f'<img class="custom-emoji" src="{url}" alt=":{nombre}:" style="width: 22px; height: 22px; vertical-align: middle; object-fit: contain; margin: 0 2px;">'

    texto = re.sub(r'<(a?):(\w+):(\d+)>', reemplazo_emoji, texto)

    # 3. Encabezados de Discord (#, ##, ###)
    # ### Encabezado pequeño
    texto = re.sub(
        r'(?m)^\s*###\s+(.*)$', 
        r'<div style="font-size: 1.05em; font-weight: 700; margin: 4px 0 2px 0;">\1</div>', 
        texto
    )
    # ## Encabezado mediano
    texto = re.sub(
        r'(?m)^\s*##\s+(.*)$', 
        r'<div style="font-size: 1.18em; font-weight: 700; margin: 6px 0 2px 0;">\1</div>', 
        texto
    )
    # # Encabezado grande
    texto = re.sub(
        r'(?m)^\s*#\s+(.*)$', 
        r'<div style="font-size: 1.35em; font-weight: 800; margin: 8px 0 3px 0;">\1</div>', 
        texto
    )

    # 4. Citas y Subtexto
    # Citas (> texto)
    texto = re.sub(
        r'(?m)^\s*>\s+(.*)$', 
        r'<div style="border-left: 3px solid rgba(120, 120, 120, 0.6); padding-left: 8px; margin: 3px 0; font-style: italic; opacity: 0.9;">\1</div>', 
        texto
    )
    # Subtexto (-# texto)
    texto = re.sub(
        r'(?m)^\s*-#\s+(.*)$', 
        r'<div style="font-size: 0.82em; opacity: 0.7; margin: 2px 0;">\1</div>', 
        texto
    )

    # 5. Formato de Texto Enriquecido
    # Bloques de código (conservar contenido limpio)
    texto = re.sub(r'```.*?```', '', texto, flags=re.DOTALL)
    texto = re.sub(r'`([^`]*)`', r'<code style="background: rgba(0,0,0,0.3); padding: 1px 4px; border-radius: 4px; font-family: monospace;">\1</code>', texto)
    
    # Negrita + Cursiva (***texto***)
    texto = re.sub(r'\*\*\*([^*]+)\*\*\*', r'<b><i>\1</i></b>', texto)
    # Negrita (**texto**)
    texto = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', texto)
    # Cursiva (*texto*)
    texto = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', texto)
    # Subrayado (__texto__)
    texto = re.sub(r'__([^_]+)__', r'<u>\1</u>', texto)
    # Tachado (~~texto~~)
    texto = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', texto)
    # Spoilers (||texto||)
    texto = re.sub(r'\|\|([^|]+)\|\|', r'<span style="background-color: rgba(0,0,0,0.7); border-radius: 3px; padding: 0 4px; color: transparent;" title="Spoiler">\1</span>', texto)

    return texto.strip()

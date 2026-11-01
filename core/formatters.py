import html
import re

# Whitelist fija de etiquetas que el pipeline de render puede generar/permitir.
_TAGS_PERMITIDOS = {"img", "div", "br", "b", "i", "u", "s", "span", "code"}


def escapar_html(texto: str) -> str:
    """
    Escapa los caracteres con significado HTML (&, <, >, ", ') para que
    cualquier contenido de usuario se muestre como texto literal y nunca
    como etiquetas o atributos ejecutables en la página de render.
    """
    if not texto:
        return ""
    return html.escape(str(texto), quote=True)


def sanitizar_html_render(texto: str) -> str:
    """
    Capa de defensa adicional del render: elimina cualquier etiqueta HTML
    fuera de la whitelist fija (conservando su contenido como texto), los
    atributos `on*` (onerror, onclick...) y los esquemas peligrosos
    (javascript:, vbscript:, data:) en atributos src/href.
    """
    if not texto:
        return ""

    def _etiqueta(match):
        cierre, nombre, attrs = match.group(1), match.group(2), match.group(3)
        if nombre.lower() not in _TAGS_PERMITIDOS:
            return ""
        # Atributos on* fuera
        attrs = re.sub(
            r'\s+on[a-zA-Z]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)',
            '',
            attrs,
            flags=re.IGNORECASE
        )
        # Esquemas peligrosos en src/href fuera
        attrs = re.sub(
            r'\s+(?:src|href)\s*=\s*(?:"(?:javascript|vbscript|data):[^"]*"|\'(?:javascript|vbscript|data):[^\']*\'|(?:javascript|vbscript|data):[^\s>]+)',
            '',
            attrs,
            flags=re.IGNORECASE
        )
        return f'<{cierre}{nombre.lower()}{attrs}>'

    return re.sub(
        r'<(/?)([a-zA-Z][a-zA-Z0-9]*)((?:"[^"]*"|\'[^\']*\'|[^>"\'])*)>',
        _etiqueta,
        texto
    )


def limpiar_formato_discord(texto: str) -> str:
    """
    Procesa emojis personalizados de Discord, encabezados (#, ##, ###),
    citas, formato de texto enriquecido (negrita, cursiva, tachado) y
    elimina enlaces de GIFs (Tenor/Giphy) que ya se muestran visualmente.

    Seguridad: TODO el contenido de usuario se escapa a HTML inerte ANTES de
    aplicar las transformaciones, por lo que las únicas etiquetas que puede
    contener el resultado son las de la whitelist fija generadas aquí dentro.
    """
    if not texto:
        return ""

    # 1. Eliminar URLs de Tenor / Giphy que Discord embebe automáticamente
    texto = re.sub(r'https?://(?:www\.)?tenor\.com/view/[^\s]+', '', texto)
    texto = re.sub(r'https?://(?:media\.)?giphy\.com/gifs/[^\s]+', '', texto)

    # 2. ESCAPADO: todo el contenido de usuario pasa a texto HTML-inerte
    #    (&, <, >, ", ' → entidades). A partir de aquí, los únicos "<" literales
    #    que quedan en la cadena son los que generan nuestras transformaciones.
    texto = escapar_html(texto)

    # 3. Procesar Emojis Personalizados de Discord (<:nombre:ID> y <a:nombre:ID>)
    #    Tras el escapado llegan como &lt;:nombre:ID&gt;
    def reemplazo_emoji(match):
        animado, nombre, id_emoji = match.groups()
        ext = "gif" if animado else "png"
        url = escapar_html(f"https://cdn.discordapp.com/emojis/{id_emoji}.{ext}")
        alt = escapar_html(f":{nombre}:")
        return f'<img class="custom-emoji" src="{url}" alt="{alt}" style="width: 22px; height: 22px; vertical-align: middle; object-fit: contain; margin: 0 2px;">'

    texto = re.sub(r'&lt;(a?):(\w+):(\d+)&gt;', reemplazo_emoji, texto)

    # 4. Encabezados de Discord (#, ##, ###)
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

    # 5. Citas y Subtexto
    # Citas (> texto). Tras el escapado, ">" llega como "&gt;"
    texto = re.sub(
        r'(?m)^\s*&gt;\s+(.*)$',
        r'<div style="border-left: 3px solid rgba(120, 120, 120, 0.6); padding-left: 8px; margin: 3px 0; font-style: italic; opacity: 0.9;">\1</div>',
        texto
    )
    # Subtexto (-# texto)
    texto = re.sub(
        r'(?m)^\s*-#\s+(.*)$',
        r'<div style="font-size: 0.82em; opacity: 0.7; margin: 2px 0;">\1</div>',
        texto
    )

    # 6. Formato de Texto Enriquecido (contenido ya escapado)
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

    # 7. Pase final de defensa: nada fuera de la whitelist debe sobrevivir.
    return sanitizar_html_render(texto.strip())

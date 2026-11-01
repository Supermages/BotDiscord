import unicodedata
import re

def normalizar_texto(texto: str) -> str:
    """
    Normaliza texto eliminando diacríticos, símbolos decorativos y fuentes especiales
    para permitir búsquedas insensibles a caracteres Unicode fancy.
    Ej: '★ 𝕬𝖗𝖙𝖚𝖗𝖔 ★' -> 'arturo', '【Elena】' -> 'elena', 'René' -> 'rene'
    """
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(texto))
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    lower = sin_tildes.lower()
    alfanumerico = re.sub(r'[^a-z0-9\s]', '', lower)
    return " ".join(alfanumerico.split())

def limpiar_termino_busqueda(texto: str) -> str:
    """
    Limpia prefijos de autocompletado (como emojis 🛡️, 📦, ⭐) y sufijos
    de información como (@dueño), (ID: ...), (Sin vincular), (Activo), etc.
    Esto permite que si Discord envía la etiqueta visible del Choice en vez del value,
    la búsqueda reconozca el nombre real del personaje.
    """
    if not texto:
        return ""
    # Quitar emojis y espacios iniciales
    limpio = re.sub(r'^[🛡️📦⭐✨\s]+', '', str(texto)).strip()
    # Quitar etiquetas finales entre paréntesis (ej: ' (@Sayaka...)', ' (ID: 12345)', ' (Sin vincular)')
    limpio = re.sub(r'\s*\((?:@[^)]+|ID:\s*[^)]+|Sin vincular|Activo|Reserva|En Reserva)\)\s*$', '', limpio).strip()
    return limpio

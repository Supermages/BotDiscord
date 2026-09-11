import re
import random
import logging
import sqlite3
import lupa
from lupa import LuaRuntime
from core.config import Config
from core.database import limpiar_termino_busqueda, normalizar_texto

logger = logging.getLogger(__name__)

def parsear_tirada_dados(expr: str) -> int:
    """
    Evalúa expresiones sencillas de dados como '1d20+5', '2d6', 'd100', '1d20-2'.
    """
    clean = str(expr).replace(" ", "").lower()
    match = re.match(r'^(\d*)d(\d+)([+-]\d+)?$', clean)
    if not match:
        try:
            return int(expr)
        except ValueError:
            return 0
    num_dados = int(match.group(1)) if match.group(1) else 1
    caras = int(match.group(2))
    modificador = int(match.group(3)) if match.group(3) else 0

    total = sum(random.randint(1, caras) for _ in range(num_dados)) + modificador
    return total

class LuaEngine:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _resolver_personaje_tag(self, char_input: str) -> str | None:
        """Resuelve el tupper_tag canónico del personaje a partir de nombre, tag o mención."""
        if not char_input:
            return None
        char_limpio = limpiar_termino_busqueda(char_input)

        with self._get_db() as conn:
            for t in [char_input, char_limpio]:
                if not t:
                    continue
                row = conn.execute(
                    'SELECT tupper_tag FROM Personaje_Tabla WHERE LOWER(tupper_tag) = LOWER(?) OR LOWER(nombre) = LOWER(?) LIMIT 1',
                    (t, t)
                ).fetchone()
                if row:
                    return row[0]

            target_norm = normalizar_texto(char_limpio) or normalizar_texto(char_input)
            if target_norm:
                rows = conn.execute('SELECT tupper_tag, nombre FROM Personaje_Tabla').fetchall()
                for r in rows:
                    if normalizar_texto(r[1]) == target_norm or normalizar_texto(r[0]) == target_norm:
                        return r[0]
                for r in rows:
                    p_nom = normalizar_texto(r[1])
                    p_tag = normalizar_texto(r[0])
                    if (p_nom and target_norm in p_nom) or (p_tag and target_norm in p_tag):
                        return r[0]

        return char_input

    def _resolver_item_id(self, item_input: str) -> str:
        """Resuelve el item_id canónico en el catálogo maestro."""
        if not item_input:
            return ""
        clean = item_input.strip()
        slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', clean.lower())

        with self._get_db() as conn:
            row = conn.execute(
                'SELECT item_id FROM Items_Catalogo WHERE LOWER(item_id) = LOWER(?) OR LOWER(nombre) = LOWER(?) OR LOWER(item_id) = ? LIMIT 1',
                (clean, clean, slug)
            ).fetchone()
            if row:
                return row[0]

        return slug

    def validar_sintaxis(self, script: str) -> tuple[bool, str]:
        """Comprueba si un fragmento de código Lua es sintácticamente válido sin ejecutarlo."""
        if not script or not script.strip():
            return True, "Script vacío (se usará lógica por defecto)."
        try:
            lua = LuaRuntime()
            lua.compile(script)
            return True, "Sintaxis válida."
        except Exception as e:
            return False, f"Error de sintaxis Lua: {e}"

    def ejecutar_script(
        self,
        script: str,
        char_input: str,
        item_input: str,
        cantidad: int = 1,
        user_id: str = ""
    ) -> tuple[bool, str, list[str]]:
        """
        Ejecuta el script Lua en un entorno Sandbox seguro.
        Retorna:
          - exito: bool (si la ejecución fue exitosa y no fue abortada con return false)
          - mensaje: str (texto acumulado con reply())
          - items_mostrados: list[str] (ítems llamados con display_item())
        """
        if not script or not script.strip():
            return True, "", []

        lua = LuaRuntime(unpack_returned_tuples=True)
        g = lua.globals()

        # Deshabilitar librerías peligrosas
        for peligroso in ['os', 'io', 'package', 'dofile', 'loadfile', 'load', 'debug']:
            g[peligroso] = None

        char_tag = self._resolver_personaje_tag(char_input) or char_input
        item_id = self._resolver_item_id(item_input) or item_input

        # Obtener identificador original o nombre del ítem en el catálogo
        with self._get_db() as conn:
            row_it = conn.execute(
                'SELECT item_id, nombre FROM Items_Catalogo WHERE LOWER(item_id) = LOWER(?) OR LOWER(nombre) = LOWER(?) LIMIT 1',
                (item_id, item_id)
            ).fetchone()
            item_db_id = row_it[0] if row_it else item_id
            item_db_nombre = row_it[1] if row_it else item_input

        # Detectar el casing o formato que el usuario escribió en el script (ej: 'Ticket-General-S')
        # para que coincida exactamente en comparaciones de igualdad 'item == ...'
        injected_item = item_input
        patrones = [
            r'(?:item|item_id|tipo_pocion)\s*==\s*["\']([^"\']+)["\']',
            r'["\']([^"\']+)["\']\s*==\s*(?:item|item_id|tipo_pocion)',
            r'\[["\']([^"\']+)["\']\]\s*='
        ]
        candidatos = []
        for pat in patrones:
            candidatos.extend(re.findall(pat, script))

        target_norm = item_db_id.lower().replace("-", "").replace("_", "").replace(" ", "")
        for cand in candidatos:
            cand_norm = cand.lower().replace("-", "").replace("_", "").replace(" ", "")
            if cand_norm == target_norm or self._resolver_item_id(cand).lower() == item_db_id.lower():
                injected_item = cand
                break

        replies = []
        displayed_items = []
        mutaciones = [0]

        def get_inventory_count(c_in, it_in):
            c_tag = self._resolver_personaje_tag(str(c_in)) or str(c_in)
            i_id = self._resolver_item_id(str(it_in)) or str(it_in)
            with self._get_db() as conn:
                row = conn.execute(
                    'SELECT cantidad FROM Inventarios WHERE personaje_id = ? AND item_id = ?',
                    (c_tag, i_id)
                ).fetchone()
                return int(row[0]) if row else 0

        def take_character_item(c_in, it_in, count):
            c_tag = self._resolver_personaje_tag(str(c_in)) or str(c_in)
            i_id = self._resolver_item_id(str(it_in)) or str(it_in)
            cnt = int(count)
            if cnt <= 0:
                return False

            with self._get_db() as conn:
                row = conn.execute(
                    'SELECT cantidad FROM Inventarios WHERE personaje_id = ? AND item_id = ?',
                    (c_tag, i_id)
                ).fetchone()
                actual = int(row[0]) if row else 0
                if actual < cnt:
                    return False

                nueva = actual - cnt
                if nueva <= 0:
                    conn.execute('DELETE FROM Inventarios WHERE personaje_id = ? AND item_id = ?', (c_tag, i_id))
                else:
                    conn.execute('UPDATE Inventarios SET cantidad = ? WHERE personaje_id = ? AND item_id = ?', (nueva, c_tag, i_id))
                conn.commit()

            mutaciones[0] += 1
            return True

        def give_character_item(c_in, it_in, count):
            c_tag = self._resolver_personaje_tag(str(c_in)) or str(c_in)
            i_id = self._resolver_item_id(str(it_in)) or str(it_in)
            cnt = int(count)
            if cnt <= 0:
                return False

            with self._get_db() as conn:
                row = conn.execute(
                    'SELECT cantidad FROM Inventarios WHERE personaje_id = ? AND item_id = ?',
                    (c_tag, i_id)
                ).fetchone()
                if row:
                    conn.execute('UPDATE Inventarios SET cantidad = cantidad + ? WHERE personaje_id = ? AND item_id = ?', (cnt, c_tag, i_id))
                else:
                    conn.execute('INSERT INTO Inventarios (personaje_id, item_id, cantidad) VALUES (?, ?, ?)', (c_tag, i_id, cnt))
                conn.commit()

            mutaciones[0] += 1
            return True

        def reply(msg):
            replies.append(str(msg))

        def display_item(it_in):
            it_id = self._resolver_item_id(str(it_in)) or str(it_in)
            if it_id not in displayed_items:
                displayed_items.append(it_id)

        def choice(*args):
            if not args:
                return None
            first = args[0]
            if hasattr(first, 'values'):
                opts = list(first.values())
            elif hasattr(first, '__iter__') and not isinstance(first, (str, bytes)):
                opts = list(first)
            else:
                opts = list(args)
            return random.choice(opts) if opts else None

        def roll(expr):
            return parsear_tirada_dados(str(expr))

        def lua_random(min_val, max_val):
            return random.randint(int(min_val), int(max_val))

        # Inyectar variables
        g['char'] = char_tag
        g['item'] = injected_item
        g['item_id'] = item_id
        g['tipo_pocion'] = injected_item
        g['amount'] = cantidad
        g['cantidad_usar'] = cantidad
        g['cantidad'] = cantidad
        g['user_id'] = str(user_id)

        # Inyectar funciones
        g['get_inventory_count'] = get_inventory_count
        g['take_character_item'] = take_character_item
        g['give_character_item'] = give_character_item
        g['reply'] = reply
        g['display_item'] = display_item
        g['choice'] = choice
        g['roll'] = roll
        g['random'] = lua_random

        try:
            res = lua.execute(script)
            if res is False:
                msg_err = "\n".join(replies) if replies else "La acción fue cancelada por el script."
                return False, msg_err, displayed_items

            if len(replies) == 0 and mutaciones[0] == 0:
                return False, f"⚠️ El script se ejecutó pero no coincidió con el ítem '{injected_item}' ni realizó ninguna acción. Comprueba las condiciones del script.", displayed_items

            msg_ok = "\n".join(replies) if replies else "Ítem utilizado con éxito."
            return True, msg_ok, displayed_items

        except Exception as e:
            logger.error(f"[Lua Engine Error] Error ejecutando script para '{item_id}': {e}", exc_info=True)
            return False, f"⚠️ Error en la ejecución del script Lua: `{e}`", displayed_items

lua_engine = LuaEngine()

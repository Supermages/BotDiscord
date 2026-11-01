import re
import random
import asyncio
import logging
import sqlite3
from contextlib import closing
import lupa
from lupa import LuaRuntime
from core.config import Config
from core.database import limpiar_termino_busqueda, normalizar_texto

logger = logging.getLogger(__name__)

# --- Límites de seguridad del sandbox Lua ---
# Presupuesto máximo de instrucciones Lua por ejecución (evita bucles infinitos
# consumiendo CPU del bot). Se aplica con debug.sethook antes de anular 'debug'.
LUA_MAX_INSTRUCCIONES = 10_000_000
# Cada cuántas instrucciones llama el hook al contador (menor = más fino).
LUA_HOOK_CADA = 50_000
# Tiempo máximo total de ejecución del script (red de seguridad adicional;
# se aplica en la variante async con un hilo de trabajo).
LUA_TIMEOUT_SEGUNDOS = 15

def parsear_tirada_dados(expr: str) -> int:
    """
    Evalúa expresiones de dados como '1d20+5', '2d6', 'd100', '1d20-2', '2d6+1d4+3'.
    """
    try:
        from services.dice_service import ejecutar_tirada
        return ejecutar_tirada(str(expr)).total
    except Exception:
        try:
            return int(expr)
        except ValueError:
            return 0

class LuaEngine:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH

    def _get_db(self) -> sqlite3.Connection:
        """Conexión síncrona con los PRAGMAs de integridad/concurrencia aplicados."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=10000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _resolver_personaje_tag(self, char_input: str) -> str | None:
        """Resuelve el tupper_tag canónico del personaje a partir de nombre, tag o mención."""
        if not char_input:
            return None
        char_limpio = limpiar_termino_busqueda(char_input)

        with closing(self._get_db()) as conn:
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

        with closing(self._get_db()) as conn:
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

        Seguridad:
          - Librerías peligrosas anuladas (os, io, package, load, debug, ...).
          - Presupuesto de instrucciones: un bucle infinito aborta el script en
            lugar de colgar el bot (hook de conteo instalado antes de anular 'debug').
          - Las mutaciones de inventario respetan las FOREIGN KEY: no se pueden
            dar ítems que no existan en el catálogo.
        """
        if not script or not script.strip():
            return True, "", []

        lua = LuaRuntime(unpack_returned_tuples=True)
        g = lua.globals()

        # Instalar el presupuesto de instrucciones ANTES de anular 'debug'.
        # El hook resta trabajo en cada disparo y aborta el script al agotarse.
        presupuesto = [LUA_MAX_INSTRUCCIONES]

        def _hook_presupuesto(*_args):
            presupuesto[0] -= LUA_HOOK_CADA
            if presupuesto[0] <= 0:
                raise RuntimeError(f"Presupuesto de instrucciones Lua excedido ({LUA_MAX_INSTRUCCIONES:,})")

        g['_py_hook_presupuesto'] = _hook_presupuesto
        try:
            # debug.sethook exige una función Lua nativa: envolvemos el callable
            # de Python en una closure Lua que lo invoca en cada disparo.
            lua.execute(f'''do
                local _pyf = _py_hook_presupuesto
                local _wrapper = function() _pyf() end
                debug.sethook(_wrapper, "", {LUA_HOOK_CADA})
            end''')
        except Exception as e:
            # Fail-closed: sin presupuesto de instrucciones no se ejecuta nada,
            # porque un bucle infinito colgaría el bot completo.
            logger.error(f"[Lua Engine] No se pudo instalar el hook de presupuesto: {e}")
            g['_py_hook_presupuesto'] = None
            return False, "⚠️ No se pudo inicializar el sandbox (presupuesto de instrucciones). Consulta los logs.", []
        finally:
            g['_py_hook_presupuesto'] = None

        # Deshabilitar librerías peligrosas
        for peligroso in ['os', 'io', 'package', 'require', 'dofile', 'loadfile', 'load', 'debug']:
            g[peligroso] = None

        char_tag = self._resolver_personaje_tag(char_input) or char_input
        item_id = self._resolver_item_id(item_input) or item_input

        # Obtener identificador original o nombre del ítem en el catálogo
        with closing(self._get_db()) as conn:
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
            with closing(self._get_db()) as conn:
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

            try:
                with closing(self._get_db()) as conn:
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
            except sqlite3.Error as e:
                logger.error(f"[Lua Engine] take_character_item({c_tag}, {i_id}) fallo: {e}")
                return False

            mutaciones[0] += 1
            return True

        def give_character_item(c_in, it_in, count):
            c_tag = self._resolver_personaje_tag(str(c_in)) or str(c_in)
            i_id = self._resolver_item_id(str(it_in)) or str(it_in)
            cnt = int(count)
            if cnt <= 0:
                return False

            try:
                with closing(self._get_db()) as conn:
                    row = conn.execute(
                        'SELECT cantidad FROM Inventarios WHERE personaje_id = ? AND item_id = ?',
                        (c_tag, i_id)
                    ).fetchone()
                    if row:
                        conn.execute('UPDATE Inventarios SET cantidad = cantidad + ? WHERE personaje_id = ? AND item_id = ?', (cnt, c_tag, i_id))
                    else:
                        # Las FOREIGN KEY están activas: solo se puede dar un ítem
                        # que exista en el catálogo maestro.
                        conn.execute('INSERT INTO Inventarios (personaje_id, item_id, cantidad) VALUES (?, ?, ?)', (c_tag, i_id, cnt))
                    conn.commit()
            except sqlite3.IntegrityError:
                logger.warning(f"[Lua Engine] give_character_item rechazado (FK): '{i_id}' no existe en el catálogo.")
                return False
            except sqlite3.Error as e:
                logger.error(f"[Lua Engine] give_character_item({c_tag}, {i_id}) fallo: {e}")
                return False

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

    async def ejecutar_script_async(
        self,
        script: str,
        char_input: str,
        item_input: str,
        cantidad: int = 1,
        user_id: str = ""
    ) -> tuple[bool, str, list[str]]:
        """
        Variante async de ejecutar_script: corre el script en un hilo de trabajo
        con un timeout, para no bloquear el event loop del bot mientras se
        ejecuta Lua o se toca SQLite de forma síncrona.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self.ejecutar_script,
                    script, char_input, item_input, cantidad, user_id
                ),
                timeout=LUA_TIMEOUT_SEGUNDOS
            )
        except asyncio.TimeoutError:
            logger.error(f"[Lua Engine] Script para '{item_input}' abortado por timeout ({LUA_TIMEOUT_SEGUNDOS}s).")
            return False, f"⚠️ El script fue abortado: superó el límite de {LUA_TIMEOUT_SEGUNDOS} s de ejecución.", []

lua_engine = LuaEngine()

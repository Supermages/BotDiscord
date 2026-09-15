import os
import sys
import ast
import asyncio
import logging
import importlib
from pathlib import Path
import discord
from discord.ext import commands
from core.config import Config, BASE_DIR

logger = logging.getLogger("HotReload")

WATCH_DIRS = ["cogs", "services", "ui", "core", "renderer"]

class HotReloadManager:
    """
    Gestiona la monitorización y recarga en caliente de Cogs, Servicios, Vistas y Módulos
    en tiempo real sin reiniciar el proceso de Discord ni Playwright.
    
    Incluye:
    - Verificación previa de sintaxis con AST para evitar crasheos por archivos incompletos.
    - Ventana de enfriamiento (debounce) para agrupar guardados múltiples.
    - Recarga en cascada de dependencias internas.
    - Aislamiento total de excepciones.
    """
    def __init__(self, bot: commands.Bot = None):
        self.bot = bot
        self._mtimes: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._running: bool = False
        self._lock = asyncio.Lock()
        self.watch_dirs = [os.path.normpath(os.path.join(BASE_DIR, d)) for d in WATCH_DIRS]

    def set_bot(self, bot: commands.Bot):
        self.bot = bot

    def start(self):
        """Inicia el monitor en segundo plano si no está ya activo."""
        if self._running or self._task is not None:
            return
        self._running = True
        self._init_mtimes()
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("[HotReload] 🚀 Sistema de recarga en caliente activo y vigilando cambios.")

    def stop(self):
        """Detiene el monitor en segundo plano."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[HotReload] 🛑 Sistema de recarga en caliente detenido.")

    def _init_mtimes(self):
        """Inicializa las marcas de tiempo de los archivos observados."""
        self._mtimes.clear()
        for root_dir in self.watch_dirs:
            if not os.path.exists(root_dir):
                continue
            for root, _, files in os.walk(root_dir):
                if "__pycache__" in root:
                    continue
                for f in files:
                    if f.endswith(".py"):
                        fpath = os.path.normpath(os.path.join(root, f))
                        try:
                            self._mtimes[fpath] = os.path.getmtime(fpath)
                        except OSError:
                            pass

    async def _watch_loop(self):
        """Bucle periódico asíncrono que comprueba marcas de tiempo cada 1 segundo."""
        while self._running:
            try:
                await asyncio.sleep(1.0)
                cambios = self._check_file_changes()
                if cambios:
                    # Enfriamiento (debounce) para que terminen de escribirse los archivos
                    await asyncio.sleep(1.2)
                    async with self._lock:
                        await self._process_changes(cambios)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[HotReload] ⚠️ Error en bucle de vigilancia: {e}")

    def _check_file_changes(self) -> list[str]:
        """Detecta archivos .py nuevos o con fecha de modificación posterior."""
        modificados = []
        archivos_actuales = set()

        for root_dir in self.watch_dirs:
            if not os.path.exists(root_dir):
                continue
            for root, _, files in os.walk(root_dir):
                if "__pycache__" in root:
                    continue
                for f in files:
                    if f.endswith(".py"):
                        fpath = os.path.normpath(os.path.join(root, f))
                        archivos_actuales.add(fpath)
                        try:
                            mtime = os.path.getmtime(fpath)
                        except OSError:
                            continue

                        prev_mtime = self._mtimes.get(fpath)
                        if prev_mtime is None or mtime > prev_mtime:
                            self._mtimes[fpath] = mtime
                            modificados.append(fpath)

        # Limpiar referencias de archivos eliminados
        for fpath in list(self._mtimes.keys()):
            if fpath not in archivos_actuales:
                self._mtimes.pop(fpath, None)

        return modificados

    def _is_syntax_valid(self, filepath: str) -> bool:
        """Comprueba mediante AST si el archivo Python tiene una sintaxis válida."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            ast.parse(content, filename=filepath)
            return True
        except SyntaxError as e:
            logger.warning(
                f"[HotReload] ⏳ Archivo con sintaxis incompleta o en guardado: {os.path.basename(filepath)} "
                f"(Línea {e.lineno}, Col {e.offset}). Esperando guardado completo..."
            )
            return False
        except Exception as e:
            logger.warning(f"[HotReload] ⚠️ No se pudo leer {os.path.basename(filepath)}: {e}")
            return False

    def _filepath_to_module(self, filepath: str) -> str | None:
        """Convierte una ruta absoluta de archivo a nombre de módulo Python dot-separated."""
        try:
            rel = os.path.relpath(filepath, BASE_DIR)
            if rel.endswith(".py"):
                rel = rel[:-3]
            return rel.replace(os.sep, ".")
        except Exception:
            return None

    async def _process_changes(self, changed_files: list[str]):
        """Procesa y recarga de forma segura los archivos modificados."""
        if not self.bot:
            return

        # Filtrar solo archivos con sintaxis correcta
        valid_files = [f for f in changed_files if os.path.exists(f) and self._is_syntax_valid(f)]
        if not valid_files:
            return

        modulos_no_cogs = []
        cogs_a_recargar = set()

        for fpath in valid_files:
            mod_name = self._filepath_to_module(fpath)
            if not mod_name:
                continue

            if mod_name.startswith("cogs."):
                cogs_a_recargar.add(mod_name)
            else:
                modulos_no_cogs.append(mod_name)

        # 1. Si cambiaron módulos internos (servicios, core, ui, renderer), recargarlos en sys.modules
        if modulos_no_cogs:
            for mod_name in modulos_no_cogs:
                try:
                    if mod_name in sys.modules:
                        importlib.reload(sys.modules[mod_name])
                        logger.info(f"[HotReload] 🔄 Módulo interno actualizado: {mod_name}")
                except Exception as e:
                    logger.error(f"[HotReload] ❌ Fallo al recargar módulo {mod_name}: {e}")

            # Al cambiar un módulo interno, recargamos todos los Cogs activos para que tomen las nuevas referencias
            for ext in list(self.bot.extensions.keys()):
                cogs_a_recargar.add(ext)

        # 2. Recargar los Cogs correspondientes
        for cog_name in cogs_a_recargar:
            ok, msg = await self.reload_cog(cog_name)
            if ok:
                logger.info(f"[HotReload] ✅ {msg}")
            else:
                logger.error(f"[HotReload] ❌ {msg}")

    async def reload_cog(self, cog_name: str) -> tuple[bool, str]:
        """Recarga de forma segura un Cog específico por nombre."""
        if not self.bot:
            return False, "Bot no inicializado en HotReloadManager."

        # Asegurar formato 'cogs.nombre'
        full_name = cog_name if cog_name.startswith("cogs.") else f"cogs.{cog_name}"

        try:
            if full_name in self.bot.extensions:
                await self.bot.reload_extension(full_name)
                return True, f"Extensión recargada exitosamente: {full_name}"
            else:
                await self.bot.load_extension(full_name)
                return True, f"Extensión cargada exitosamente: {full_name}"
        except Exception as e:
            return False, f"Error al recargar {full_name}: {e}"

    async def reload_all(self) -> tuple[bool, list[str], list[str]]:
        """Recarga todas las extensiones activas registradas en el bot."""
        if not self.bot:
            return False, [], ["Bot no inicializado"]

        exitos = []
        errores = []

        async with self._lock:
            # Primero recargar módulos de soporte
            for root_dir in self.watch_dirs:
                if os.path.basename(root_dir) == "cogs":
                    continue
                for mod_name in list(sys.modules.keys()):
                    if any(mod_name.startswith(f"{d}.") or mod_name == d for d in ["services", "ui", "core", "renderer"]):
                        try:
                            importlib.reload(sys.modules[mod_name])
                        except Exception:
                            pass

            # Luego recargar todos los Cogs
            for ext in list(self.bot.extensions.keys()):
                ok, msg = await self.reload_cog(ext)
                if ok:
                    exitos.append(ext)
                else:
                    errores.append(f"{ext}: {msg}")

        todo_ok = (len(errores) == 0)
        return todo_ok, exitos, errores

    async def sync_tree(self, guild_id: int | None = None) -> tuple[bool, str]:
        """Sincroniza el árbol de comandos Slash con Discord de forma controlada."""
        if not self.bot:
            return False, "Bot no disponible."
        try:
            guild = discord.Object(id=guild_id) if guild_id else None
            synced = await self.bot.tree.sync(guild=guild)
            scope = f"en servidor {guild_id}" if guild_id else "globalmente"
            return True, f"Sincronizados {len(synced)} comandos {scope}."
        except Exception as e:
            return False, f"Error sincronizando árbol: {e}"

# Instancia global compartida
hot_reload_manager = HotReloadManager()

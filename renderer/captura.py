import os
import datetime
import asyncio
import logging
from playwright.async_api import async_playwright
from core.database import obtener_personaje

RENDERER_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = f"file://{os.path.join(RENDERER_DIR, 'index.html')}"

class BrowserRenderer:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Inicializa Playwright y arranca el navegador Chromium si no están activos."""
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                
                logging.info("[Playwright] Inicializando instancia compartida de Chromium...")
                self._browser = await self._playwright.chromium.launch(
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-web-security',
                        '--allow-file-access-from-files'
                    ]
                )

    async def close(self):
        """Cierra ordenadamente el navegador y el proceso Playwright."""
        async with self._lock:
            if self._browser:
                logging.info("[Playwright] Cerrando Chromium compartido...")
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

    async def generar_captura(self, chat_json):
        """Genera una imagen PNG del chat utilizando una pestaña ligera del navegador compartido."""
        await self.start()

        # Creamos un contexto ligero con viewport amplio y escala 2x para nitidez
        context = await self._browser.new_context(
            viewport={'width': 1000, 'height': 8000},
            device_scale_factor=2
        )
        page = await context.new_page()

        try:
            # 1. Cargar plantilla HTML
            await page.goto(HTML_PATH)
            await page.wait_for_timeout(50)

            # 2. Rellenar título
            titulo = chat_json["Chat"]["titulo"]
            await page.evaluate("(t) => { document.getElementById('title').innerText = t; }", titulo)

            # 3. Insertar mensajes dinámicamente
            for mensaje in chat_json["Chat"]["mensajes"]:
                personaje_id = mensaje["Personaje"]
                personaje = await obtener_personaje(personaje_id)

                if not personaje:
                    nombre, lado, avatar_url, color, color_texto = "Desc", "I", "https://cdn.discordapp.com/embed/avatars/0.png", "#FFF", "#000"
                else:
                    nombre, lado, avatar_url, color, color_texto = personaje[:5]

                datos_msg = {
                    "container": ".chat-container",
                    "color": color,
                    "colorTexto": color_texto,
                    "avatar": avatar_url,
                    "derecha": (lado == "D"),
                    "id": f"id{personaje_id}",
                    "texto": mensaje["Mensaje"],
                    "adjuntos": mensaje["Adjuntos"]
                }

                await page.evaluate("""(data) => {
                    const chat = new Chat(data.container, data.color, data.colorTexto, data.avatar, data.derecha, data.id);
                    chat.addMessage(data.texto, data.adjuntos);
                }""", datos_msg)

            # 4. Espera reactiva: fuentes e imágenes cargadas (sin timeouts ciegos innecesarios)
            try:
                await page.evaluate("""async () => {
                    if (document.fonts) {
                        await document.fonts.ready;
                    }
                    const images = Array.from(document.querySelectorAll('img'));
                    await Promise.all(images.map(img => {
                        if (img.complete) return Promise.resolve();
                        return new Promise(resolve => {
                            img.onload = resolve;
                            img.onerror = resolve;
                            setTimeout(resolve, 1500); // Límite de seguridad individual por imagen
                        });
                    }));
                }""")
            except Exception as e:
                logging.warning(f"[Playwright] Error durante la espera de recursos: {e}. Aplicando fallback...")
                await page.wait_for_timeout(300)

            # 5. Medir área exacta del contenedor
            clip_area = await page.evaluate("""() => {
                const element = document.querySelector('.chat-container');
                if (!element) return null;
                const rect = element.getBoundingClientRect();
                return {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                };
            }""")

            if not clip_area:
                raise RuntimeError("No se pudo medir el contenedor .chat-container")

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"captura_{timestamp}.png"

            # 6. Captura de pantalla recortada
            await page.screenshot(
                path=filename,
                clip=clip_area,
                omit_background=True
            )

            return filename

        finally:
            await context.close()

# Singleton compartido a nivel de módulo
_renderer = BrowserRenderer()

async def generar_captura(chat_json):
    """Función de compatibilidad que reutiliza el singleton del renderizador."""
    return await _renderer.generar_captura(chat_json)

async def iniciar_navegador():
    """Inicia explícitamente el navegador compartido."""
    await _renderer.start()

async def cerrar_navegador():
    """Cierra el navegador compartido."""
    await _renderer.close()
# captura.py
import os
import datetime
from playwright.async_api import async_playwright
from core.database import obtener_personaje

RENDERER_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = f"file://{os.path.join(RENDERER_DIR, 'index.html')}"

async def generar_captura(chat_json):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                '--no-sandbox', 
                '--disable-setuid-sandbox', 
                '--disable-web-security',      # <--- NUEVO
                '--allow-file-access-from-files' # <--- NUEVO
            ]
        )
        page = await browser.new_page()

        # 1. Cargar archivo local
        await page.goto(HTML_PATH)
        
        # 2. Esperar a que la fuente cargue (evita errores visuales)
        await page.wait_for_function("typeof window.Chat !== 'undefined'")
        await page.evaluate("document.fonts.ready")

        # 3. Inyectar título
        titulo = chat_json["Chat"]["titulo"]
        await page.evaluate(f"document.getElementById('title').innerText = '{titulo}';")

        # 4. Procesar mensajes
        for mensaje in chat_json["Chat"]["mensajes"]:
            personaje_id = mensaje["Personaje"]
            # Nota: añadir await aquí porque db ahora es async
            personaje = await obtener_personaje(personaje_id) 
            
            if not personaje:
                continue

            nombre, lado, avatar_url, color, color_texto = personaje
            
            # Preparar objeto de datos para pasar a JS limpiamente
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

            # Inyección limpia (sin f-strings gigantes)
            await page.evaluate("""(data) => {
                const chat = new Chat(data.container, data.color, data.colorTexto, data.avatar, data.derecha, data.id);
                chat.addMessage(data.texto, data.adjuntos);
            }""", datos_msg)

        # 5. Estilizar contenedor final
        await page.evaluate("""() => {
            const container = document.querySelector('.chat-container');
            container.style.borderRadius = '20px';
            container.style.overflow = 'hidden';
            container.style.padding = '20px';
            container.style.boxShadow = '0 0 15px rgba(0,0,0,0.5)';
        }""")

        await page.wait_for_timeout(1000)
        
        # 2. (Opcional pero recomendado) Esperar a que no haya tráfico de red
        # Esto asegura que todas las imágenes han terminado de bajar
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except:
            pass # Si tarda mucho, seguimos igual

        # Captura
        chat_element = await page.query_selector('.chat-container')
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"captura_{timestamp}.png"
        
        await chat_element.screenshot(path=filename)
        await browser.close()
        
        return filename
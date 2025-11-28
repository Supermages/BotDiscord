import os
import datetime
from playwright.async_api import async_playwright
# Ajusta el import según tu estructura
from core.database import obtener_personaje

RENDERER_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = f"file://{os.path.join(RENDERER_DIR, 'index.html')}"

async def generar_captura(chat_json):
    async with async_playwright() as p:
        # Lanzamos navegador
        browser = await p.chromium.launch(
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-web-security', '--allow-file-access-from-files']
        )
        
        # 1. Viewport inicial GIGANTE para asegurar que todo se renderice bien
        # (Aunque luego recortemos, necesitamos espacio para pintar)
        context = await browser.new_context(
            viewport={'width': 1000, 'height': 8000}, 
            device_scale_factor=2
        )
        page = await context.new_page()

        # 2. Cargar y rellenar datos (Igual que siempre)
        await page.goto(HTML_PATH)
        await page.wait_for_timeout(100)
        
        titulo = chat_json["Chat"]["titulo"]
        await page.evaluate("(t) => { document.getElementById('title').innerText = t; }", titulo)

        for mensaje in chat_json["Chat"]["mensajes"]:
            personaje_id = mensaje["Personaje"]
            personaje = await obtener_personaje(personaje_id) 
            
            if not personaje:
                nombre, lado, avatar_url, color, color_texto = "Desc", "I", "https://cdn.discordapp.com/embed/avatars/0.png", "#FFF", "#000"
            else:
                nombre, lado, avatar_url, color, color_texto = personaje
            
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

        # 3. Esperar a que todo cargue (Imágenes, fuentes)
        await page.wait_for_timeout(1500)

        # --- AQUÍ ESTÁ LA SOLUCIÓN ---
        
        # Obtenemos las coordenadas exactas del contenedor
        # getBoundingClientRect nos da {x, y, width, height} exactos
        clip_area = await page.evaluate("""() => {
            const element = document.querySelector('.chat-container');
            const rect = element.getBoundingClientRect();
            return {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height
            };
        }""")

        # Si por lo que sea falla, usaremos valores por defecto, pero no debería
        if not clip_area:
            raise Exception("No se pudo medir el chat.")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"captura_{timestamp}.png"

        # Hacemos la captura usando 'clip'. 
        # Esto ignora el tamaño de la ventana y recorta exactamente lo que le decimos.
        await page.screenshot(
            path=filename,
            clip=clip_area, # <--- LA CLAVE
            omit_background=True
        )
        
        await browser.close()
        return filename
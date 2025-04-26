import asyncio
import datetime
import json
from playwright.async_api import async_playwright

URL_PAGINA = "http://localhost:5500/"

async def generar_captura(chat_json):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Configurar un manejador de eventos para capturar los logs de la consola de JavaScript
        async def handle_console_message(msg):
            # Imprimir los logs de JavaScript en la consola de Python
            print(f"JS Log: {msg.text}")

        page.on("console", handle_console_message)

        # Después de ir a la página y esperar selector
        await page.goto(URL_PAGINA)
        await page.wait_for_selector('.chat-container')

        # Limpiar mensajes anteriores
        await page.evaluate('''
            const container = document.querySelector('.chat-container');
            container.innerHTML = container.children[0].outerHTML + container.children[1].outerHTML;
        ''')

        # Insertar cada mensaje de manera segura
        for personaje in chat_json["Chat"]["personajes"]:
            personaje_id = personaje["_id"]
            avatar = personaje["Avatar"]
            derecha = personaje["DerOIzq"] == "D"

            # Colores corregidos y pasados directamente como cadenas
            color = "#2C58E2" if derecha else "#FFFFFF"  # Azul para derecha, blanco para izquierda
            color_text = "#FFFFFF" if derecha else "#000000"  # Blanco para texto en azul, negro para texto en blanco
            avatar_js = json.dumps(avatar)
            derecha_js = "true" if derecha else "false"
            personaje_id_js = json.dumps(f"id{(personaje_id)}")
            mensajes = [m["Mensaje"] for m in chat_json["Chat"]["mensajes"] if m["Personaje"] == personaje_id]
           
            for mensaje in mensajes:
                mensaje_js = json.dumps(mensaje)  # Convierte el mensaje a cadena JSON válida
                await page.evaluate(f'''
                    const chat5 = new Chat('.chat-container', "{color}", "{color_text}", {avatar_js}, {derecha_js}, {personaje_id_js});
                    console.log("Color:", "{color}", "Color Texto:", "{color_text}");
                    chat5.addMessage({mensaje_js});
                ''')

        # Añadir borde visual al contenedor
        await page.evaluate('''
            const container = document.querySelector('.chat-container');
            container.style.borderRadius = '20px';
            container.style.overflow = 'hidden';
            container.style.padding = '20px';
            container.style.boxShadow = '0 0 15px rgba(0,0,0,0.5)';
        ''')

        await page.wait_for_timeout(500)

        chat_container = await page.query_selector('.chat-container')
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"exports/chat_{timestamp}.png"

        await chat_container.screenshot(path=filename)

        await browser.close()

        return filename
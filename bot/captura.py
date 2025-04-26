import asyncio
import datetime
import json
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

URL_PAGINA = "https://supermages.github.io/BotDiscord/"

async def generar_captura(chat_json):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        try:
            await page.goto(URL_PAGINA, timeout=15000)
            await page.wait_for_selector('.chat-container', timeout=10000)
            await page.wait_for_function('window.Chat !== undefined', timeout=10000)

            # Limpiar mensajes anteriores
            await page.evaluate('''
                const container = document.querySelector('.chat-container');
                container.innerHTML = container.children[0].outerHTML + container.children[1].outerHTML;
            ''')

            # Insertar los mensajes
            for personaje in chat_json["Chat"]["personajes"]:
                personaje_id = personaje["_id"]
                avatar = personaje["Avatar"]
                derecha = personaje["DerOIzq"] == "D"
                color = "#2C58E2" if derecha else "white"
                color_text = "white" if derecha else "black"

                mensajes = [m["Mensaje"] for m in chat_json["Chat"]["mensajes"] if m["Personaje"] == personaje_id]

                for mensaje in mensajes:
                    await page.evaluate('''
                        const chat = new Chat('.chat-container', color, colorText, avatar, derecha, user);
                        chat.addMessage(mensaje);
                    ''', {
                        "color": color,
                        "colorText": color_text,
                        "avatar": avatar,
                        "derecha": derecha,
                        "user": personaje_id,
                        "mensaje": mensaje
                    })

            # Embellecer el contenedor
            await page.evaluate('''
                const container = document.querySelector('.chat-container');
                container.style.borderRadius = '20px';
                container.style.overflow = 'hidden';
                container.style.padding = '20px';
                container.style.boxShadow = '0 0 15px rgba(0,0,0,0.5)';
            ''')

            await page.wait_for_timeout(500)

            # Capturar solo el chat
            chat_container = await page.query_selector('.chat-container')
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"exports/chat_{timestamp}.png"

            await chat_container.screenshot(path=filename)

            await browser.close()

            return filename

        except PlaywrightTimeout:
            await browser.close()
            raise Exception("❌ Error: No se pudo cargar la página o la clase Chat en el tiempo esperado.")

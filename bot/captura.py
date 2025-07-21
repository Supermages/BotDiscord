
import asyncio
import datetime
import json
from playwright.async_api import async_playwright
from db import obtener_personaje

URL_PAGINA = "https://supermages.github.io/BotDiscord/"

async def generar_captura(chat_json):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        async def handle_console_message(msg):
            print(f"JS Log: {msg.text}")

        page.on("console", handle_console_message)

        await page.goto(URL_PAGINA)
        await page.wait_for_selector('.chat-container')

        await page.evaluate('''
            const container = document.querySelector('.chat-container');
            container.innerHTML = container.children[0].outerHTML + container.children[1].outerHTML;
        ''')

        await page.evaluate('''
            const container = document.querySelector('.chat-container');
            const title = document.getElementById('title');
            title.innerHTML = "''' + chat_json["Chat"]["titulo"] + '''";
        ''')

        for mensaje in chat_json["Chat"]["mensajes"]:
            personaje_id = mensaje["Personaje"]
            mensaje_texto = mensaje["Mensaje"]
            adjuntos = mensaje["Adjuntos"]
            personaje = obtener_personaje(personaje_id)
            if not personaje:
                print(f"⚠️ Personaje con ID {personaje_id} no encontrado en la base de datos.")
                continue

            nombre, lado, avatar_url, color, color_texto = personaje
            derecha = lado == "D"

            avatar_js = json.dumps(avatar_url)
            derecha_js = "true" if derecha else "false"
            personaje_id_js = json.dumps(f"id{personaje_id}")
            mensaje_js = json.dumps(mensaje_texto)
            adjuntos_js = json.dumps(adjuntos) 

            await page.evaluate(f'''
                const chat5 = new Chat('.chat-container', "{color}", "{color_texto}", {avatar_js}, {derecha_js}, {personaje_id_js});
                chat5.addMessage({mensaje_js}, {adjuntos_js});
            ''')

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
        filename = f"exportaciones/chat_{timestamp}.png"

        await chat_container.screenshot(path=filename)
        await browser.close()
        return filename
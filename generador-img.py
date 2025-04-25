import asyncio
from playwright.async_api import async_playwright

async def generar_chat(data, output_path="chat_result.png"):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://zenless.tools/chat-generator", timeout=60000)

        # Esperar a que cargue la caja de chat
        await page.wait_for_selector(".chat-box")

        # Obtener elementos existentes
        items = await page.query_selector_all(".chat-item")

        for i, msg in enumerate(data):
            if i < len(items):
                # Reutilizar un mensaje existente
                await page.evaluate(
                    """([index, avatar, message]) => {
                        const el = document.querySelectorAll('.chat-item')[index];
                        if (!el) return;
                        el.querySelector('img').src = avatar;
                        el.querySelector('.chat-message').innerText = message;
                    }""",
                    [i, msg["avatar_url"], msg["message"]]
                )
            else:
                # Clonar uno existente y modificarlo
                await page.evaluate(
                    """([avatar, message]) => {
                        const base = document.querySelector('.chat-item');
                        const clone = base.cloneNode(true);
                        clone.querySelector('img').src = avatar;
                        clone.querySelector('.chat-message').innerText = message;
                        document.querySelector('.chat-box').appendChild(clone);
                    }""",
                    [msg["avatar_url"], msg["message"]]
                )

        # Esperamos un poco y bajamos al fondo para capturar
        await page.wait_for_timeout(1000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        container = await page.query_selector(".chat-box")
        await container.screenshot(path=output_path)

        await browser.close()
        return output_path


if __name__ == "__main__":
    # Entrada de ejemplo (sin username ahora)
    sample_data = [
        {
            "avatar_url": "https://cdn.discordapp.com/avatars/123456789012345678/abcdef1234567890.png",
            "message": "¿Hola? ¿Hay alguien ahí?"
        },
        {
            "avatar_url": "https://cdn.discordapp.com/avatars/987654321098765432/fedcba0987654321.png",
            "message": "Sí, te escucho fuerte y claro. ¿Qué pasa?"
        }
    ]
    asyncio.run(generar_chat(sample_data))

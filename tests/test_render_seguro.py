"""
Tests de seguridad del pipeline de render (XSS / inyeccion HTML):
- core/formatters.py (escapado de contenido de usuario y whitelist de etiquetas)
"""

import os
import sys
import re
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.formatters import limpiar_formato_discord, escapar_html, sanitizar_html_render

# Payload clasico de XSS que antes rompia el layout o ejecutaba JS en la pagina de render
PAYLOAD_XSS = '</div><img src=x onerror=alert(1)><script>alert("xss")</script>'


class TestRenderSeguro(unittest.TestCase):

    # ---------- escapar_html ----------

    def test_escapar_html_caracteres_peligrosos(self):
        """Los caracteres con significado HTML deben quedar como entidades inertes."""
        self.assertEqual(
            escapar_html('<script>alert("x")</script>'),
            '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;'
        )
        self.assertEqual(escapar_html("<img src='x' onerror='y'>"), '&lt;img src=&#x27;x&#x27; onerror=&#x27;y&#x27;&gt;')
        self.assertEqual(escapar_html("a & b"), "a &amp; b")
        self.assertEqual(escapar_html(""), "")
        self.assertEqual(escapar_html(None), "")

    # ---------- limpiar_formato_discord con contenido malicioso ----------

    def test_formatters_payload_malicioso_sin_tags_activos(self):
        """El payload XSS debe renderizarse como TEXTO visible, sin tags activos."""
        resultado = limpiar_formato_discord(PAYLOAD_XSS)
        # Ninguna etiqueta ejecutable fuera de la whitelist...
        self.assertNotIn("<script", resultado.lower())
        self.assertNotIn("<iframe", resultado.lower())
        self.assertNotIn("<img src=x", resultado)
        # ...ningun atributo on* dentro de un tag real...
        self.assertIsNone(re.search(r"<[a-zA-Z][^>]*\son[a-zA-Z]+\s*=", resultado))
        # ...y el texto original sigue visible de forma inerte.
        self.assertIn("&lt;script&gt;", resultado)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", resultado)

    def test_formatters_encabezado_con_html_inyectado(self):
        """Un encabezado con HTML debe mostrarlo como texto, no ejecutarlo."""
        resultado = limpiar_formato_discord("# Titulo <b>importante</b> y <script>x</script>")
        self.assertIn("font-size: 1.35em", resultado)
        self.assertNotIn("<b>importante", resultado)
        self.assertIn("&lt;b&gt;importante&lt;/b&gt;", resultado)
        self.assertNotIn("<script", resultado.lower())

    def test_formatters_spoiler_y_negrita_con_html(self):
        """Formato legitimo mezclado con HTML inyectado: solo se generan tags de la whitelist."""
        resultado = limpiar_formato_discord("**negrita</b> y ||spoiler <img src=x onerror=y>||**")
        self.assertIn("<b>negrita", resultado)
        self.assertIn('title="Spoiler"', resultado)
        self.assertIsNone(re.search(r"<[a-zA-Z][^>]*\son[a-zA-Z]+\s*=", resultado))
        self.assertNotIn("<script", resultado.lower())

    def test_formatters_formato_legitimo_se_mantiene(self):
        """El escapado no debe romper las transformaciones legítimas del chat."""
        self.assertIn("font-size: 1.05em", limpiar_formato_discord("### Subtitulo"))
        self.assertIn("font-size: 1.18em", limpiar_formato_discord("## Titulo"))
        self.assertIn("font-size: 0.82em", limpiar_formato_discord("-# Esto es un subtexto"))
        self.assertIn("border-left", limpiar_formato_discord("> Esto es una cita"))
        self.assertIn("<b>hola</b>", limpiar_formato_discord("**hola**"))
        self.assertIn("<i>mundo</i>", limpiar_formato_discord("*mundo*"))
        emoji = limpiar_formato_discord("Reacciona <:fuego:9876543210>")
        self.assertIn('<img class="custom-emoji"', emoji)
        self.assertIn("cdn.discordapp.com/emojis/9876543210.png", emoji)

    # ---------- sanitizar_html_render (whitelist final) ----------

    def test_sanitizar_html_render_elimina_tags_prohibidos(self):
        """Las etiquetas fuera de la whitelist se eliminan conservando su contenido como texto."""
        sucio = '<div class="ok">visible</div><script>alert(1)</script><iframe src="http://x"></iframe><span style="opacity:0.5">spoiler</span>'
        limpio = sanitizar_html_render(sucio)
        self.assertNotIn("<script", limpio.lower())
        self.assertNotIn("<iframe", limpio.lower())
        self.assertIn('<div class="ok">visible</div>', limpio)
        self.assertIn("alert(1)", limpio)  # el contenido queda como texto, no se pierde
        self.assertIn('<span style="opacity:0.5">spoiler</span>', limpio)

    def test_sanitizar_html_render_elimina_atributos_on(self):
        """Los atributos on* se eliminan incluso en etiquetas permitidas."""
        limpio = sanitizar_html_render('<div onerror="alert(1)" class="x">hola</div>')
        self.assertIsNone(re.search(r"\son[a-zA-Z]+\s*=", limpio))
        self.assertIn('class="x"', limpio)
        self.assertIn("hola", limpio)

    def test_sanitizar_html_render_bloquea_esquemas_peligrosos(self):
        """src/href con esquemas peligrosos se eliminan (y <a> fuera de whitelist se elimina)."""
        limpio = sanitizar_html_render('<img src="javascript:alert(1)"><a href="javascript:alert(2)">link</a>')
        self.assertNotIn("javascript:", limpio)
        self.assertIn("<img", limpio)
        self.assertIn("link", limpio)
        self.assertNotIn("<a ", limpio)

    def test_sanitizar_html_render_acepta_tags_de_la_whitelist(self):
        """Las etiquetas y atributos legitimos del render pasan intactas."""
        limpio = sanitizar_html_render('<div style="font-size: 1.35em;">Titulo</div><br><b>negrita</b>')
        self.assertIn('<div style="font-size: 1.35em;">Titulo</div>', limpio)
        self.assertIn("<br>", limpio)
        self.assertIn("<b>negrita</b>", limpio)


if __name__ == "__main__":
    unittest.main()

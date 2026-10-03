"""
Tests unitarios y de integracion para la capa de servicios de EriduBot:
- services/dice_service.py
- services/inventory_service.py
- services/crafting_service.py
- services/tupper_service.py
- services/image_service.py
- services/hot_reload_service.py
- services/lua_service.py
"""

import os
import sys
import time
import tempfile
import unittest
from unittest.mock import MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.config import Config
from core.database import (
    inicializar_base,
    set_db_path,
    get_db_path,
    guardar_personaje,
    crear_o_actualizar_item,
    modificar_cantidad_inventario,
    obtener_inventario_personaje,
    crear_receta
)
from services.dice_service import ejecutar_tirada, TiradaResultado
from services.inventory_service import (
    es_admin,
    puede_gestionar_personaje,
    consumir_item
)
from services.crafting_service import verificar_y_craftear
from services.tupper_service import TupperMatchEngine
from services.image_service import dividir_en_lotes_inteligentes
from services.hot_reload_service import HotReloadManager
from services.lua_service import parsear_tirada_dados

TEST_SERVICES_DB = os.path.join(BASE_DIR, "data", "test_services.sqlite")


class TestDiceService(unittest.TestCase):

    def test_tiradas_basicas_y_modificadores(self):
        """Verifica tiradas simples con y sin modificador."""
        # 1d20+5
        res = ejecutar_tirada("1d20+5")
        self.assertIsInstance(res, TiradaResultado)
        self.assertGreaterEqual(res.total, 6)
        self.assertLessEqual(res.total, 25)
        self.assertEqual(res.modificador, 5)

        # 2d6
        res2 = ejecutar_tirada("2d6")
        self.assertGreaterEqual(res2.total, 2)
        self.assertLessEqual(res2.total, 12)

        # Compuesta: 2d6 + 1d4 + 3
        res3 = ejecutar_tirada("2d6 + 1d4 + 3")
        self.assertGreaterEqual(res3.total, 2 + 1 + 3)
        self.assertLessEqual(res3.total, 12 + 4 + 3)

    def test_ventaja_y_desventaja(self):
        """Verifica que el modo ventaja y desventaja lancen 2 dados y descarten el correspondiente."""
        res_v = ejecutar_tirada("1d20+2", modo="ventaja")
        self.assertEqual(res_v.modo, "ventaja")
        self.assertEqual(len(res_v.grupos[0].tiradas), 1)
        self.assertEqual(len(res_v.grupos[0].tiradas_descartadas), 1)
        # En ventaja el dado elegido debe ser >= al descartado
        elegido = res_v.grupos[0].tiradas[0]
        descartado = res_v.grupos[0].tiradas_descartadas[0]
        self.assertGreaterEqual(elegido, descartado)

        res_d = ejecutar_tirada("1d20+2", modo="desventaja")
        self.assertEqual(res_d.modo, "desventaja")
        elegido_d = res_d.grupos[0].tiradas[0]
        descartado_d = res_d.grupos[0].tiradas_descartadas[0]
        # En desventaja el dado elegido debe ser <= al descartado
        self.assertLessEqual(elegido_d, descartado_d)

    def test_deteccion_critico_y_pifia(self):
        """Verifica que los atributos de critico y pifia esten disponibles en el resultado."""
        res = ejecutar_tirada("1d20")
        self.assertIn(res.es_critico, (True, False))
        self.assertIn(res.es_pifia, (True, False))

    def test_formulas_invalidas_y_seguridad(self):
        """Verifica que formulas maliciosas o excesivas lancen ValueError."""
        with self.assertRaises(ValueError):
            ejecutar_tirada("invalid_dice")

        with self.assertRaises(ValueError):
            ejecutar_tirada("100d20")  # Excede limite de 50 dados


class TestTupperService(unittest.TestCase):

    def test_tupper_match_engine(self):
        """Verifica la deduccion de autoría entre mensajes humanos y de webhook."""
        engine = TupperMatchEngine(max_history_per_channel=10, max_age_seconds=2.0)
        channel_id = 123456
        user_id = 7890

        # Registrar mensaje humano con prefijos tipo tupper (ej: Elena: Hola)
        engine.registrar_mensaje_humano(channel_id, user_id, "Elena: Hola a todos")

        # Coincidencia con el texto emitido por el webhook
        match_id = engine.buscar_coincidencia(channel_id, "Hola a todos")
        self.assertEqual(match_id, user_id)

        # Mensaje no coincidente
        no_match = engine.buscar_coincidencia(channel_id, "Texto completamente distinto")
        self.assertIsNone(no_match)

        # Expiracion por tiempo
        engine.registrar_mensaje_humano(channel_id, user_id, "Mensaje viejo")
        time.sleep(2.1)
        match_expired = engine.buscar_coincidencia(channel_id, "Mensaje viejo")
        self.assertIsNone(match_expired)


class TestImageService(unittest.TestCase):

    def test_dividir_en_lotes_inteligentes(self):
        """Verifica la segmentacion adaptativa de mensajes por peso y limite."""
        mensajes_cortos = [{"Mensaje": f"Msg {i}", "Adjuntos": []} for i in range(15)]
        lotes = dividir_en_lotes_inteligentes(mensajes_cortos, max_por_lote=5)
        # 15 mensajes cortos a max 5 por lote = 3 lotes
        self.assertEqual(len(lotes), 3)
        self.assertEqual(len(lotes[0]), 5)

        # Mensajes con adjuntos pesan mas (2.5 extra c/u)
        mensajes_pesados = [
            {"Mensaje": "Foto 1", "Adjuntos": ["img1.png", "img2.png"]},
            {"Mensaje": "Foto 2", "Adjuntos": ["img3.png", "img4.png"]},
            {"Mensaje": "Foto 3", "Adjuntos": ["img5.png", "img6.png"]}
        ]
        lotes_pesados = dividir_en_lotes_inteligentes(mensajes_pesados, max_por_lote=10, peso_maximo=10.0)
        self.assertGreater(len(lotes_pesados), 1)


class TestHotReloadService(unittest.TestCase):

    def test_ast_syntax_validation(self):
        """Verifica que el validador AST reconozca sintaxis valida e invalida."""
        manager = HotReloadManager()

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f_valid:
            f_valid.write("def suma(a, b):\n    return a + b\n")
            valid_path = f_valid.name

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f_invalid:
            f_invalid.write("def broken(\n    return a +\n")
            invalid_path = f_invalid.name

        try:
            self.assertTrue(manager._is_syntax_valid(valid_path))
            self.assertFalse(manager._is_syntax_valid(invalid_path))
        finally:
            if os.path.exists(valid_path):
                os.remove(valid_path)
            if os.path.exists(invalid_path):
                os.remove(invalid_path)


class TestLuaService(unittest.TestCase):

    def test_parsear_tirada_dados(self):
        """Verifica la funcion puente parsear_tirada_dados."""
        val = parsear_tirada_dados("1d20+5")
        self.assertGreaterEqual(val, 6)
        self.assertLessEqual(val, 25)

        # Valor numerico directo
        val_directo = parsear_tirada_dados("42")
        self.assertEqual(val_directo, 42)

        # Invalido
        val_inv = parsear_tirada_dados("abc")
        self.assertEqual(val_inv, 0)


class TestInventoryAndCraftingServices(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.prev_db = get_db_path()
        set_db_path(TEST_SERVICES_DB)
        if os.path.exists(TEST_SERVICES_DB):
            try:
                os.remove(TEST_SERVICES_DB)
            except Exception:
                pass
        await inicializar_base()

    async def asyncTearDown(self):
        set_db_path(self.prev_db)
        for f in [TEST_SERVICES_DB, TEST_SERVICES_DB + "-wal", TEST_SERVICES_DB + "-shm"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    async def test_puede_gestionar_personaje(self):
        """Valida las reglas de permisos para interactuar con personajes."""
        mock_user = MagicMock(id=1111)
        mock_other = MagicMock(id=2222)

        # 1. Personaje activo y pertenece al usuario
        pj_activo = {
            "tupper_tag": "pj_1",
            "owner_id": "1111",
            "creator_id": "1111"
        }
        puede, motivo = puede_gestionar_personaje(mock_user, pj_activo)
        self.assertTrue(puede)
        self.assertEqual(motivo, "dueño")

        # 2. Personaje activo de otro usuario
        puede_otro, motivo_otro = puede_gestionar_personaje(mock_other, pj_activo)
        self.assertFalse(puede_otro)
        self.assertEqual(motivo_otro, "no_es_dueño")

        # 3. Personaje en reserva propia
        pj_reserva = {
            "tupper_tag": "pj_2",
            "owner_id": None,
            "creator_id": "1111"
        }
        puede_res, motivo_res = puede_gestionar_personaje(mock_user, pj_reserva)
        self.assertFalse(puede_res)
        self.assertEqual(motivo_res, "en_reserva_propia")

    async def test_consumir_item_servicio(self):
        """Prueba consumo estandar de items consumibles."""
        await guardar_personaje("p1", "Heroe", "I", "", owner_id="1111", creator_id="1111")
        await crear_o_actualizar_item(
            item_id="manzana",
            nombre="Manzana Roja",
            emoji="🍎",
            categoria="Comida",
            descripcion="Recupera energia",
            es_usable=1,
            mensaje_uso="Te has comido una crujiente manzana."
        )

        # 1. Sin stock
        ok_fail, msg_fail, _, _ = await consumir_item("p1", "manzana", 1)
        self.assertFalse(ok_fail)
        self.assertIn("insuficiente", msg_fail.lower())

        # 2. Con stock
        await modificar_cantidad_inventario("p1", "manzana", 2)
        ok_exito, msg_exito, item_data, _ = await consumir_item("p1", "manzana", 1)
        self.assertTrue(ok_exito)
        self.assertEqual(msg_exito, "Te has comido una crujiente manzana.")

        # Verificar stock restante = 1
        inv = await obtener_inventario_personaje("p1")
        manzanas = next((i["cantidad"] for i in inv if i["item_id"] == "manzana"), 0)
        self.assertEqual(manzanas, 1)

    async def test_verificar_y_craftear_servicio(self):
        """Verifica el flujo completo del servicio de crafteo."""
        await guardar_personaje("herrero", "Herrero", "I", "")
        await crear_o_actualizar_item("cobre", "Lingote de Cobre", "🥉", "Material")
        await crear_o_actualizar_item("casco_cobre", "Casco de Cobre", "🪖", "Armadura")

        await crear_receta("rec_casco", "Casco Basico", "casco_cobre", 1, {"cobre": 3}, "Forja casco")

        # Intentar fabricar sin material
        ok_no, msg_no, _ = await verificar_y_craftear("herrero", "rec_casco", 1)
        self.assertFalse(ok_no)
        self.assertIn("Materiales insuficientes", msg_no)

        # Proveer material y fabricar
        await modificar_cantidad_inventario("herrero", "cobre", 5)
        ok_si, msg_si, _ = await verificar_y_craftear("herrero", "rec_casco", 1)
        self.assertTrue(ok_si)

        inv = await obtener_inventario_personaje("herrero")
        cascos = next((i["cantidad"] for i in inv if i["item_id"] == "casco_cobre"), 0)
        cobre_restante = next((i["cantidad"] for i in inv if i["item_id"] == "cobre"), 0)
        self.assertEqual(cascos, 1)
        self.assertEqual(cobre_restante, 2)


if __name__ == "__main__":
    unittest.main()

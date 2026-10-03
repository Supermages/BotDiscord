"""
Ejecutor maestro de pruebas para EriduBot.
Ejecuta todas las suites de prueba:
- tests/test_core.py
- tests/test_services.py
- tests/test_cogs_integrity.py
- tests/test_optimizations.py

Uso:
    python tests/run_all.py
    python -m unittest discover tests
"""

import os
import sys
import unittest
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

def main():
    print("=" * 70)
    print("        SUITE COMPLETA DE PRUEBAS DE REGRESION - ERIDUBOT")
    print("=" * 70)
    start_time = time.time()

    loader = unittest.defaultTestLoader
    suite = loader.discover(start_dir=os.path.join(BASE_DIR, "tests"), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    elapsed = time.time() - start_time
    print("=" * 70)
    print(f" TOTAL PRUEBAS EJECUTADAS: {result.testsRun}")
    print(f" TIEMPO TOTAL:             {elapsed:.2f} segundos")
    print(f" ERRORES:                  {len(result.errors)}")
    print(f" FALLOS:                   {len(result.failures)}")
    print("=" * 70)

    if result.wasSuccessful():
        print(" [ESTADO: PASADO] - Todos los sistemas estan 100% operativos.")
        return 0
    else:
        print(" [ESTADO: FALLO] - Se detectaron regresiones en el proyecto.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

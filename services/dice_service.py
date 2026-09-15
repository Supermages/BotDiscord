import random
import re
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class GrupoDado:
    cantidad: int
    caras: int
    signo: int  # 1 o -1
    tiradas: List[int] = field(default_factory=list)
    tiradas_descartadas: List[int] = field(default_factory=list)
    subtotal: int = 0

@dataclass
class TiradaResultado:
    formula: str
    total: int
    desglose: str
    modificador: int
    modo: str  # "normal", "ventaja", "desventaja"
    es_critico: bool = False
    es_pifia: bool = False
    mensaje_destacado: Optional[str] = None
    grupos: List[GrupoDado] = field(default_factory=list)

def ejecutar_tirada(formula: str = "1d20", modo: str = "normal") -> TiradaResultado:
    """
    Parsea y ejecuta una tirada de dados al estilo D&D (ej: '1d20+2', '2d6', 'd100', '1d20-3').
    Soporta:
    - Fórmulas simples y compuestas: '2d6 + 1d4 + 3', 'd20 + 5'
    - Modos: 'normal', 'ventaja' (mayor de 2), 'desventaja' (menor de 2)
    - Detección de Nat 20 (Crítico) y Nat 1 (Pifia) en d20
    """
    if not formula or not str(formula).strip():
        formula = "1d20"

    raw_formula = str(formula).strip()
    clean = raw_formula.replace(" ", "").lower()

    # Normalizar modo
    modo = (modo or "normal").strip().lower()
    if modo not in ("normal", "ventaja", "desventaja"):
        modo = "normal"

    # Tokenizar la expresión
    tokens = re.findall(r'([+-]?(?:\d*d\d+|\d+))', clean)
    if not tokens or "".join(tokens) != clean:
        raise ValueError(f"Fórmula de dados inválida: `{raw_formula}`. Ejemplo de uso: `1d20+2`, `2d6`, `d100`.")

    grupos_dados: List[GrupoDado] = []
    modificador_total = 0
    total_dados_contados = 0

    for token in tokens:
        signo = -1 if token.startswith('-') else 1
        t_clean = token.lstrip('+-')

        if 'd' in t_clean:
            partes = t_clean.split('d')
            cant_str, caras_str = partes[0], partes[1]
            cant = int(cant_str) if cant_str else 1
            caras = int(caras_str)

            if cant <= 0:
                raise ValueError("La cantidad de dados debe ser al menos 1.")
            if caras < 2:
                raise ValueError("Los dados deben tener al menos 2 caras (ej: d4, d6, d20).")
            if caras > 1000:
                raise ValueError("Los dados no pueden tener más de 1000 caras.")

            total_dados_contados += cant
            if total_dados_contados > 50:
                raise ValueError("No puedes lanzar más de 50 dados en una sola tirada.")

            grupos_dados.append(GrupoDado(cantidad=cant, caras=caras, signo=signo))
        else:
            valor_mod = int(t_clean) * signo
            modificador_total += valor_mod

    if not grupos_dados and modificador_total == 0:
        raise ValueError("No se especificaron dados ni modificadores válidos.")

    total_acumulado = 0
    es_critico = False
    es_pifia = False
    partes_desglose = []

    # Procesar grupos de dados
    for idx, g in enumerate(grupos_dados):
        # Manejo de Ventaja / Desventaja:
        # Se aplica al primer grupo si tiene 1 solo dado (o si es d20)
        es_primer_grupo_d20_o_unitario = (idx == 0 and (g.caras == 20 or g.cantidad == 1))

        if modo in ("ventaja", "desventaja") and es_primer_grupo_d20_o_unitario:
            dado1 = random.randint(1, g.caras)
            dado2 = random.randint(1, g.caras)

            if modo == "ventaja":
                elegido = max(dado1, dado2)
                descartado = min(dado1, dado2)
            else:
                elegido = min(dado1, dado2)
                descartado = max(dado1, dado2)

            g.tiradas = [elegido]
            g.tiradas_descartadas = [descartado]
            g.subtotal = elegido * g.signo
            total_acumulado += g.subtotal

            # Detección de crítico / pifia en d20
            if g.caras == 20:
                if elegido == 20:
                    es_critico = True
                elif elegido == 1:
                    es_pifia = True

            # Formato de ventaja/desventaja en desglose
            str_dados = f"d{g.caras}(~~[{descartado}]~~, **[{elegido}]**)"
            if g.signo == -1:
                partes_desglose.append(f"- {str_dados}")
            else:
                prefix = "+ " if idx > 0 else ""
                partes_desglose.append(f"{prefix}{str_dados}")

        else:
            # Tirada normal de los dados del grupo
            tiradas = [random.randint(1, g.caras) for _ in range(g.cantidad)]
            g.tiradas = tiradas
            sub = sum(tiradas) * g.signo
            g.subtotal = sub
            total_acumulado += sub

            # Detección de crítico / pifia si es 1d20
            if g.caras == 20 and g.cantidad == 1:
                if tiradas[0] == 20:
                    es_critico = True
                elif tiradas[0] == 1:
                    es_pifia = True

            str_dados = f"{g.cantidad}d{g.caras} [{', '.join(str(x) for x in tiradas)}]"
            if g.signo == -1:
                partes_desglose.append(f"- {str_dados}")
            else:
                prefix = "+ " if idx > 0 else ""
                partes_desglose.append(f"{prefix}{str_dados}")

    # Añadir modificador al total y al desglose
    total_acumulado += modificador_total
    if modificador_total != 0:
        if modificador_total > 0:
            partes_desglose.append(f"+ {modificador_total}")
        else:
            partes_desglose.append(f"- {abs(modificador_total)}")

    desglose_final = " ".join(partes_desglose)

    mensaje_destacado = None
    if es_critico:
        mensaje_destacado = "🎉 ¡ÉXITO CRÍTICO NATURAL (Nat 20)!"
    elif es_pifia:
        mensaje_destacado = "💀 ¡PIFIA NATURAL (Nat 1)!"

    return TiradaResultado(
        formula=raw_formula,
        total=total_acumulado,
        desglose=desglose_final,
        modificador=modificador_total,
        modo=modo,
        es_critico=es_critico,
        es_pifia=es_pifia,
        mensaje_destacado=mensaje_destacado,
        grupos=grupos_dados
    )

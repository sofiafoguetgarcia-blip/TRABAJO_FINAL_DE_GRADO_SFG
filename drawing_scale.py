# -*- coding: utf-8 -*-
"""
drawing_scale.py
================
Calcula el tamano del dibujo que hara el UR3e en funcion del tamano
real de la baldosa que le manda el JSON.

La idea es sencilla: no todas las baldosas miden lo mismo, asi que
el dibujo tiene que adaptarse a cada una. Se toma el lado mas corto
de la baldosa y se aplica un porcentaje (DRAWING_SCALE_ON_TILE) para
que el dibujo no llegue justo al borde.

Tambien hay unos limites minimo y maximo por seguridad: si por alguna
razon el calculo da un valor raro, se ajusta dentro del rango seguro.
"""

import logging
from config import (
    DRAWING_SCALE_ON_TILE,
    MAX_DRAWING_WIDTH_M,
    MIN_DRAWING_WIDTH_M,
)

log = logging.getLogger(__name__)

# Porcentaje del lado menor que ocupa el dibujo.
# Se importa de config.py para que sea facil de cambiar desde un solo sitio.
_ESCALA = DRAWING_SCALE_ON_TILE


def calcular_ancho_dibujo_por_baldosa(
    ancho_mm: float,
    alto_mm: float,
    escala: float | None = None,
) -> float:
    """
    Devuelve el ancho del dibujo en metros, ajustado al tamano de la baldosa.

    Recibe el ancho y el alto de la baldosa en milimetros (tal como vienen
    del JSON) y calcula cuanto espacio puede usar el robot para dibujar.

    El parametro escala es opcional: si no se pasa, se usa el valor de config.py.
    Esto permite ajustar el tamano desde fuera si hace falta en alguna prueba.

    El resultado siempre queda dentro de [MIN_DRAWING_WIDTH_M, MAX_DRAWING_WIDTH_M].
    """
    if escala is None:
        escala = _ESCALA

    # Tomamos el lado mas corto para que el dibujo quepa bien en la baldosa
    lado_menor_mm = min(ancho_mm, alto_mm)
    lado_menor_m = lado_menor_mm / 1000.0

    # Aplicamos el porcentaje de escala
    ancho_raw_m = lado_menor_m * escala

    # Ajustamos al rango seguro por si el calculo da algo extremo
    ancho_final_m = max(MIN_DRAWING_WIDTH_M, min(MAX_DRAWING_WIDTH_M, ancho_raw_m))

    log.info(
        f"Escala dibujo | baldosa: {ancho_mm:.1f}x{alto_mm:.1f} mm "
        f"| lado menor: {lado_menor_mm:.1f} mm "
        f"| escala: {escala:.2f} "
        f"| ancho dibujo calculado: {ancho_raw_m*1000:.1f} mm "
        f"| ancho dibujo final: {ancho_final_m*1000:.1f} mm"
    )

    # Avisamos si el valor tuvo que ajustarse para no perdernos casos raros
    if ancho_raw_m != ancho_final_m:
        log.warning(
            f"El ancho calculado ({ancho_raw_m*1000:.1f} mm) quedo fuera de los limites "
            f"[{MIN_DRAWING_WIDTH_M*1000:.0f}, {MAX_DRAWING_WIDTH_M*1000:.0f}] mm "
            f"y se ajusto a {ancho_final_m*1000:.1f} mm."
        )

    return ancho_final_m


def resumen_escala(piezas: list[dict]) -> str:
    """
    Genera una tabla con el tamano de dibujo que se asignara a cada pieza.
    Se imprime al principio del programa para revisar que todo tiene buena pinta
    antes de enviar nada a los robots.
    """
    lineas = [
        "",
        "=" * 65,
        f"  {'Pieza':>5}  {'Baldosa (mm)':^18}  {'Lado menor':>10}  {'Dibujo (mm)':>11}",
        "-" * 65,
    ]
    for p in piezas:
        num = p.get("numero", "?")
        a = float(p.get("ancho_mm", 0))
        h = float(p.get("alto_mm", 0))
        lado = min(a, h)
        dibujo_m = calcular_ancho_dibujo_por_baldosa(a, h)
        lineas.append(
            f"  {num:>5}  {a:>7.1f} x {h:<7.1f}  {lado:>10.1f}  {dibujo_m*1000:>11.1f}"
        )
    lineas += ["=" * 65, ""]
    return "\n".join(lineas)

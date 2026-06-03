"""
Visualización: dibujo de anotaciones sobre imágenes.

Este módulo es OPCIONAL. Su único propósito es generar imágenes de
validación visual. El sistema funciona correctamente sin él.
"""

import math

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Helpers de dibujo
# ---------------------------------------------------------------------------

def _punto_en_eje(cx: float, cy: float, angulo_rad: float,
                  longitud: float, eje: str) -> tuple[int, int]:
    """
    Punto a `longitud/2` del centro a lo largo del eje indicado.
    Convención: angulo_rad es la dirección del lado CORTO (ancho).
      eje='ancho' → dirección del lado corto  (angulo_rad)
      eje='alto'  → dirección del lado largo  (angulo_rad + 90°)
    """
    if eje == "ancho":
        dx = math.cos(angulo_rad) * longitud / 2
        dy = math.sin(angulo_rad) * longitud / 2
    else:  # alto
        dx = math.cos(angulo_rad + math.pi / 2) * longitud / 2
        dy = math.sin(angulo_rad + math.pi / 2) * longitud / 2
    return (round(cx + dx), round(cy + dy))


def _texto_con_sombra(img: np.ndarray, texto: str, pos: tuple[int, int],
                      escala: float, color: tuple, grosor: int) -> None:
    """Texto con sombra negra para mejor legibilidad sobre cualquier fondo."""
    fuente = cv2.FONT_HERSHEY_SIMPLEX
    off = max(1, round(grosor * 0.8))
    cv2.putText(img, texto, (pos[0] + off, pos[1] + off),
                fuente, escala, (0, 0, 0), grosor + 1, cv2.LINE_AA)
    cv2.putText(img, texto, pos, fuente, escala, color, grosor, cv2.LINE_AA)


def _extremo_izquierdo_o_inferior(p1: tuple[int, int],
                                  p2: tuple[int, int]) -> tuple[int, int]:
    """
    Devuelve el extremo más a la izquierda de la línea.
    Si es completamente vertical (|dx| < 5), devuelve el extremo inferior
    (mayor y, ya que en imagen y crece hacia abajo).
    """
    dx = abs(p2[0] - p1[0])
    if dx < 5:
        return p1 if p1[1] > p2[1] else p2
    return p1 if p1[0] < p2[0] else p2


def _dibujar_texto_en_extremo(img: np.ndarray, texto: str,
                               p1: tuple[int, int], p2: tuple[int, int],
                               escala: float, color: tuple, grosor: int) -> None:
    """
    Dibuja `texto` cerca del extremo izquierdo (o inferior si vertical) de la
    línea p1–p2, con una línea guía fina que lo conecta con el extremo.
    El texto se desplaza perpendicularmente hacia 'arriba' en la imagen.
    """
    ext = _extremo_izquierdo_o_inferior(p1, p2)
    otro = p2 if ext is p1 else p1

    dx = otro[0] - ext[0]
    dy = otro[1] - ext[1]
    L = math.hypot(dx, dy)
    if L < 1:
        L = 1

    # Perpendicular hacia "arriba" en la imagen (menor y)
    perp_x = dy / L
    perp_y = -dx / L

    desplazamiento = max(20, round(img.shape[1] / 120))
    pos = (round(ext[0] + perp_x * desplazamiento),
           round(ext[1] + perp_y * desplazamiento))

    # Línea guía fina
    cv2.line(img, ext, pos, color, 1, cv2.LINE_AA)

    # Ajuste para que el texto no quede justo encima del punto final
    pos = (pos[0] + 2, pos[1] + 2)
    _texto_con_sombra(img, texto, pos, escala, color, grosor)


# ---------------------------------------------------------------------------
# Anotación de piezas
# ---------------------------------------------------------------------------

def dibujar_anotaciones(img_original: np.ndarray, piezas: list[dict],
                        modo: str = "camara") -> np.ndarray:
    """
    Dibuja sobre una copia de la imagen las anotaciones de cada pieza.

    modo="camara"  → textos en píxeles (centro_x, centro_y, ancho, alto).
    modo="robot"   → textos en mm      (robot_x, robot_y, ancho_mm, alto_mm).
    """
    img = img_original.copy()
    h_img, w_img = img.shape[:2]

    escala_fuente = max(0.8, w_img / 2500)
    grosor = max(2, round(w_img / 1000))

    es_robot = (modo == "robot")

    for pieza in piezas:
        cx = pieza["centro_x"]
        cy = pieza["centro_y"]
        rect = pieza["_rect"]
        angulo = pieza["angulo_grados"]
        numero = pieza["numero"]

        # Valores a mostrar según modo
        if es_robot:
            cx_texto = pieza.get("robot_x", cx)
            cy_texto = pieza.get("robot_y", cy)
            ancho_texto = pieza.get("ancho_mm", pieza["ancho"])
            alto_texto = pieza.get("alto_mm", pieza["alto"])
            unidad = "mm"
        else:
            cx_texto = cx
            cy_texto = cy
            ancho_texto = pieza["ancho"]
            alto_texto = pieza["alto"]
            unidad = "px"

        ancho = pieza["ancho"]
        alto = pieza["alto"]
        ang_rad = math.radians(angulo)

        # Contorno rotado (verde)
        box = np.int32(cv2.boxPoints(rect))
        cv2.drawContours(img, [box], 0, (0, 220, 0), grosor + 1)

        # Centro (círculo rojo + coordenadas)
        r = max(8, round(w_img / 300))
        cv2.circle(img, (cx, cy), r, (0, 0, 220), -1)
        cv2.circle(img, (cx, cy), r + 2, (255, 255, 255), 2)
        off_txt = round(r * 1.8)
        _texto_con_sombra(img, f"({cx_texto:.1f}, {cy_texto:.1f})",
                          (cx + off_txt, cy - off_txt),
                          escala_fuente * 0.85, (255, 255, 255), grosor)

        # Número de pieza (amarillo, esquina superior del bbox)
        pto_sup = box[box[:, 1].argmin()]
        pos_num = (pto_sup[0] - round(escala_fuente * 25),
                   pto_sup[1] - round(escala_fuente * 15))
        _texto_con_sombra(img, str(numero), pos_num,
                          escala_fuente * 1.6, (0, 220, 255), grosor + 1)

        # Línea ALTO (naranja) — eje largo
        p1 = _punto_en_eje(cx, cy, ang_rad, alto, "alto")
        p2 = _punto_en_eje(cx, cy, ang_rad, -alto, "alto")
        cv2.line(img, p1, p2, (0, 140, 255), grosor)
        _dibujar_texto_en_extremo(
            img, f"H:{alto_texto:.1f}{unidad}", p1, p2,
            escala_fuente * 0.8, (0, 140, 255), grosor)

        # Línea ANCHO (azul-cian) — eje corto
        p3 = _punto_en_eje(cx, cy, ang_rad, ancho, "ancho")
        p4 = _punto_en_eje(cx, cy, ang_rad, -ancho, "ancho")
        cv2.line(img, p3, p4, (255, 200, 0), grosor)
        _dibujar_texto_en_extremo(
            img, f"W:{ancho_texto:.1f}{unidad}", p3, p4,
            escala_fuente * 0.8, (255, 200, 0), grosor)

        # Ángulo (lila)
        _texto_con_sombra(img, f"{angulo:.1f} grados",
                          (cx + off_txt, cy + off_txt + round(escala_fuente * 22)),
                          escala_fuente * 0.75, (200, 200, 255), grosor)

    return img


# ---------------------------------------------------------------------------
# Anotación de referencias
# ---------------------------------------------------------------------------

from scripts.deteccion_referencias import REF_CONFIG


def dibujar_referencias(
    img: np.ndarray,
    refs: dict[str, tuple[float, float]],
    label_coords: dict[str, tuple[float, float]] | None = None,
) -> None:
    """
    Dibuja sobre la imagen las referencias detectadas.

    Args:
        img: Imagen sobre la que dibujar (modificada in-place).
        refs: Coordenadas en píxeles de cada referencia.
        label_coords: Coordenadas alternativas para mostrar en el texto del
            label (p. ej. coordenadas del robot). Si es None, se usan las de `refs`.
    """
    h_img, w_img = img.shape[:2]
    escala_fuente = max(0.7, w_img / 3000)
    grosor = max(2, round(w_img / 1200))
    radio = max(10, round(w_img / 250))
    long_cruz = max(15, round(w_img / 180))

    colores = {
        "ref1": (255, 0, 255),   # magenta
        "ref2": (0, 255, 255),   # cian
    }
    nombres_label = {
        "ref1": "Ref1",
        "ref2": "Ref2",
    }

    for nombre, (cx, cy) in refs.items():
        color = colores.get(nombre, (0, 255, 0))
        ix, iy = int(round(cx)), int(round(cy))

        # Ventana de búsqueda (ROI) calculada desde porcentajes
        cfg = REF_CONFIG[nombre]
        x0 = max(0, int(w_img * cfg["x_min"]))
        y0 = max(0, int(h_img * cfg["y_min"]))
        x1 = min(w_img, int(w_img * cfg["x_max"]))
        y1 = min(h_img, int(h_img * cfg["y_max"]))
        cv2.rectangle(img, (x0, y0), (x1, y1), color, 2, cv2.LINE_AA)

        # Cruz centrada
        cv2.line(img, (ix - long_cruz, iy), (ix + long_cruz, iy), color, grosor)
        cv2.line(img, (ix, iy - long_cruz), (ix, iy + long_cruz), color, grosor)

        # Círculo
        cv2.circle(img, (ix, iy), radio, color, grosor)
        cv2.circle(img, (ix, iy), radio + 3, (255, 255, 255), 2)

        # Texto con sombra (coordenadas del label o de la imagen)
        lx, ly = label_coords.get(nombre, (cx, cy)) if label_coords else (cx, cy)
        label = f"{nombres_label.get(nombre, nombre)}: ({lx:.1f}, {ly:.1f})"
        off_x = ix + radio + 10
        off_y = iy - radio - 5

        fuente = cv2.FONT_HERSHEY_SIMPLEX
        off_sombra = max(1, round(grosor * 0.8))
        cv2.putText(img, label, (off_x + off_sombra, off_y + off_sombra),
                    fuente, escala_fuente, (0, 0, 0), grosor + 1, cv2.LINE_AA)
        cv2.putText(img, label, (off_x, off_y),
                    fuente, escala_fuente, color, grosor, cv2.LINE_AA)

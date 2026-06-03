# -*- coding: utf-8 -*-
"""
trajectory.py
=============
Convierte los bordes de una imagen en una lista de trayectorias 2D
que el UR3e puede seguir para dibujar sobre la baldosa.

Cada trayectoria es una lista de puntos (x, y) en metros, centrados
en (0, 0) para que el robot los coloque encima del centro de la baldosa.
La escala se calcula en funcion del tamano real de la baldosa, de modo
que el dibujo se adapta a cada pieza.
"""

from typing import List, Tuple
import logging
import cv2
import numpy as np

from config import EPSILON_PX, DECIMATE_STEP, MIN_PUNTOS_CONTORNO, MIN_LONGITUD_PX, MAX_PUNTOS_TOTAL

log = logging.getLogger(__name__)

# Tipos para que el codigo sea mas legible
Punto = Tuple[float, float]
Trayectoria = List[Punto]


def extraer_trayectorias(
    edges: np.ndarray,
    img_shape: Tuple[int, int],
    ancho_dibujo_m: float
) -> List[Trayectoria]:
    """
    A partir de la imagen de bordes, extrae los contornos y los convierte
    en trayectorias en metros centradas en el origen.

    El proceso es:
    1. Buscar contornos en la imagen de bordes.
    2. Ordenarlos de mayor a menor longitud (los mas largos primero).
    3. Filtrar los que sean demasiado cortos o que sean el borde de la imagen.
    4. Simplificar cada contorno con approxPolyDP para reducir puntos redundantes.
    5. Decimarlo (coger un punto de cada N) para no sobrecargar el robot.
    6. Escalar y centrar los puntos para que encajen en la baldosa real.

    Se para cuando se llega al limite maximo de puntos totales.
    """
    img_h, img_w = img_shape[:2]

    # La escala convierte pixeles a metros.
    # Para imagenes de flores usamos el ancho directamente.
    # (Para otros dibujos como el oso se usaria ancho*2, segun el aspecto del dibujo)
    escala = ancho_dibujo_m / float(img_w)

    # Buscamos todos los contornos de la imagen
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise ValueError("No se detectaron contornos en la imagen de dibujo.")

    # Ordenamos de mas largo a mas corto para priorizar los trazos importantes
    contours = sorted(contours, key=lambda c: cv2.arcLength(c, False), reverse=True)

    trayectorias: List[Trayectoria] = []
    total_puntos = 0
    descartados = 0

    for c in contours:
        x, y, w, h = cv2.boundingRect(c)

        # Descartamos contornos que ocupen casi toda la imagen (suelen ser el borde)
        if w >= img_w * 0.98 or h >= img_h * 0.98:
            descartados += 1
            continue

        # Descartamos contornos demasiado cortos para que merezca la pena dibujarlos
        if cv2.arcLength(c, False) < MIN_LONGITUD_PX:
            descartados += 1
            continue

        # Simplificamos el contorno para no tener puntos casi identicos seguidos
        approx = cv2.approxPolyDP(c, EPSILON_PX, closed=False) 
        pts = approx.reshape(-1, 2)

        # Decimamos: nos quedamos con un punto de cada DECIMATE_STEP
        if DECIMATE_STEP > 1:
            pts = pts[::DECIMATE_STEP]

        # Si despues de todo esto queda muy poca cosa, lo descartamos
        if len(pts) < MIN_PUNTOS_CONTORNO:
            descartados += 1
            continue

        # Convertimos de pixeles a metros y centramos respecto al centro de la imagen
        trayectoria = [
            ((px - img_w / 2.0) * escala, -(py - img_h / 2.0) * escala)
            for px, py in pts
        ]
        trayectorias.append(trayectoria)
        total_puntos += len(trayectoria)

        # Paramos si ya tenemos suficientes puntos para no saturar el robot
        if total_puntos >= MAX_PUNTOS_TOTAL:
            log.warning(f"Limite de {MAX_PUNTOS_TOTAL} puntos alcanzado.")
            break

    if not trayectorias:
        raise ValueError("No hay trayectorias validas tras el filtrado.")

    log.info(
        f"Trayectorias validas: {len(trayectorias)} | puntos={total_puntos} | "
        f"descartados={descartados} | ancho dibujo={ancho_dibujo_m*1000:.1f} mm"
    )
    return trayectorias

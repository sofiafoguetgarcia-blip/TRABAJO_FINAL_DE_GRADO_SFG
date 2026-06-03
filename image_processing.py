# -*- coding: utf-8 -*-
"""
image_processing.py
===================
Preprocesa la imagen del dibujo que luego ejecutara el UR3e.

El objetivo es extraer los bordes de la imagen de forma robusta.
Se usan dos pasadas de Canny con umbrales distintos (uno mas fino y
otro mas grueso) y ademas el gradiente morfologico. Los tres resultados
se combinan para no perder detalles ni lineas finas.

Al final se guarda una imagen de debug para poder ver que bordes
se han detectado antes de mandar nada al robot.
"""

import os
import logging
import cv2
import numpy as np

from config import CANNY_FINO_LOW, CANNY_FINO_HIGH, CANNY_GRUESO_LOW, CANNY_GRUESO_HIGH

log = logging.getLogger(__name__)


def cargar_imagen(path: str) -> np.ndarray:
    """
    Carga la imagen del dibujo desde disco.
    Si el archivo no existe o no se puede leer, lanza un error claro
    en lugar de fallar de forma misteriosa mas adelante.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No existe la imagen de dibujo: {path}")
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"OpenCV no pudo leer la imagen: {path}")
    log.info(f"Imagen de dibujo cargada: {path} ({img.shape[1]}x{img.shape[0]} px)")
    return img


def preprocesar_imagen(img: np.ndarray) -> np.ndarray:
    """
    Extrae bordes combinando Canny fino, Canny grueso y gradiente morfologico.
    Esta combinacion mantiene detalles finos y ayuda a cerrar lineas del dibujo.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)

    edges_fino = cv2.Canny(blur, CANNY_FINO_LOW, CANNY_FINO_HIGH)
    edges_grueso = cv2.Canny(blur, CANNY_GRUESO_LOW, CANNY_GRUESO_HIGH)

    kernel = np.ones((3, 3), np.uint8)
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
    _, edges_grad = cv2.threshold(grad, 15, 255, cv2.THRESH_BINARY)

    edges = cv2.bitwise_or(edges_fino, edges_grueso)
    edges = cv2.bitwise_or(edges, edges_grad)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)

    log.debug("Preprocesado completado.")
    return edges


def guardar_debug(edges: np.ndarray, path: str = "debug_edges.png") -> None:
    """
    Guarda la imagen de bordes en disco para poder revisarla visualmente.
    Util para comprobar que se han detectado bien los contornos del dibujo.
    """
    cv2.imwrite(path, edges)
    log.info(f"Imagen de bordes guardada: {path}")

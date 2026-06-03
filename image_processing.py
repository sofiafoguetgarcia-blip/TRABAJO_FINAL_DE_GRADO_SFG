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
    Preprocesado simple para dibujo blanco sobre fondo negro.
    Mantiene la flor completa.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) # Convierte a escala de grises. Porq Canny funciona mejor en imágenes monocromáticas.
    blur = cv2.GaussianBlur(gray, (3, 3), 0) # Aplica un desenfoque gaussiano para reducir ruido. El kernel de 3x3 es un buen compromiso entre suavizado y detalle.

    edges_fino   = cv2.Canny(blur, CANNY_FINO_LOW,   CANNY_FINO_HIGH) # Detecta bordes finos con umbrales bajos.
    edges_grueso = cv2.Canny(blur, CANNY_GRUESO_LOW,  CANNY_GRUESO_HIGH) # Detecta bordes gruesos con umbrales altos.

    kernel = np.ones((3, 3), np.uint8) # Kernel para operaciones morfológicas. Un bloque de 3x3 píxeles.
    grad   = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel) # Calcula el gradiente morfológico, que resalta los bordes como la diferencia entre dilatación y erosión. 
    # Útil para detectar bordes que Canny podría perder.
    
    _, edges_grad = cv2.threshold(grad, 15, 255, cv2.THRESH_BINARY) # Convierte el gradiente a una imagen binaria. El umbral de 15 es un valor que resalta los bordes sin incluir demasiado ruido.

    edges = cv2.bitwise_or(edges_fino,  edges_grueso) # Combina los bordes finos y gruesos usando una operación OR bit a bit. Así se conservan ambos tipos de bordes.
    edges = cv2.bitwise_or(edges,       edges_grad) # Combina el resultado anterior con el gradiente morfológico para incluir bordes adicionales que Canny podría haber pasado por alto.
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1) # Aplica una operación de cierre (dilatación seguida de erosión) para cerrar pequeños huecos en los bordes y conectar segmentos cercanos. 
    # Ayuda a formar contornos más continuos.

    log.debug("Preprocesado completado.") 
    return edges

def guardar_debug(edges: np.ndarray, path: str = "debug_edges.png") -> None:
    """
    Guarda la imagen de bordes en disco para poder revisarla visualmente.
    Util para comprobar que se han detectado bien los contornos del dibujo.
    """
    cv2.imwrite(path, edges)
    log.info(f"Imagen de bordes guardada: {path}")

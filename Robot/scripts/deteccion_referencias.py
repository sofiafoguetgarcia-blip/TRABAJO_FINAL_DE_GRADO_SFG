"""
Detección automática de las cruces de referencia de calibración.

Las cruces son marcas oscuras en forma de 'X' pintadas sobre la mesa.
Se detectan sobre la imagen rectificada (vista cenital).

Los ROIs de búsqueda se definen como porcentaje del ancho/alto de la imagen
rectificada, de modo que escalan correctamente independientemente de la
distancia de la cámara.
"""

import warnings
from pathlib import Path

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent.parent
IMAGEN_ENTRADA = BASE_DIR / "assets" / "imagenes" / "DSC07665.jpg"

# Configuración de ROIs como porcentaje de la imagen rectificada (0–1).
# Ref 1: ~20 % desde arriba, ~71 % desde la derecha (= 29 % desde izquierda)
# Ref 2: ~89 % desde arriba, ~22 % desde la derecha (= 78 % desde izquierda)
# Margen ±6 % alrededor del punto estimado
REF_CONFIG = {
    "ref1": {
        "x_min": 0.23, "x_max": 0.35,   # 29 % ± 6 % desde izquierda
        "y_min": 0.14, "y_max": 0.26,   # 20 % ± 6 % desde arriba
    },
    "ref2": {
        "x_min": 0.72, "x_max": 0.84,   # 78 % ± 6 % desde izquierda
        "y_min": 0.83, "y_max": 0.95,   # 89 % ± 6 % desde arriba
    },
}


def detectar_referencias(img: np.ndarray) -> dict[str, tuple[float, float]]:
    """
    Detecta las cruces de referencia y devuelve sus centros exactos en píxeles.

    Args:
        img: Imagen BGR rectificada (solo la mesa, vista cenital).

    Retorna:
        {"ref1": (x1, y1), "ref2": (x2, y2)}
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h_img, w_img = gray.shape

    centros: dict[str, tuple[float, float]] = {}

    for nombre, cfg in REF_CONFIG.items():
        # Calcular ROI en píxeles a partir de porcentajes
        x0 = int(w_img * cfg["x_min"])
        x1 = int(w_img * cfg["x_max"])
        y0 = int(h_img * cfg["y_min"])
        y1 = int(h_img * cfg["y_max"])

        # Centro estimado del ROI (para selección del contorno más cercano)
        cx_est = (x0 + x1) / 2.0
        cy_est = (y0 + y1) / 2.0

        roi = gray[y0:y1, x0:x1]

        # Umbral adaptativo con Otsu (robusto ante cambios de iluminación).
        # Si Otsu no encuentra separación bimodal, usar el centro del ROI.
        ret, mask = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        if ret == 0:
            warnings.warn(
                f"{nombre}: Otsu no pudo encontrar umbral en el ROI. "
                f"Usando centro del ROI como fallback."
            )
            centros[nombre] = (float(cx_est), float(cy_est))
            continue

        # Limpiar ruido pequeño
        k = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)

        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            warnings.warn(
                f"{nombre}: no se encontraron contornos en el ROI con umbral Otsu={ret:.0f}. "
                f"Usando centro del ROI como fallback."
            )
            centros[nombre] = (float(cx_est), float(cy_est))
            continue

        # Seleccionar el contorno más cercano al centro estimado
        mejor_cnt = None
        mejor_dist = float("inf")
        for c in cnts:
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx_roi = M["m10"] / M["m00"]
            cy_roi = M["m01"] / M["m00"]
            dist = abs(cx_roi - (cx_est - x0)) + abs(cy_roi - (cy_est - y0))
            if dist < mejor_dist:
                mejor_dist = dist
                mejor_cnt = c

        if mejor_cnt is None:
            centros[nombre] = (float(cx_est), float(cy_est))
            continue

        M = cv2.moments(mejor_cnt)
        cx_roi = M["m10"] / M["m00"]
        cy_roi = M["m01"] / M["m00"]

        # Convertir a coordenadas globales de la imagen rectificada
        centros[nombre] = (float(cx_roi + x0), float(cy_roi + y0))

    return centros


def main() -> None:
    from scripts.homografia import rectificar_imagen

    img = cv2.imread(str(IMAGEN_ENTRADA))
    if img is None:
        raise FileNotFoundError(f"No se pudo cargar la imagen: {IMAGEN_ENTRADA}")

    img_rect, _, _ = rectificar_imagen(img)
    refs = detectar_referencias(img_rect)

    print("Referencias detectadas (sobre imagen rectificada):")
    for nombre, (x, y) in refs.items():
        print(f"  {nombre}: ({x:.2f}, {y:.2f})")


if __name__ == "__main__":
    main()

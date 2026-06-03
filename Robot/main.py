"""
Orquestador principal del sistema de detección de piezas cerámicas.

Flujo:
  1. Rectificar imagen (homografía) → vista cenital.
  2. Recortar bordes de la rectificada (20 % izq, 5 % resto).
  3. Detectar piezas y referencias (lógica pura).
  4. Calibrar y transformar coordenadas píxeles → robot (mm).
  5. Guardar JSON de resultados (salida definitiva).
  6. (Opcional) Generar imágenes anotadas para validación visual.

NOTA: Los pasos 1–5 son el núcleo funcional. El paso 6 es OPCIONAL y puede
eliminarse o comentarse sin afectar la generación de los archivos JSON.
"""

import json
from pathlib import Path

import cv2
import numpy as np

from scripts.homografia import rectificar_imagen
from scripts.deteccion_piezas import detectar_piezas, guardar_json, normalizar_rect
from scripts.deteccion_referencias import detectar_referencias
from scripts.calibracion import (
    calcular_calibracion,
    pixel_a_robot,
    REF1_ROBOT,
    REF2_ROBOT,
)

# ── Importación opcional de visualización ──────────────────────────────────
# Si se comenta o elimina este bloque, el sistema sigue generando los JSON
# correctamente; solo dejará de producir las imágenes de validación.
from scripts.visualizacion import dibujar_anotaciones, dibujar_referencias


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
IMAGEN_ENTRADA = BASE_DIR / "assets" / "imagenes" / "DSC07665.jpg"
DIR_RESULTADOS = BASE_DIR / "resultados"

IMAGEN_ANOTADA = DIR_RESULTADOS / "imagen1_resultado.jpg"
IMAGEN_ANOTADA_ROBOT = DIR_RESULTADOS / "imagen1_resultado_robot.jpg"
JSON_DETECCION = DIR_RESULTADOS / "deteccion.json"
JSON_ROBOT = DIR_RESULTADOS / "datos_robot.json"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)

    print(f"Imagen: {IMAGEN_ENTRADA}")

    # ═══════════════════════════════════════════════════════════════════════
    # SECCIÓN 0 — RECTIFICACIÓN DE PERSPECTIVA
    # ═══════════════════════════════════════════════════════════════════════
    img = cv2.imread(str(IMAGEN_ENTRADA))
    if img is None:
        raise FileNotFoundError(f"No se pudo cargar la imagen: {IMAGEN_ENTRADA}")

    img_rect, M, esquinas = rectificar_imagen(img)
    print(f"Esquinas mesa detectadas: {len(esquinas)}")
    print(f"Imagen rectificada: {img_rect.shape[1]}x{img_rect.shape[0]} px")

    # ═══════════════════════════════════════════════════════════════════════
    # SECCIÓN 0b — RECORTE DE BORDES
    # ═══════════════════════════════════════════════════════════════════════
    H, W = img_rect.shape[:2]
    x0 = int(W * 0.20)          # quitar 20 % a la izquierda
    x1 = int(W * 0.95)          # quitar 5 % a la derecha
    y0 = int(H * 0.05)          # quitar 5 % arriba
    y1 = int(H * 0.95)          # quitar 5 % abajo
    img_crop = img_rect[y0:y1, x0:x1]

    print(f"Imagen recortada: {img_crop.shape[1]}x{img_crop.shape[0]} px")

    # ═══════════════════════════════════════════════════════════════════════
    # SECCIÓN 1 — DETECCIÓN (lógica pura)
    # ═══════════════════════════════════════════════════════════════════════
    piezas = detectar_piezas(img_crop)
    print(f"\nPiezas detectadas: {len(piezas)}")

    # Ajustar coordenadas al espacio de la imagen rectificada completa
    for p in piezas:
        p["centro_x"] += x0
        p["centro_y"] += y0
        (cx, cy), (w, h), angle = p["_rect"]
        p["_rect"] = ((cx + x0, cy + y0), (w, h), angle)
        p["_contour"] = p["_contour"] + np.array([[x0, y0]])

    print(f"{'N°':>3}  {'Centro (px)':^18}  {'Ancho':>7}  {'Alto':>7}  {'Ángulo':>9}")
    print("-" * 55)
    for p in piezas:
        print(
            f"{p['numero']:>3}  "
            f"({p['centro_x']:>5}, {p['centro_y']:>5})  "
            f"{p['ancho']:>7}px  "
            f"{p['alto']:>7}px  "
            f"{p['angulo_grados']:>8.2f}°"
        )

    refs = detectar_referencias(img_rect)
    ref1_px_detectado = refs["ref1"]
    ref2_px_detectado = refs["ref2"]

    print("\nReferencias detectadas:")
    print(f"  Ref 1 (img):  ({ref1_px_detectado[0]:.2f}, {ref1_px_detectado[1]:.2f})")
    print(f"  Ref 2 (img):  ({ref2_px_detectado[0]:.2f}, {ref2_px_detectado[1]:.2f})")

    # ═══════════════════════════════════════════════════════════════════════
    # SECCIÓN 2 — CALIBRACIÓN Y TRANSFORMACIÓN (lógica pura)
    # ═══════════════════════════════════════════════════════════════════════
    cal = calcular_calibracion(
        ref1_px_detectado, REF1_ROBOT,
        ref2_px_detectado, REF2_ROBOT,
    )
    print("\nParámetros de calibración (similitud con reflexión Y):")
    print(f"  escala s = {cal['s']:.6f} mm/px")
    print(f"  rotación θ = {cal['theta_grados']:.2f}°")
    print(f"  traslación c = {cal['c']:.2f}, f = {cal['f']:.2f}")

    piezas_robot = []
    for p in piezas:
        # Centro
        rx, ry = pixel_a_robot(p["centro_x"], p["centro_y"], cal)

        # Dimensiones: escala uniforme
        ancho_mm = p["ancho"] * cal["s"]
        alto_mm = p["alto"] * cal["s"]

        # Ángulo: transformar las 4 esquinas del rectángulo al espacio robot
        box = cv2.boxPoints(p["_rect"])                 # (4,2) en px
        ones = np.ones((4, 1), dtype=np.float32)
        box_h = np.concatenate([box, ones], axis=1)     # (4,3)
        box_robot = (cal["M"] @ box_h.T).T              # (4,2) en mm
        rect_robot = cv2.minAreaRect(box_robot.astype(np.float32))
        (_, _), (w_r, h_r), angle_r = rect_robot
        _, _, angulo_robot = normalizar_rect(w_r, h_r, angle_r)

        piezas_robot.append({
            "numero": p["numero"],
            "robot_x": round(rx, 2),
            "robot_y": round(ry, 2),
            "ancho_mm": round(ancho_mm, 2),
            "alto_mm": round(alto_mm, 2),
            "angulo_grados": round(angulo_robot, 2),
        })

    # ═══════════════════════════════════════════════════════════════════════
    # SECCIÓN 3 — SERIALIZACIÓN JSON (salida definitiva)
    # ═══════════════════════════════════════════════════════════════════════
    guardar_json(piezas, IMAGEN_ENTRADA, JSON_DETECCION)
    print(f"\nJSON detección guardado: {JSON_DETECCION}")

    datos_salida = {
        "imagen": IMAGEN_ENTRADA.name,
        "total_piezas": len(piezas_robot),
        "piezas": piezas_robot,
        "calibracion": {
            "ref1_px": {"x": round(ref1_px_detectado[0], 2), "y": round(ref1_px_detectado[1], 2)},
            "ref1_robot": {"x": REF1_ROBOT[0], "y": REF1_ROBOT[1]},
            "ref2_px": {"x": round(ref2_px_detectado[0], 2), "y": round(ref2_px_detectado[1], 2)},
            "ref2_robot": {"x": REF2_ROBOT[0], "y": REF2_ROBOT[1]},
            "escala_mm_px": round(cal["s"], 6),
            "rotacion_grados": cal["theta_grados"],
            "matriz_afin": {
                "m11": round(cal["a"], 6),
                "m12": round(cal["b"], 6),
                "m13": round(cal["c"], 2),
                "m21": round(cal["b"], 6),
                "m22": round(-cal["a"], 6),
                "m23": round(cal["f"], 2),
            },
        },
    }
    with open(JSON_ROBOT, "w", encoding="utf-8") as f:
        json.dump(datos_salida, f, indent=2, ensure_ascii=False)

    print(f"JSON robot guardado: {JSON_ROBOT}")
    print("\nPiezas en coordenadas robot:")
    print(f"{'N°':>3}  {'Robot X (mm)':>12}  {'Robot Y (mm)':>12}  {'Ancho':>8}  {'Alto':>8}  {'Ángulo':>9}")
    print("-" * 65)
    for p in piezas_robot:
        print(
            f"{p['numero']:>3}  "
            f"{p['robot_x']:>12.2f}  "
            f"{p['robot_y']:>12.2f}  "
            f"{p['ancho_mm']:>7.1f}mm  "
            f"{p['alto_mm']:>7.1f}mm  "
            f"{p['angulo_grados']:>8.2f}°"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # SECCIÓN 4 — VISUALIZACIÓN (opcional, solo para validación humana)
    # ═══════════════════════════════════════════════════════════════════════
    # Comentar o eliminar todo este bloque si no se necesitan imágenes.

    # Preparar dicts mezclados para dibujo (sin modificar los originales)
    piezas_dibujo_cam = [dict(p) for p in piezas]
    piezas_dibujo_rob = []
    for p, pr in zip(piezas, piezas_robot):
        pd = dict(p)
        pd["robot_x"] = pr["robot_x"]
        pd["robot_y"] = pr["robot_y"]
        pd["ancho_mm"] = pr["ancho_mm"]
        pd["alto_mm"] = pr["alto_mm"]
        piezas_dibujo_rob.append(pd)

    # Modo cámara (px) — dibujado sobre la imagen rectificada
    img_anotada = dibujar_anotaciones(img_rect, piezas_dibujo_cam, modo="camara")
    dibujar_referencias(img_anotada, refs)
    cv2.imwrite(str(IMAGEN_ANOTADA), img_anotada)
    print(f"\nImagen anotada guardada: {IMAGEN_ANOTADA}")

    # Modo robot (mm) — dibujado sobre la imagen rectificada
    img_anotada_robot = dibujar_anotaciones(img_rect, piezas_dibujo_rob, modo="robot")
    ref_labels_robot = {
        "ref1": pixel_a_robot(ref1_px_detectado[0], ref1_px_detectado[1], cal),
        "ref2": pixel_a_robot(ref2_px_detectado[0], ref2_px_detectado[1], cal),
    }
    dibujar_referencias(img_anotada_robot, refs, label_coords=ref_labels_robot)
    cv2.imwrite(str(IMAGEN_ANOTADA_ROBOT), img_anotada_robot)
    print(f"Imagen robot guardada:   {IMAGEN_ANOTADA_ROBOT}")


if __name__ == "__main__":
    main()

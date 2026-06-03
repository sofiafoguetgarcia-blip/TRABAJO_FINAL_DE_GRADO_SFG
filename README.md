# Sistema Colaborativo UR5e + UR3e para Manipulación y Decoración Automática de Baldosas Cerámicas

## Descripción del proyecto

Este proyecto ha sido desarrollado como parte de un Trabajo Fin de Grado y tiene como objetivo implementar una célula robótica colaborativa capaz de manipular y decorar automáticamente piezas cerámicas mediante dos robots colaborativos de Universal Robots: un UR5e y un UR3e.

El sistema integra visión artificial, procesamiento de imágenes, generación automática de trayectorias, comunicación TCP/IP y generación dinámica de programas URScript para coordinar ambos robots de forma segura dentro de una zona de trabajo compartida.

El flujo completo permite detectar baldosas cerámicas, obtener sus dimensiones y posición, adaptar automáticamente un dibujo al tamaño de cada pieza y coordinar ambos robots para realizar las tareas de manipulación y decoración.

---

## Objetivos

Los objetivos principales del proyecto son:

- Detectar automáticamente las baldosas presentes en la zona de trabajo.
- Obtener su posición, dimensiones y orientación mediante visión artificial.
- Adaptar automáticamente el tamaño del dibujo a cada baldosa.
- Generar trayectorias de dibujo a partir de una imagen.
- Coordinar dos robots colaborativos mediante comunicación TCP/IP.
- Manipular automáticamente las piezas utilizando un sistema de vacío.
- Realizar dibujos sobre las baldosas mediante un útil de escritura.
- Evitar accesos simultáneos a la zona compartida.

---

## Arquitectura general del sistema

```text
                    CÁMARA
                       │
                       ▼
            Sistema de Visión Artificial
                       │
                       ▼
                 datos_robot.json
                       │
                       ▼
                    main.py
                       │
       ┌───────────────┼───────────────┐
       ▼                               ▼
Generación URScript            Comunicación TCP/IP
       │                               │
       ▼                               ▼
     UR5e                           UR3e
(Manipulación)                 (Decoración)
       │                               │
       └────── Zona Compartida ────────┘
```

---

## Robots utilizados

### UR5e

El UR5e es el encargado de la manipulación de las piezas cerámicas:

- Recoge la baldosa en su posición original.
- Transporta la pieza hasta la zona compartida.
- Espera a que el UR3e finalice el dibujo.
- Recoge nuevamente la pieza.
- La devuelve a su posición original.

### UR3e

El UR3e es el encargado de la decoración:

- Detecta automáticamente la superficie mediante sensor de fuerza.
- Ajusta la altura de dibujo.
- Ejecuta las trayectorias generadas.
- Dibuja sobre la superficie de la baldosa utilizando un útil de escritura.

---

## Sistema de visión artificial

La detección de baldosas se realiza mediante una cámara fija situada sobre la zona de trabajo.

El sistema de visión genera un archivo JSON con toda la información necesaria para el resto del sistema:

```json
{
  "imagen": "DSC07665.jpg",
  "total_piezas": 9,
  "piezas": [
    {
      "numero": 1,
      "robot_x": 160.88,
      "robot_y": -399.15,
      "ancho_mm": 139.7,
      "alto_mm": 140.67,
      "angulo_grados": -8.35
    }
  ]
}
```

El módulo `vision.py` se encarga de:

- Leer el JSON.
- Validar los datos.
- Convertir milímetros a metros.
- Devolver la información preparada para los robots.

Las coordenadas calculadas por visión se utilizan directamente, sin aplicar offsets ni transformaciones adicionales.

---

## Procesamiento de imágenes

El dibujo que realizará el UR3e se obtiene a partir de una imagen.

Ejemplo:

```text
flor_simple.jpg
```

El módulo `image_processing.py` realiza:

1. Conversión a escala de grises.
2. Suavizado mediante filtro Gaussiano.
3. Detección de bordes mediante:
   - Canny fino.
   - Canny grueso.
   - Gradiente morfológico.
4. Combinación de resultados.
5. Limpieza mediante operaciones morfológicas.
6. Generación de una imagen de depuración (`debug_edges.png`).

El objetivo es obtener contornos robustos y continuos para generar posteriormente las trayectorias de dibujo.

---

## Adaptación automática del dibujo

No todas las baldosas tienen el mismo tamaño.

Por este motivo, el dibujo se adapta automáticamente utilizando el lado menor de la pieza.

La escala se define mediante:

```python
DRAWING_SCALE_ON_TILE = 0.75
```

Por defecto el dibujo ocupa aproximadamente el 75% del lado menor de la baldosa.

Además, se establecen límites mínimos y máximos de seguridad:

```python
MIN_DRAWING_WIDTH_M
MAX_DRAWING_WIDTH_M
```

Esto evita generar dibujos demasiado pequeños o excesivamente grandes.

---

## Generación de trayectorias

El módulo `trajectory.py` transforma los contornos detectados en trayectorias que posteriormente seguirá el UR3e.

Proceso:

1. Detección de contornos.
2. Ordenación por longitud.
3. Eliminación de ruido.
4. Simplificación mediante `approxPolyDP`.
5. Reducción de puntos redundantes.
6. Conversión de píxeles a metros.
7. Centrando el dibujo respecto al origen.

El resultado final es una lista de trayectorias:

```python
[
    [(x1,y1), (x2,y2), ...],
    [(x1,y1), (x2,y2), ...]
]
```

Cada trayectoria representa un trazo independiente.

---

## Generación automática de URScript

Para cada baldosa se generan tres programas URScript.

### 1. Recogida de la pieza

Archivo:

```text
pieza_X_ur5_recoger.urscript
```

Funciones:

- Ir a la pieza.
- Detectar la superficie mediante fuerza.
- Activar la ventosa.
- Transportar la baldosa.
- Depositarla en la zona compartida.

---

### 2. Dibujo sobre la baldosa

Archivo:

```text
pieza_X_ur3_dibujar.urscript
```

Funciones:

- Detectar la superficie.
- Ajustar automáticamente la altura de dibujo.
- Ejecutar las trayectorias generadas.
- Volver a posición HOME.

---

### 3. Devolución de la pieza

Archivo:

```text
pieza_X_ur5_devolver.urscript
```

Funciones:

- Recoger la baldosa de la zona compartida.
- Transportarla a su posición original.
- Liberarla.
- Volver a posición HOME.

---

## Comunicación entre robots

La coordinación se realiza mediante TCP/IP.

### Puertos utilizados

```python
PORT_UR5_LISTO_UR3 = 50001
PORT_UR3_LISTO_UR5 = 50002
```

### Mensaje de sincronización

```text
LISTO
```

### Flujo de coordinación

```text
UR5e recoge pieza
          │
          ▼
UR5e deposita en zona compartida
          │
          ▼
UR5e → LISTO
          │
          ▼
PC envía script al UR3e
          │
          ▼
UR3e dibuja
          │
          ▼
UR3e → LISTO
          │
          ▼
PC envía script al UR5e
          │
          ▼
UR5e devuelve pieza
```

Esta estrategia garantiza que ambos robots nunca accedan simultáneamente a la zona compartida.

---

## Seguridad

El sistema incorpora varias medidas de seguridad:

### Detección por fuerza

UR5e:

```python
F_UMBRAL_UR5 = 1.2
```

UR3e:

```python
F_UMBRAL_UR3 = 1.2
```

### Posiciones HOME

Ambos robots disponen de posiciones de reposo seguras.

### Zona compartida controlada

La sincronización mediante TCP/IP evita accesos simultáneos.

### Limitación geométrica

Se utilizan:

- Alturas de aproximación.
- Velocidades reducidas.
- Detección táctil.
- Retirada automática.

para minimizar el riesgo de colisiones.

---

## Estructura del proyecto

```text
Proyecto/
│
├── main.py
├── config.py
├── vision.py
├── image_processing.py
├── drawing_scale.py
├── trajectory.py
├── transform.py
├── robot_comm.py
├── urscript_generator.py
│
├── imagenes/
│   └── flor_simple.jpg
│
├── resultados/
│   ├── datos_robot.json
│   ├── pieza_1_ur5_recoger.urscript
│   ├── pieza_1_ur3_dibujar.urscript
│   └── pieza_1_ur5_devolver.urscript
│
└── debug_edges.png
```

---

## Instalación

### Requisitos

- Python 3.10 o superior
- OpenCV
- NumPy
- Robots Universal Robots UR3e y UR5e
- Conexión TCP/IP entre PC y robots

### Instalación de dependencias

```bash
pip install opencv-python numpy
```

---

## Ejecución

Procesar todas las piezas:

```bash
python main.py
```

Procesar una pieza concreta:

```bash
python main.py --pieza 3
```

Generar únicamente los scripts URScript sin mover los robots:

```bash
python main.py --pieza 3 --dry-run
```

---

## Resultados generados

El sistema genera automáticamente:

- Imagen de depuración de bordes.
- Scripts URScript de recogida.
- Scripts URScript de dibujo.
- Scripts URScript de devolución.

Todos los programas generados se almacenan en la carpeta:

```text
Resultados/
```

---

## Posibles mejoras futuras

- Calibración automática cámara-robot.
- Utilización del ángulo detectado por visión para orientar las piezas.
- Optimización de trayectorias.
- Planificación avanzada de movimientos.
- Evaluación de riesgos conforme a ISO 10218:2025.
- Integración de herramientas industriales de decoración cerámica.
- Procesamiento simultáneo de múltiples diseños.

---

## Autora

Sofía Foguet García

Trabajo Fin de Grado

Universitat Jaume I

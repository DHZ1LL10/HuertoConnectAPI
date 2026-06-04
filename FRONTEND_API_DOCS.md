# 📚 Documentación de Consumo API (Para Equipo Frontend)

Este documento contiene la guía oficial para que el equipo de Frontend (Web / Móvil) pueda conectarse a los microservicios de **Huerto Connect**, enfocándose especialmente en los nuevos endpoints de **Inteligencia Artificial**.

---

## 🏗️ Arquitectura y Puertos Base

El backend está dividido en 3 servicios principales que corren en puertos distintos. Asegúrense de apuntar sus peticiones (axios, fetch, http) al puerto correcto:

1. **API Gateway (Autenticación y Sesiones)**
   * **URL Base:** `http://localhost:3000/api`
   * **Propósito:** Login, Registro, OTP, Gestión de usuarios.

2. **Huertos Service (IA - Random Forest)**
   * **URL Base:** `http://localhost:8000/api/huertos`
   * **Propósito:** Recomendaciones predictivas de cultivos con datos de clima.

3. **Plagas Service (IA - YOLOv8 Visión Artificial)**
   * **URL Base:** `http://localhost:8003/api/plagas`
   * **Propósito:** Subida de imágenes, detección de plagas y tratamientos.

---

## 🔐 Autenticación Universal (JWT)

Todos los endpoints protegidos (incluyendo los de IA) requieren que el usuario haya iniciado sesión en el Gateway (puerto `3000`).
El Gateway les devolverá un `token` en la respuesta del Login/Verificación OTP. 

Ese token deben mandarlo en los **Headers** de **todas** las peticiones a la IA:

```json
{
  "Authorization": "Bearer eyJhbGciOiJIUz...",
  "Content-Type": "application/json"
}
```

---

## 🤖 1. Endpoint: Recomendación Inteligente de Cultivos

Este endpoint toma la ubicación GPS del usuario, consulta el clima en vivo y lo pasa por el modelo de *Random Forest* para recomendar qué sembrar.

* **URL:** `POST http://localhost:8000/api/huertos/recomendar`
* **Header requerido:** `Authorization: Bearer <token>`

### Request Body (JSON)
Deberán enviar la latitud, longitud y municipio del usuario:
```json
{
  "lat": 19.5312,
  "lon": -96.9276,
  "municipio": "Xalapa"
}
```

### Response Exitosa (200 OK)
Devolverá el clima actual y un arreglo de 3 recomendaciones. 
**Recomendación UI:** Pinten el campo `justificacion` para que el usuario entienda la decisión de la IA.

```json
{
  "clima": {
    "temp_actual": 17.8,
    "humedad": 97,
    "descripcion": "Lluvia ligera",
    "ciudad": "Xalapa"
  },
  "recomendaciones": [
    {
      "cultivo": "Tomate",
      "confianza": 0.85,
      "justificacion": "Modelo predictivo basado en Xalapa, temp: 17.8°C, humedad: 97%",
      "temporada_ideal": "Otoño-Invierno (Oct–Feb)",
      "tecnica_riego": "Goteo, cada 2 días"
    }
  ],
  "modo": "modelo_real"
}
```

---

## 🐞 2. Endpoint: Detección de Plagas (Visión Artificial)

Este endpoint recibe la URL de una foto tomada por el usuario, la procesa a través de la Red Neuronal Convolucional (YOLOv8) y devuelve la plaga detectada junto con los tratamientos ecológicos para combatirla.

* **URL:** `POST http://localhost:8003/api/plagas/detectar`
* **Header requerido:** `Authorization: Bearer <token>`

### Request Body (JSON)
*Nota: El Frontend debe subir primero la foto a la nube (ej. Cloudinary, Firebase Storage) y mandar a este endpoint la URL pública.*

```json
{
  "imagen_url": "https://raw.githubusercontent.com/ultralytics/yolov5/master/data/images/bus.jpg"
}
```

### Response Exitosa (200 OK)
**Recomendación UI:** El nivel de `severidad` (Alta/Media/Baja) se puede usar para poner un ícono rojo/amarillo. Los `tratamientos_ecologicos` deben pintarse en tarjetas (Cards) iterando el arreglo.

```json
{
  "deteccion": {
    "plaga": "Pulgon Verde",
    "nombre_cientifico": "Myzus persicae / Aphis gossypii",
    "confianza": 0.72,
    "severidad": "Media",
    "descripcion_plaga": "Áfido verde que coloniza brotes...",
    "cultivos_afectados": ["Chile", "Jitomate"],
    "tratamientos_ecologicos": [
      {
        "nombre": "Extracto de ajo y chile",
        "tipo": "botanico",
        "descripcion": "Alicina y capsaicina repelen y dañan colonias de pulgón.",
        "aplicacion": "50 g ajo + 50 g chile / L agua. Macerar, filtrar, diluir 1:10.",
        "frecuencia": "Cada 5 días hasta eliminar colonias"
      }
    ],
    "nota_mitigacion": null
  },
  "modo": "modelo_real"
}
```

---

## 💡 Recomendaciones y Buenas Prácticas para el Frontend

1. **Manejo de Tiempos de Carga (Loading States):**
   * Los modelos de IA pesan gigabytes y hacen cálculos matemáticos complejos en milisegundos.
   * Sin embargo, descargar el clima en vivo o descargar la foto de la nube puede tomar **de 1 a 3 segundos**.
   * **Recomendación:** Pongan un *Loading Spinner* bonito (animación) o un "Skeleton Loader" mientras esperan la respuesta de los puertos `8000` y `8003`. ¡No dejen la pantalla congelada!

2. **Validación del "Modo" del Modelo:**
   * Ambas respuestas de IA devuelven un campo `"modo"`. 
   * Si en sus pruebas notan que `"modo"` dice `"mock"`, significa que al Backend (Docker) le faltó cargar los archivos `.pt` (PyTorch) o `.pkl`. Solo deben avisarle al equipo de Backend para que lo reinicie. En producción **siempre** debe decir `"modelo_real"`.

3. **Excepción: Araña Roja vs Mancha Foliar:**
   * El modelo de visión de plagas (YOLO) fue entrenado con la versión V1. Existe un ligero solapamiento visual entre etapas tempranas de Araña Roja y Mancha Foliar.
   * Si el modelo detecta Mancha Foliar, enviará un aviso en el campo `nota_mitigacion`. Asegúrense de **mostrar esa nota** en pantalla ("Tip: Si notas telarañas, revisa tratamientos de Araña Roja"). Esto hará ver al sistema mucho más inteligente y "humano" durante las presentaciones o demos.

4. **CORS:**
   * Si les da error de CORS, asegúrense de estar corriendo la app desde la URL configurada en el `.env` del backend (por defecto `http://localhost:4200` o `http://localhost:8081`).

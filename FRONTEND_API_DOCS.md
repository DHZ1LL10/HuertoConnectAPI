# 📚 Documentación Completa de Consumo API (Frontend)

Este documento es la guía definitiva para conectar el Frontend (Web / Móvil) con el Backend de Huerto Connect. 

---

## 🏗️ URL Base Única (API Gateway)

El backend usa un **API Gateway** (Proxy Inverso) que centraliza TODAS las peticiones en un solo puerto. No necesitas conectarte a diferentes puertos para cada cosa.

* **Si estás probando localmente:** Usa `http://localhost:8000/api`
* **Si te pasaron un link de LocalTunnel/Ngrok:** Usa `https://<URL_GENERADA>.loca.lt/api`

Todo el tráfico debe apuntar a esa única URL base.

---

## 🔐 1. AUTENTICACIÓN Y SESIONES (`/auth`)

Aquí inicia la sesión el usuario y es donde obtienes el **Token JWT** que usarás para todas las demás peticiones.

* **`POST /auth/register`** (Registrar usuario)
  * **Body:** `{ "firstName": "Juan", "lastName": "Perez", "email": "juan@correo.com", "password": "Password123!" }`

* **`POST /auth/send-otp`** (Iniciar Login)
  * **Body:** `{ "email": "juan@correo.com", "password": "Password123!" }`
  * **Response:** Envía un código OTP de 6 dígitos al correo.

* **`POST /auth/verify-otp`** (Confirmar Login)
  * **Body:** `{ "email": "juan@correo.com", "otp": "123456" }`
  * **Response:** Devuelve la información del usuario y el **`token` JWT** (¡GUÁRDALO EN LOCALSTORAGE/SECURESTORAGE!).

* **`GET /auth/me`** (Mi Perfil)
  * **Headers:** `Authorization: Bearer <TU_TOKEN>`

---

## 🤖 2. IA HUERTOS (`/huertos`)
*(Requiere Header: `Authorization: Bearer <TU_TOKEN>`)*

* **`POST /huertos/recomendar`** (Recomendación Predictiva de Cultivos)
  * **Body:**
    ```json
    {
      "lat": 19.5312,
      "lon": -96.9276,
      "municipio": "Xalapa"
    }
    ```
  * **Response:** Descarga el clima real y usa *Random Forest* para devolver los 3 cultivos más óptimos con su nivel de confianza y técnica de riego.

---

## 🐞 3. IA PLAGAS (`/plagas`)
*(Requiere Header: `Authorization: Bearer <TU_TOKEN>`)*

* **`POST /plagas/detectar`** (Detección por Visión Artificial)
  * **Nota:** Debes subir la foto tomada por la cámara a tu nube (Cloudinary/S3) y luego enviar la URL pública aquí.
  * **Body:**
    ```json
    {
      "imagen_url": "https://raw.githubusercontent.com/ultralytics/yolov5/master/data/images/bus.jpg"
    }
    ```
  * **Response:** El modelo *YOLOv8* analiza la foto y devuelve el nombre de la plaga, severidad y tratamientos ecológicos.

---

## 💡 Buenas Prácticas UI/UX para el Frontend

1. **Loading States en IA:** Las peticiones `/recomendar` y `/detectar` tardan de 1 a 3 segundos porque procesan matemáticas complejas y descargan imágenes. Pon un *Spinner* o *Skeleton Loader* mientras esperas.
2. **Tokens Vencidos:** Si el backend te responde `401 Unauthorized`, cierra la sesión y manda al usuario a Login.
3. **Swagger UI:** Si quieres probar la API de forma visual, entra desde tu navegador a la URL base y agrega `/docs` al final (ej. `http://localhost:8000/docs`). ¡Ahí está todo el catálogo interactivo!

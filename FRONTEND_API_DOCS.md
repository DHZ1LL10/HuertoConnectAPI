# 📚 Documentación Completa de Consumo API (Frontend)

Este documento es la guía definitiva para conectar el Frontend (Web / Móvil) con los **3 microservicios** que conforman el Backend de Huerto Connect. 

---

## 🏗️ Puertos y URLs Base

El backend corre en 3 servicios distintos. Dependiendo de la función, debes apuntar a un puerto u otro:

1. **API Gateway (Auth & Usuarios)** 👉 `http://localhost:3000`
2. **Huertos Service (IA Cultivos)** 👉 `http://localhost:8000`
3. **Plagas Service (IA Visión)** 👉 `http://localhost:8003`

---

## 🔐 1. API GATEWAY (Puerto `3000`)
**URL Base:** `http://localhost:3000/api`

Este es el módulo central. Aquí inicia la sesión el usuario y es quien **te entrega el Token JWT** que usarás para todas las demás peticiones.

### Autenticación y Cuentas (`/auth`)

* **`POST /auth/register`** (Registrar usuario)
  * **Body:** `{ "firstName": "Juan", "lastName": "Perez", "email": "juan@correo.com", "password": "Password123!" }`
  * **Response:** Envía un código OTP al correo.

* **`POST /auth/send-otp`** (Iniciar Login)
  * **Body:** `{ "email": "juan@correo.com", "password": "Password123!" }`
  * **Response:** Si las credenciales son correctas, envía un código OTP de 6 dígitos al correo.

* **`POST /auth/verify-otp`** (Confirmar Login)
  * **Body:** `{ "email": "juan@correo.com", "otp": "123456" }`
  * **Response:** Devuelve la información del usuario y el **`token` JWT** (¡GUÁRDALO EN LOCALSTORAGE/SECURESTORAGE!).

* **`POST /auth/forgot-password`** (Olvidé mi contraseña)
  * **Body:** `{ "email": "juan@correo.com" }`
  * **Response:** Envía un OTP para recuperar la cuenta.

* **`POST /auth/reset-password`** (Cambiar contraseña)
  * **Body:** `{ "resetToken": "...", "newPassword": "NuevaPassword123!" }`

* **`GET /auth/me`** (Mi Perfil)
  * **Headers:** `Authorization: Bearer <TU_TOKEN>`
  * **Response:** Devuelve los datos del usuario logueado.

* **`POST /auth/logout`** (Cerrar sesión)
  * **Headers:** `Authorization: Bearer <TU_TOKEN>`

### Recursos de Usuario (`/user`)
*(Requieren Header: `Authorization: Bearer <TU_TOKEN>`)*

* **`GET /user/huertos`** -> Devuelve la lista de huertos del usuario.
* **`GET /user/dashboard`** -> Devuelve el dashboard principal del productor.

---

## 🤖 2. IA HUERTOS SERVICE (Puerto `8000`)
**URL Base:** `http://localhost:8000/api/huertos`

*(Requiere Header: `Authorization: Bearer <TU_TOKEN>`)*

* **`POST /recomendar`** (Recomendación Predictiva)
  * **Body:**
    ```json
    {
      "lat": 19.5312,
      "lon": -96.9276,
      "municipio": "Xalapa"
    }
    ```
  * **Response:** Descarga el clima real y lo pasa por un modelo *Random Forest* para devolver los 3 cultivos más óptimos con su nivel de confianza y técnica de riego.

---

## 🐞 3. IA PLAGAS SERVICE (Puerto `8003`)
**URL Base:** `http://localhost:8003/api/plagas`

*(Requiere Header: `Authorization: Bearer <TU_TOKEN>`)*

* **`POST /detectar`** (Detección por Visión Artificial)
  * **Nota Front:** Primero debes subir la foto tomada por la cámara a tu nube (Cloudinary/S3) y luego enviar la URL pública aquí.
  * **Body:**
    ```json
    {
      "imagen_url": "https://raw.githubusercontent.com/ultralytics/yolov5/master/data/images/bus.jpg"
    }
    ```
  * **Response:** El modelo *YOLOv8* analiza la foto y devuelve:
    * Nombre de la plaga.
    * Nivel de Severidad (Alta/Media/Baja).
    * Arreglo `tratamientos_ecologicos` (Itera este arreglo para crear tarjetas con curas botánicas/biológicas).

---

## 💡 Buenas Prácticas UI/UX para el Frontend

1. **Tokens Vencidos:** Si el backend te responde `401 Unauthorized`, cierra la sesión del usuario inmediatamente y mándalo a la pantalla de Login.
2. **Loading States en IA:** Las peticiones a los puertos `8000` y `8003` pueden tardar de 1 a 3 segundos porque procesan matemáticas complejas y descargan imágenes. Pon un *Spinner* o *Skeleton Loader* mientras esperas.
3. **Manejo de Errores:** Si mandas mal una contraseña o el OTP no es válido, el Gateway (puerto `3000`) te devolverá un código HTTP `400` o `401` con un mensaje JSON. Atrapa ese error en tu `try/catch` y muéstraselo al usuario en un modal/toast.

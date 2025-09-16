# LotoWeb - Aplicación de Venta de Lotería

Esta es una aplicación web desarrollada con Python y Flask para gestionar la venta de números de lotería, siguiendo las especificaciones proporcionadas.

## 1. Descripción del Funcionamiento

La aplicación tiene dos roles de usuario:

- **Administrador**: Tiene control total sobre la plataforma.
- **Vendedor**: Puede gestionar sus clientes y registrar sus ventas.

### Funcionalidades del Administrador

- **Dashboard Principal**: Muestra acceso a todas las funciones de administrador.
- **Vendedores**: Permite crear, ver y editar la información de los vendedores.
- **Ventas (Facturas)**: Muestra un listado de **todas** las ventas de **todos** los vendedores. Se pueden aplicar filtros.
- **Comisiones**: Genera un reporte de comisiones por vendedor y por sorteo. Calcula las ventas totales, la comisión, los premios pagados por los clientes de ese vendedor y el balance final.
- **Sorteos**: Permite crear nuevos sorteos (definiendo la fecha y hora) y, una vez que un sorteo ha pasado, permite ingresar los números ganadores para calcular los resultados.
- **Ganadores**: Muestra una lista de todos los ganadores para un sorteo específico.
- **Clientes**: Permite ver y gestionar la información de **todos** los clientes y a qué vendedor están asignados.

### Funcionalidades del Vendedor

- **Dashboard Principal**: Muestra acceso a las funciones del vendedor.
- **Clientes**: Permite crear, ver y editar la información de **sus propios** clientes.
- **Nueva Venta**: Un formulario para registrar una nueva venta para uno de sus clientes, eligiendo un sorteo futuro y añadiendo los números (billetes o chances) que el cliente desea comprar.
- **Mis Ventas**: Un listado de todas las ventas que el vendedor ha realizado.
- **Ganadores**: Muestra una lista de los ganadores que pertenecen a **sus propios** clientes para un sorteo específico.

## 2. Estructura de la Base de Datos

La aplicación está diseñada para ser flexible con la base de datos:

-   **Desarrollo Local (SQLite)**: Por defecto, si no se especifica una `DATABASE_URL`, la aplicación utiliza un archivo SQLite (`lottery.db`). Este es ideal para el desarrollo y pruebas locales.
-   **Producción (PostgreSQL)**: Para entornos de producción (como Render), la aplicación se conecta a una base de datos PostgreSQL si la variable de entorno `DATABASE_URL` está configurada.

Ambas bases de datos contienen las siguientes tablas principales:

-   `users`: Almacena la información de los usuarios (administradores y vendedores), incluyendo sus credenciales y porcentaje de comisión.
-   `clients`: Guarda los datos de los clientes finales, asociados a un vendedor.
-   `raffles`: Contiene la información de cada sorteo, incluyendo la fecha y los números ganadores una vez que se ingresan.
-   `invoices`: La cabecera de cada factura o venta, asociada a un sorteo, un cliente y un vendedor.
-   `invoice_items`: El detalle de cada venta, guardando cada número, la cantidad, y el tipo (billete o chance).
-   `winners`: Una vez que se calculan los resultados, esta tabla almacena cada número ganador, el cliente, el tipo de premio y el monto a pagar.

## 3. Tecnologías Utilizadas

- **Backend**: Python con el framework Flask.
- **Base de Datos**: SQLite (un solo archivo, `lottery.db`, fácil de manejar).
- **Frontend**: HTML con el sistema de plantillas Jinja2 (integrado en Flask) y CSS simple para el diseño.

## 4. Cómo Ejecutar la Aplicación en Windows

Sigue estos pasos desde una terminal o línea de comandos (`cmd` o `PowerShell`) en la carpeta `c:\WSGemini`.

### Paso 1: Crear un Entorno Virtual

Es una buena práctica para aislar las dependencias de este proyecto.

```bash
python -m venv venv
```

### Paso 2: Activar el Entorno Virtual

```bash
.\venv\Scripts\activate
```

Verás `(venv)` al principio de la línea de tu terminal, indicando que el entorno está activo.

### Paso 3: Instalar las Dependencias

Necesitarás instalar Flask y Werkzeug (para las contraseñas).

```bash
pip install Flask werkzeug
```

### Paso 4: Inicializar la Base de Datos (Solo para SQLite local)

Este comando creará el archivo `lottery.db` y las tablas necesarias para el desarrollo local con SQLite. También creará los dos usuarios por defecto. **Solo necesitas ejecutarlo una vez.**

```bash
flask --app app initdb
```

Verás mensajes indicando que la base de datos y los usuarios por defecto fueron creados.

**Nota para Producción (PostgreSQL):** Si estás desplegando en un entorno como Render que usa PostgreSQL, la inicialización de la base de datos (creación de tablas y usuarios iniciales) deberá realizarse directamente en la base de datos PostgreSQL, posiblemente ejecutando el esquema `schema_postgres.sql` y scripts de inserción de datos apropiados. La función `init_db()` en `database.py` actualmente solo soporta la inicialización de SQLite.

### Paso 5: Ejecutar la Aplicación

```bash
flask --app app run
```

La aplicación estará corriendo. Abre tu navegador web y ve a la siguiente dirección:

**http://127.0.0.1:5000**

## 6. Flujo de Trabajo y Despliegue

Este proyecto sigue un flujo de trabajo que integra desarrollo local, control de versiones con GitHub y despliegue continuo con Render.

-   **Control de Versiones (GitHub)**: El código fuente se gestiona en un repositorio de GitHub. Los cambios locales se suben a este repositorio para mantener un historial de versiones y facilitar la colaboración.
-   **Despliegue Continuo (Render)**: La aplicación está configurada para desplegarse automáticamente en Render.com cada vez que se suben cambios a la rama principal (main) del repositorio de GitHub. Render utiliza la variable de entorno `DATABASE_URL` para conectarse a una base de datos PostgreSQL en producción.

### Cambios Recientes Realizados

Durante la sesión actual, se han implementado los siguientes cambios:

- **sales.html**: Se actualizó la lógica para que, por defecto, se muestren las ventas del sorteo más reciente. Esto incluye ajustes en el backend (`app.py`) para establecer el `selected_raffle_id` al ID del sorteo más reciente.
- **Estilo y Diseño**: Se realizaron mejoras en la disposición de columnas y en la responsividad para dispositivos móviles y de escritorio.
- **Flujo de Trabajo**: Se verificó que los cambios se alineen con los requisitos del usuario y se subieron al repositorio de GitHub en la rama principal (`main`).

## 5. Credenciales de Acceso por Defecto

- **Usuario Administrador**:
  - **Usuario**: `admin`
  - **Contraseña**: `adminpass`

- **Usuario Vendedor**:
  - **Usuario**: `vendedor1`
  - **Contraseña**: `vendedorpass`

¡Y eso es todo! La aplicación está lista para ser probada.

# LI Punto de Venta

Base funcional de POS inspirada en los módulos y el stack documentados para TPN. El código fuente privado original de TPN no estaba disponible: **no es una copia literal**.

## Probar sin Docker

### Windows: abrir con doble clic

1. Descarga el repositorio completo como ZIP desde GitHub y extráelo, o clónalo con Git.
2. Instala Python 3.12 con la opción **Add python.exe to PATH**.
3. Haz doble clic en `INICIAR_LI_POS.bat` desde la carpeta extraída. La primera vez instalará dependencias y te pedirá crear un usuario administrador (empresa de demo: `1`).
4. Al terminar, se abrirá `http://127.0.0.1:8000` en tu navegador. Conserva tus credenciales; no están incluidas en el repositorio.

El lanzador usa SQLite y no requiere Docker. Si ya existe un `pos.db` de una versión anterior, **lo respalda y migra si reconoce su versión**; para bases antiguas no reconocidas, consulta `docs/operations/SEGURIDAD_Y_MIGRACIONES.md`. La primera instalación necesita conexión a internet para descargar las dependencias de Python.

### Consola

```bash
cd LI-PUNTO-DE-VENTA
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Mac/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
python scripts/create_admin.py
uvicorn backend.app.main:app --reload
```

Abrir http://localhost:8000. Por defecto usa SQLite local en `pos.db`. Para PostgreSQL: `docker compose -f infrastructure/docker-compose.yml up --build`; Docker requiere virtualización habilitada. API en `/docs`.

## Módulos y alcance

Se conserva el árbol ya creado en GitHub: `backend/app/api`, `core`, `db`, `services`, `integrations`; `frontend/public` y `frontend/src/features`; `desktop`, `database`, `infrastructure`, `docs`, `scripts` y `tests`. Se reservan carpetas para ventas, caja, inventario, productos, clientes, proveedores, compras, devoluciones, traspasos, cotizaciones, facturación, reportes, usuarios, auditoría, configuración, Clip y sucursales. **Actualmente funcionan catálogo editable con código de barras e impuestos, existencias y costo promedio por sucursal, kardex, traspasos, conteos físicos, cajas y turnos por cajero, entradas/retiros autorizados, ventas y descuentos autorizados, tickets con folio, clientes, proveedores, órdenes y recepciones parciales, historial, resumen y bitácora.** Los demás módulos siguen pendientes.

Demo: seis sucursales configuradas para la empresa de prueba 1, usuarios con contraseña Argon2 y sesión JWT, impuestos configurables por producto, sin procesamiento real de pagos. En producción faltan revocación y límites de intentos de inicio de sesión, pruebas de concurrencia PostgreSQL, folios fiscales, facturación CFDI/PAC, Clip y modo offline con sincronización. La clave de reintento actual solo cubre ventas en línea. Las rutas de operación exigen autenticación y permisos; aún no está autorizada para ventas reales. Consulta `docs/operations/SEGURIDAD_Y_MIGRACIONES.md`.

## Ticket de venta

Después de confirmar una venta, la pantalla muestra un comprobante con sucursal, productos, impuestos, total, pago y cambio. También puedes abrir el ticket desde el historial, imprimirlo o preparar un mensaje de WhatsApp; el envío requiere una acción manual. `GET /api/sales/{id}` devuelve el detalle solo a usuarios autorizados para esa sucursal. Este comprobante no es una factura CFDI.

## Traspasos entre sucursales

Un administrador puede enviar inventario a otra sucursal asignada desde la pantalla. `POST /api/stock/transfers` exige permiso de inventario, acceso a ambas sucursales y una cabecera `Idempotency-Key` de 8 a 100 caracteres. Descuenta origen, suma destino y registra salida, entrada y auditoría en una sola transacción. Repetir la misma solicitud con la misma clave devuelve el traspaso existente; cambiar los datos con esa clave produce un conflicto. Para una base con Alembic, ejecuta `alembic upgrade head` antes de iniciar la nueva versión. La interfaz todavía no muestra un listado específico de traspasos; los movimientos pueden consultarse en `/api/stock/movements`.

## Clientes

Se pueden registrar, buscar y editar clientes con nombre y teléfono opcional, y asociarlos a una venta desde la pantalla de caja. El historial muestra compras de ese cliente en la sucursal autorizada; el ticket conserva el nombre que tenía cuando se cobró. Las rutas de clientes requieren sesión y permisos. Los datos fiscales y el consentimiento para comunicaciones siguen pendientes. Antes de iniciar una base existente con Alembic, ejecuta `alembic upgrade head` para añadir el nombre histórico a ventas.

## Pruebas

`python -m pytest -q tests` desde raíz. Cada venta descuenta existencias y crea log dentro de la misma transacción. PostgreSQL usa bloqueos de fila para cobros simultáneos. No se confirman ventas con stock insuficiente ni pagos insuficientes.

## Nota de actualización

El esquema cambió. Si tienes un `pos.db` de la demo anterior, **consérvalo** y sigue `docs/operations/SEGURIDAD_Y_MIGRACIONES.md` para migrarlo con respaldo. Alembic instala el esquema nuevo, pero no convierte automáticamente una demo antigua.

Consulta `docs/operations/ESTADO_Y_PLAN.md` para el alcance real y los siguientes módulos.

Los requerimientos priorizados, criterios de aceptación y decisiones pendientes están en `docs/requirements/REQUERIMIENTOS_LI_POS.md`.

## Productos, cajas y compras

- **Productos y ventas:** agregar/editar SKU, código de barras, unidad (cantidad entera), impuesto y precio con/sin impuesto. El carrito obtiene los totales desde la API. Descuentos porcentuales requieren motivo y autorización de administración; el ticket conserva precios e impuestos históricos y un folio no fiscal.
- **Cajas y turnos:** seleccionar/crear caja, abrir un turno a nombre del usuario, registrar entradas/retiros como administrador y cerrar con diferencia. Cada cajero vende únicamente en su propio turno. Los comprobantes de movimiento y corte se imprimen desde el historial.
- **Proveedores y compras:** registrar/editar proveedor, guardar una orden con varias partidas y recibir cantidades parciales. Solo la recepción aumenta inventario, recalcula el costo promedio por sucursal y registra al receptor. La clave de reintento evita duplicados.
- **Inventario:** consultar stock/costo/kardex, traspasar y conciliar conteos físicos con motivo. Si las existencias cambian desde que se cargó el conteo, se exige actualizar y volver a contar.

Consulta `docs/operations/SEGURIDAD_Y_MIGRACIONES.md` antes de actualizar una instalación con datos. Todavía faltan cantidades fraccionarias, precios por sucursal, descuentos por partida, cancelación de órdenes, cuentas por pagar, valoración de costo desconocido, CFDI, Clip y la validación del piloto con PostgreSQL/hardware real.

## Recuperar el acceso local en Windows

Cierra el servidor antes de recuperar el acceso. Desde la raíz del proyecto ejecuta:

~~~powershell
.\.venv\Scripts\python.exe scripts/reset_local_password.py
~~~

El asistente muestra los nombres exactos, pide el usuario existente, permite corregir su nombre (Enter lo conserva) y solicita una nueva contraseña oculta con confirmación. Escribe GUARDAR para aplicar. Crea un respaldo SQLite antes del cambio y conserva el ID, empresa, rol y asignaciones. No activa cuentas desactivadas. Esta herramienta requiere acceso al archivo local pos.db; no es un endpoint web ni recuperación de PostgreSQL. Reinicia INICIAR_LI_POS.bat para invalidar las sesiones locales y entra con los nuevos datos.


## Respaldos locales

El iniciador Windows crea una copia verificada en `backups/` antes de abrir el servidor. Cada respaldo contiene `.db` y `.json`; conserva ambos archivos juntos. No se borran copias automáticamente.

Desde la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe scripts/local_backups.py create
.\.venv\Scripts\python.exe scripts/local_backups.py list
```

Recuperación, copia a otro disco y límites: [Respaldos y recuperación](docs/operations/RESPALDOS_Y_RECUPERACION.md).

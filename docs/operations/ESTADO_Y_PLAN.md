# Estado de implementación · LI Punto de Venta

## Completado en la demo

- Seis sucursales de muestra asociadas a empresa 1; selección de sucursal en pantalla.
- Productos y stock separados por sucursal; movimientos de alta, ajuste y venta consultables.
- Apertura de caja, retiro de efectivo con motivo, corte con diferencia y bloqueo de ventas con caja cerrada.
- Venta con comprobación de stock, total e IVA de demostración; clave de reintento para no duplicar la misma venta.
- Resumen de ventas por sucursal y forma de pago; historial de últimas ventas y bitácora básica.
- Pruebas de flujo para aislamiento básico, pago insuficiente, stock insuficiente, reintento, retiro y cierre.
- Ticket de venta consultable, imprimible y compartible manualmente por WhatsApp; aún no es CFDI.
- Traspasos atómicos entre sucursales autorizadas, con movimientos de salida/entrada y clave de reintento.

## Pendiente antes de producción

1. **Seguridad:** login JWT, hash Argon2, roles y asignación de sucursales implementados. Pendiente: revocación, protección contra intentos repetidos, HTTPS, revisión integral y permisos por caja/turno.
2. **Base de datos:** migración inicial Alembic y actualización de la segunda demo SQLite implementadas. Pendientes: migración de la primera demo y pruebas de concurrencia en PostgreSQL.
3. **Caja:** varias cajas y cajeros por sucursal, entradas de efectivo, autorización y comprobante de retiros, conciliación de pagos externos.
4. **Venta:** folios y series, descuentos autorizados, productos con distintos impuestos y crédito si se aprueba; el ticket actual es un comprobante no fiscal.
5. **Operación:** clientes, proveedores, compras, devoluciones, conteos, listado de traspasos y reportes detallados.
6. **Integraciones:** CFDI/PAC, Clip, flujo de cliente para WhatsApp y hardware, después de definir credenciales y conciliación.
7. **Resiliencia:** cola offline duradera, sincronización, conflictos, respaldo/restauración y monitoreo.

## Orden técnico siguiente

- Endurecer autenticación, migraciones y pruebas en PostgreSQL; separar modelos por dominio.
- Folios y series fiscales, reglas de impuestos y más operaciones de caja.
- Clientes y compras, luego devoluciones y conteos; completar la consulta de traspasos.
- PAC/Clip, operación offline y piloto controlado.

**Límite actual:** se registra una sola caja abierta por sucursal; hay permisos básicos de usuario, pero no control por turno ni cobro real. No usar para ventas reales.

Los criterios de aceptación y decisiones de negocio están en `docs/requirements/REQUERIMIENTOS_LI_POS.md`.

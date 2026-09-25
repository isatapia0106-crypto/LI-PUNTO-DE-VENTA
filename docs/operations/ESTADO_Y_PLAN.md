# Estado de implementación · LI Punto de Venta

## Completado en la demo

- Seis sucursales de muestra asociadas a empresa 1; selección de sucursal en pantalla.
- Productos y stock separados por sucursal; movimientos de alta, ajuste y venta consultables.
- Apertura de caja, retiro de efectivo con motivo, corte con diferencia y bloqueo de ventas con caja cerrada.
- Venta con comprobación de stock, total e IVA de demostración; clave de reintento para no duplicar la misma venta.
- Resumen de ventas por sucursal y forma de pago; historial de últimas ventas y bitácora básica.
- Pruebas de flujo para aislamiento básico, pago insuficiente, stock insuficiente, reintento, retiro y cierre.

## Pendiente antes de producción

1. **Seguridad:** usuarios, contraseña, sesión/JWT, roles, autorizaciones por empresa/sucursal/caja y auditoría de actor real. Las cabeceras de demo son manipulables y producción está bloqueada.
2. **Base de datos:** Alembic y migración del esquema previo; restricciones y pruebas de concurrencia en PostgreSQL. SQLite sirve solo como demo.
3. **Caja:** varias cajas y cajeros por sucursal, entradas de efectivo, autorización y comprobante de retiros, conciliación de pagos externos.
4. **Venta:** folios y series, descuentos autorizados, productos con distintos impuestos, ticket impreso y crédito si se aprueba.
5. **Operación:** clientes, proveedores, compras, devoluciones, traspasos, conteos y reportes detallados.
6. **Integraciones:** CFDI/PAC, Clip, WhatsApp y hardware, después de definir credenciales y flujos de conciliación.
7. **Resiliencia:** cola offline duradera, sincronización, conflictos, respaldo/restauración y monitoreo.

## Orden técnico siguiente

- Autenticación y permisos reales, ligados a sucursal.
- Migraciones y modelos separados por dominio; prueba en PostgreSQL.
- Folios/tickets e inventario por movimiento; más operaciones de caja.
- Clientes y compras, luego devoluciones/traspasos.
- PAC/Clip, operación offline y piloto controlado.

**Límite actual:** se registra una sola caja abierta por sucursal; no hay permisos de usuario ni cobro real. No usar para ventas reales.

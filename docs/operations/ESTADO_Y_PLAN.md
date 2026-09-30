# Estado de implementación · LI Punto de Venta

Actualizado el 30 de septiembre de 2026. Funciones verificadas en la demo local; falta aceptación operativa del piloto.

## Implementado

- Seis sucursales demo, usuarios, roles y permisos por sucursal/empresa.
- Productos editables: SKU, código de barras único por empresa, unidad de venta entera, activo/inactivo, precio e impuesto configurable (incluido, separado o exento).
- Ventas atómicas, totales calculados por línea en la API, descuentos porcentuales con motivo y autorización de administración, folio único de ticket no fiscal y reimpresión con datos históricos.
- Cajas físicas múltiples, un turno activo por caja y por cajero/sucursal, cobro exclusivo en turno propio, entradas y retiros registrados por administración, comprobantes, cortes e historial.
- Clientes: alta, búsqueda, edición, historial y vínculo con venta.
- Proveedores: alta/edición; órdenes con varias partidas, recepción parcial/completa, historial de recepción y costo promedio por producto/sucursal. Crear una orden no modifica stock.
- Inventario: kardex con actor/fecha, ajuste, traspaso que conserva costo de origen y conteo físico conciliado. El conteo verifica la existencia esperada para evitar sobrescribir movimientos recientes.
- Migración Alembic `f2b3409ac871`, actualización local con respaldo automático y comprobación de preservación de ventas/stock. El lanzador Windows migra las versiones reconocidas antes de iniciar.

## Pendiente

1. Seguridad: revocación, límite de intentos, administración completa de usuarios, HTTPS y auditoría de seguridad.
2. Empresas: razones sociales, datos fiscales y configuración por empresa/sucursal.
3. Productos/ventas: cantidades fraccionarias, precios por sucursal, vigencias, descuentos por partida, series fiscales y crédito si se aprueba.
4. Caja: solicitud y aprobación separadas de movimientos, pagos integrados y conciliación externa. Administración puede cerrar un turno ajeno; el cierre registra quién lo realizó.
5. Compras/inventario: cancelación de órdenes, impuestos de compra, cuentas por pagar, conteos masivos y valoración de inventario que no tenía costo registrado.
6. Operación: devoluciones/cancelaciones de ventas, datos fiscales de clientes, consentimiento y reportes/exportaciones completos.
7. Integraciones: PAC/CFDI, Clip, impresora/lector/cajón y operación offline si se aprueba.
8. Infraestructura: pruebas de concurrencia PostgreSQL, respaldo/restauración de producción, monitoreo y piloto con datos de cada sucursal.

## Verificación de esta entrega

Pruebas de API: aislamiento, autorización de descuentos, impuestos mixtos/precio incluido/exento, histórico de ticket, cajas por cajero, movimientos y reintentos, compras parciales, costo promedio, recepción atómica, conteos y cobros simultáneos SQLite. Prueba de migración/restauración con venta y stock antiguos. La interfaz pasó comprobación de sintaxis JavaScript; falta prueba visual en un navegador con el servidor accesible.

El ticket no es CFDI; tarjeta/transferencia son registros manuales y no confirman un pago externo. El piloto de operación real sigue pendiente.

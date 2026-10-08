# Estado de implementación · LI Punto de Venta

Actualizado el 7 de octubre de 2026. Implementación y validaciones automatizadas; la aceptación del piloto y la validación con credenciales reales siguen pendientes.

## Implementado

- Seis sucursales demo, usuarios, roles y permisos por sucursal/empresa.
- Productos editables: SKU, código de barras único por empresa, unidad de venta entera, activo/inactivo, precio e impuesto configurable (incluido, separado o exento).
- Ventas atómicas, totales calculados por línea en la API, descuentos porcentuales con motivo y autorización de administración, folio único de ticket no fiscal y reimpresión con datos históricos.
- Cajas físicas múltiples, un turno activo por caja y por cajero/sucursal, cobro exclusivo en turno propio, entradas y retiros registrados por administración, comprobantes, cortes e historial.
- Clientes: alta, búsqueda, edición, historial y vínculo con venta.
- Proveedores: alta/edición; órdenes con varias partidas, recepción parcial/completa, historial de recepción y costo promedio por producto/sucursal. Crear una orden no modifica stock.
- Inventario: kardex con actor/fecha, ajuste, traspaso que conserva costo de origen y conteo físico conciliado. El conteo verifica la existencia esperada para evitar sobrescribir movimientos recientes.
- Migración Alembic `f2b3409ac871`, actualización local con respaldo automático y comprobación de preservación de ventas/stock. El lanzador Windows migra las versiones reconocidas antes de iniciar.

## Avances posteriores\n\n- Conteos masivos de hasta 100 productos por transacción con validación de reservas, stock esperado, grupos durables e idempotencia.\n\n- Reversos de abonos con motivo y responsable; devoluciones a proveedor con reducción de stock, crédito a cuenta y saldo a favor si excede deuda. Histórico original conservado.\n\n- Cuentas por pagar: reconocimiento explícito por compra recibida completa, factura única por proveedor, saldo, vencimiento y abonos manuales externos con idempotencia y bloqueo concurrente.\n\n- Impuesto histórico por partida de compra; subtotal, impuesto y total. Recepciones conservan costo promedio sin impuestos.

- Cancelación de cantidades pendientes de compras, conservando recepciones e inventario, con bloqueo concurrente y auditoría.

- Administración de usuarios, desactivación y revocación de sesiones.
- Devoluciones parciales, cancelaciones y conservación de cortes cerrados; reembolsos integrados de Mercado Pago con confirmación antes de reintegrar inventario.
- Reportes por fecha/cajero, utilidad histórica, Excel, impresión y enlace manual WhatsApp.
- Mínimos de inventario y alertas.
- Checkout Mercado Pago, reservas, observaciones verificadas, resolución de incidencias y reintentos idempotentes. Pendiente validación real.
- Asistente local de consultas con permisos, periodos relativos y navegación a módulos; sin IA generativa externa.
- Panel de auditoría con filtros y paginación; muestra bitácora existente, no implica cobertura de todos los eventos de seguridad.
- Conciliación interna de tickets netos y pagos observados, diferencias, contracargos y devoluciones pendientes. No verifica comisiones ni depósitos bancarios.
- CI SQLite/PostgreSQL, migraciones, restauración comparada y construcción de imagen de producción; infraestructura HTTPS preparada. Falta despliegue y monitoreo operativo.

## Pendiente

1. Seguridad: revisión integral de cobertura de auditoría y controles de acceso antes del piloto.
2. Empresas: razones sociales, datos fiscales y configuración por empresa/sucursal.
3. Productos/ventas: cantidades fraccionarias, precios por sucursal, vigencias, descuentos por partida, series fiscales y crédito si se aprueba.
4. Caja: solicitud y aprobación separadas de movimientos, conciliación de comisiones y liquidaciones bancarias; validación real de pagos integrados. Administración puede cerrar un turno ajeno; el cierre registra quién lo realizó.
5. Compras/inventario: retenciones de compra y facturación parcial, importación de conteos y valoración de inventario que no tenía costo registrado.
6. Operación: datos fiscales de clientes, consentimiento y aceptación de reportes en piloto.
7. Integraciones: PAC/CFDI, Clip, impresora/lector/cajón y operación offline si se aprueba.
8. Infraestructura: ejecutar restauración y pruebas de carga en el entorno real, configurar monitoreo y realizar piloto por sucursal.

## Verificación de esta entrega

Pruebas de API: aislamiento, autorización de descuentos, impuestos mixtos/precio incluido/exento, histórico de ticket, cajas por cajero, movimientos y reintentos, compras parciales, costo promedio, recepción atómica, conteos y cobros simultáneos SQLite. Prueba de migración/restauración con venta y stock antiguos. La interfaz pasó comprobación de sintaxis JavaScript; falta prueba visual en un navegador con el servidor accesible.

El ticket no es CFDI; tarjeta/transferencia son registros manuales y no confirman un pago externo. El piloto de operación real sigue pendiente.

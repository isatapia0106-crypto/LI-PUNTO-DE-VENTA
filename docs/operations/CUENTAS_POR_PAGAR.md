# Cuentas por pagar a proveedores

Primera versión: reconoce una factura por orden completamente recibida. El importe se obtiene del total histórico de compra con impuestos; se captura referencia y fecha de vencimiento. La factura es una referencia administrativa, no un CFDI timbrado ni una validación de su XML. Registro explícito: crear o recibir una compra no genera deuda automáticamente. Compras antiguas no crean saldos por la migración.

Administración general, administración de sucursal y contabilidad pueden registrar cuentas y abonos (permiso payable_write). Consulta requiere reportes. La API valida empresa y sucursal en cada acción. La referencia de factura se normaliza a mayúsculas y debe ser única por proveedor/empresa; una compra sólo tiene una cuenta. Reintento con misma referencia/vencimiento devuelve el registro original; otros datos generan conflicto.

Abonos: importe positivo de hasta dos decimales, método tarjeta o transferencia manual, referencia del pago externo. No se envía dinero, no se consulta al banco y no se modifica caja. No permite efectivo en esta versión para evitar retiros sin conciliación. Se conserva actor/fecha y evento de auditoría. La clave idempotente impide duplicar reintentos con los mismos datos; claves distintas representan operaciones diferentes, por lo que el operador debe verificar comprobantes.

Saldo = importe reconocido - abonos registrados. El servidor bloquea cuenta y sucursal para impedir que dos abonos simultáneos excedan saldo. Estado pagada, pendiente o vencida (fecha México; vence al terminar la fecha capturada). No hay edición ni borrado. Los abonos pueden revertirse con motivo y responsable; se conserva el original y se recalcula saldo. No registrar un abono negativo. Historial y paginación de cuentas disponibles en Proveedores y compras.

Límites: una factura por compra recibida completa, importe exacto del total de orden. Facturación parcial, varias facturas por orden, descuentos del proveedor, anticipos, retenciones y conciliación bancaria quedan pendientes. Devoluciones físicas con crédito aceptado y reversos de abonos implementados; ver REVERSOS_Y_DEVOLUCIONES_PROVEEDOR.md. Sin agregados globales de página parcial.

Migración 5e289b3056a7 crea tablas vacías de cuentas/abonos y conserva operaciones existentes. Ejecutar scripts/migrate_local.py con servidor detenido. El lanzador migra bases reconocidas con respaldo.

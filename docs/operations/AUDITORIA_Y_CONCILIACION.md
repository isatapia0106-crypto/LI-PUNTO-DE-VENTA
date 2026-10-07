# Auditoría y conciliación

Módulo «Auditoría y pagos», disponible para usuarios con permiso de reportes. Toda consulta valida empresa y sucursal en la API. No permite editar ni eliminar eventos.

Auditoría: rango de fechas de México (hasta 366 días), ID de usuario y código exacto de operación opcionales. Muestra usuario, fecha, acción, registro y evento. Páginas de 100 eventos con cursor exclusivo. La bitácora registra acciones del sistema; falta revisión de cobertura de eventos de seguridad y conservación externa.

Conciliación: selecciona Mercado Pago y el periodo de creación de los cobros. Compara valor actual de tickets menos devoluciones confirmadas con pagos aprobados/reembolsados menos reembolsos observados. Detecta diferencias, pagos principales faltantes, contracargos, importes inconsistentes y devoluciones pendientes. «Coincide» sólo expresa igualdad con las observaciones guardadas; no representa saldo bancario ni una verificación nueva del proveedor. Cada fila muestra cuándo fue verificada por última vez. Consulta o reconcilia el cobro desde Productos y ventas para actualizar observaciones.

El periodo agrupa cobros por creación, no ingresos bancarios ni ventas por día; un ticket o devolución posterior afecta sus valores acumulados. Páginas de 100 cobros, sin totales globales que puedan confundirse con una página parcial. No llama al proveedor ni altera dinero, existencias, incidentes o cortes.

Pendiente para conciliación externa completa: reportes de liquidación, comisiones, fechas de abono, retenciones y comparación con movimientos bancarios. Validación real de cuenta Mercado Pago pendiente.

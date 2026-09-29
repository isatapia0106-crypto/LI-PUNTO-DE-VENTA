# Requerimientos · LI Punto de Venta

**Versión:** 0.1 · **Estado:** base para revisión operativa · **Fecha:** 28 de septiembre de 2026

Este documento define el alcance del sistema LI. Los estados describen lo que existe en el repositorio, no una aprobación para usarlo en ventas reales. La arquitectura toma como referencia los módulos conocidos de TPN; no replica su código privado.

## 1. Alcance y reglas generales

- Operación prevista en seis sucursales: Zamora, Zacapu, Uruapan, 20 de Noviembre, Maravatío y CDMX.
- Cada sucursal pertenece a una empresa y se asocia a una razón social para facturación. **La asignación de las dos razones sociales sigue pendiente de confirmación.** No emitir CFDI hasta definir RFC, régimen, serie, CSD y PAC de cada emisor.
- Toda venta, movimiento de inventario, caja y consulta debe conservar empresa, sucursal, usuario y fecha. Un usuario no puede operar otra empresa ni sucursal no asignada.
- Precios, impuestos, descuentos, folios, crédito y métodos de pago se configurarán mediante reglas por empresa/sucursal. El IVA fijo de 16 % que hoy calcula la demo no representa todos los casos fiscales.
- Las operaciones que cambian dinero o existencias deben ser atómicas y resistentes a reintentos.

## 2. Funciones y criterios de aceptación

| ID | Prioridad | Requerimiento y criterio verificable | Estado actual |
| --- | --- | --- | --- |
| SUC-01 | P0 | Registrar empresas, razones sociales y sucursales; impedir acceso cruzado y asignar usuarios a sucursales. | Parcial: seis sucursales demo, empresa y permisos; faltan razones sociales y administración. |
| SEG-01 | P0 | Iniciar sesión con contraseña protegida, roles y permisos en la API; bloquear cuentas inactivas y registrar actor. | Parcial: JWT, Argon2 y roles; faltan revocación, límites de intentos y revisión de seguridad. |
| CAT-01 | P0 | Crear y consultar productos por SKU, con precio y existencia por sucursal; definir unidad, código de barras, impuestos y vigencia. | Parcial: SKU, nombre, precio y stock; faltan atributos, precios e impuestos configurables. |
| INV-01 | P0 | Registrar entradas, salidas, ajustes y traspasos con motivo, usuario y referencia; no permitir existencias negativas; consultar kardex. | Parcial: alta, ajuste, venta y traspaso atómico; faltan compras, conteos y conciliación. |
| VEN-01 | P0 | Capturar carrito, calcular importes por línea, impuestos y total, cobrar y descontar stock una sola vez; rechazar stock y pago insuficientes. | Parcial: flujo demo con efectivo, tarjeta y transferencia manual; faltan reglas fiscales y pagos integrados. |
| VEN-02 | P0 | Asignar folio/serie únicos por emisor y sucursal, conservar detalle histórico y permitir reimpresión de ticket sin alterar la venta. | Parcial: ID y ticket imprimible; faltan folio y serie de negocio. |
| CAJ-01 | P0 | Abrir turno por caja/cajero, registrar fondo, ventas, entradas/retiros autorizados y cerrar con importe esperado, contado y diferencia. | Parcial: una caja por sucursal, apertura, retiro y cierre; faltan múltiples cajas, cajero y autorización. |
| AUD-01 | P0 | Registrar acciones críticas con usuario, empresa, sucursal, fecha, entidad e identificador; permitir consulta autorizada. | Parcial: bitácora básica; faltan consulta y cobertura completa. |
| CLI-01 | P1 | Crear clientes, identificar datos de contacto y fiscales, consultar historial y vincular ventas. | Parcial: alta, búsqueda, edición, historial por sucursal y vínculo con venta; faltan datos fiscales y consentimiento. |
| CRE-01 | P1 | Si se aprueba venta a crédito: límite, plazo, saldo, abonos, vencimientos y bloqueo por excedente; conciliar con caja. | Pendiente de decisión de negocio. |
| COM-01 | P1 | Registrar proveedores, órdenes, recepción parcial, costos y actualización de inventario con trazabilidad. | Pendiente. |
| DEV-01 | P1 | Devolver o cancelar mediante autorización, referencia a venta original, ajuste de stock y dinero; si aplica, nota de crédito fiscal. | Pendiente. |
| REP-01 | P1 | Mostrar ventas, utilidad estimada, inventario, cortes, retiros y diferencias por fecha, sucursal, empresa y forma de pago; exportar. | Parcial: resumen básico por sucursal y método. |
| FIS-01 | P1 | Emitir CFDI 4.0 con PAC elegido, estados de timbrado, reintentos, cancelación y conciliación con venta; resguardar CSD. | Pendiente; depende de datos fiscales y PAC. |
| PAG-01 | P1 | Integrar terminal Clip con referencia de venta, confirmación verificable, reversos y conciliación; nunca considerar pagado un cobro no confirmado. | Pendiente; tarjeta actual es registro manual. |
| MSG-01 | P2 | Ofrecer enlace de WhatsApp al finalizar la venta para compartir el comprobante, con confirmación manual del operador. | Parcial: texto compartible manualmente; falta flujo de cliente y consentimiento. |
| OFF-01 | P2 | Si se autoriza operación sin conexión: cola local persistente, identificadores únicos, sincronización, conflictos y límites de caja/stock. | Pendiente; no operar offline con la demo. |
| HW-01 | P2 | Verificar impresora térmica, lector de código, cajón, terminal y equipo por sucursal; registrar modelos y pruebas. | Pendiente. |
| OPS-01 | P0 | Disponer de migraciones, respaldo/restauración probado, monitoreo, HTTPS y procedimiento de recuperación antes del piloto real. | Parcial: migraciones Alembic; faltan pruebas operativas completas. |

**P0:** necesario antes de un piloto controlado. **P1:** siguiente etapa funcional. **P2:** condicionado a la operación y las integraciones seleccionadas.

## 3. Roles mínimos

| Rol | Operación prevista |
| --- | --- |
| Administrador general | Configura empresas, sucursales, usuarios y reglas; consulta todas las sucursales de su empresa. |
| Administrador de sucursal | Supervisa ventas, caja, inventario y reportes de sus sucursales asignadas. |
| Vendedor/Cajero | Vende y opera su caja/turno; no autoriza retiros ni cambia inventario. |
| Almacenista | Registra movimientos y traspasos de las sucursales asignadas, sujetos a aprobación si se define. |
| Supervisor de inventarios | Realiza conteos, ajustes autorizados y revisión de kardex. |
| Contabilidad | Consulta cortes, conciliación y comprobantes fiscales; no modifica ventas. |
| Repartidor | Solo consulta las entregas que se le asignen cuando exista ese módulo. |
| Auditoría/Consulta | Acceso de lectura a bitácora y reportes autorizados. |

Los permisos actuales de la API son una primera versión; esta matriz define el comportamiento esperado al completar cada módulo.

## 4. Flujos para aceptar el piloto

1. **Venta:** usuario autorizado abre su caja → selecciona sucursal y productos → se valida stock/precio/impuesto → registra pago → la transacción crea venta, descuento y bitácora → se obtiene folio y ticket. Repetir la misma solicitud no duplica cobro ni existencias.
2. **Traspaso:** usuario autorizado en origen y destino selecciona producto/cantidad → se verifica stock → una transacción registra salida y entrada con la misma referencia → el reintento no duplica el movimiento.
3. **Corte:** cajero cuenta efectivo → el sistema calcula fondo + cobros en efectivo + entradas − retiros/devoluciones en efectivo → guarda diferencia y responsables. Una caja cerrada no acepta ventas nuevas.
4. **Factura:** venta confirmada → se valida razón social y datos fiscales → PAC timbra → se conserva UUID/estado y XML/PDF → fallos quedan pendientes de reintento sin crear una segunda venta.

## 5. Decisiones pendientes con responsables de negocio

1. ¿Qué sucursales pertenecen a cada una de las dos razones sociales y qué RFC/serie fiscal tendrá cada una?
2. ¿Se venderá a crédito desde el primer piloto? En caso afirmativo: límites, plazo, autorización y política de cobranza.
3. ¿Qué PAC se contratará y qué modelos Clip/hardware existen en cada sucursal?
4. ¿Cuántas cajas simultáneas habrá por sucursal y quién puede aprobar retiros, descuentos, cancelaciones y ajustes?
5. ¿Cuáles productos requieren tasa 0 %, exención u otra regla fiscal? ¿Los precios capturados incluyen impuestos?
6. ¿Se requiere operación offline en el piloto o solo después de estabilizar la operación conectada?

## 6. Condición de salida

El piloto debe probar los flujos anteriores con datos de cada sucursal, permisos por rol, respaldo restaurado y conciliación de caja/inventario. CFDI y pagos externos se activan únicamente después de validar sus integraciones y credenciales. El estado de demo actual no cumple todavía esta condición.

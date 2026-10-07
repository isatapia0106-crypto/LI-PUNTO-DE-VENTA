"""Local assistant: fixed read-only tools, using the application's authorization."""
import re
import unicodedata
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field, ConfigDict

class AssistantIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    branch_id: int = Field(gt=0)
    message: str = Field(min_length=2, max_length=600)


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.lower()) if unicodedata.category(c) != 'Mn')


def answer(data, user):
    # Import lazily so routes and models finish initializing before tool execution.
    from . import main as pos
    from sqlalchemy.orm import Session
    with Session(pos.engine) as db:
        branch = pos.branch_for(db, user, data.branch_id)
        branch_name = branch.name
    text = normalized(data.message)
    words = set(re.findall(r'\w+', text))
    result = {'branch_id': data.branch_id, 'branch_name': branch_name,
              'mode': 'local', 'generated_at': datetime.now(ZoneInfo('America/Mexico_City')).isoformat(),
              'source': None, 'items': [], 'truncated': False}
    def reply(message, source=None, items=None, truncated=False):
        return {**result, 'answer': message, 'source': source, 'items': items or [], 'truncated': truncated}
    if words & {'borra', 'elimina', 'ejecuta', 'sql', 'password', 'contrasena', 'token', 'secreto'}:
        return reply('No ejecuto instrucciones del sistema ni consulto credenciales. Puedo consultar ventas, inventario y turnos de la sucursal seleccionada.')
    if words & {'como', 'ayuda', 'instrucciones', 'pasos'}:
        if words & {'devolucion', 'devoluciones', 'devolver', 'reembolso'}:
            pos.require(user, 'sale_return')
            return reply('En Productos y ventas abre el ticket y pulsa Devolver. Selecciona cantidades, motivo y si la mercancía puede reintegrarse. Mercado Pago debe confirmar el reembolso antes de actualizar inventario. Si queda pendiente, consulta el historial y reintenta desde la misma devolución.')
        if words & {'corte', 'cerrar', 'cierre'}:
            pos.require_any(user, 'cash_close', 'report')
            return reply('En Cajas y turnos selecciona tu turno, captura el efectivo contado y revisa la diferencia. Confirma el cierre desde ese módulo. El corte cerrado conserva sus importes históricos.')
        return reply('Puedes preguntar: «ventas de hoy», «ventas del 2026-10-01 al 2026-10-06», «productos bajo mínimo», «buscar producto café», «turnos de caja» o «cómo devolver un ticket». Las consultas respetan tus permisos. No realizo cobros ni modifico inventario.')
    if words & {'cobra', 'cobrar', 'cancela', 'cancelar', 'reembolsa', 'ajusta', 'traspasa', 'registra', 'crea', 'modifica', 'cierra'}:
        return reply('Este asistente sólo consulta datos. Realiza esa operación en su módulo, donde se validan permisos y confirmaciones.')
    if words & {'venta', 'ventas', 'vendido', 'utilidad', 'ingresos'}:
        pos.require(user, 'report')
        today = datetime.now(ZoneInfo('America/Mexico_City')).date()
        dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', text)
        if len(dates) > 2:
            raise pos.HTTPException(422, 'Indica una fecha o un intervalo de dos fechas.')
        try:
            start = date.fromisoformat(dates[0]) if dates else today - timedelta(days=1 if 'ayer' in words else 0)
            end = date.fromisoformat(dates[-1]) if dates else start
        except ValueError:
            raise pos.HTTPException(422, 'Fecha inválida. Usa AAAA-MM-DD.')
        if not dates and words & {'semana', 'mes', 'historico', 'ano'}:
            return reply('Para ese periodo indica las fechas exactas: ventas del AAAA-MM-DD al AAAA-MM-DD.')
        report = pos.sales_report(data.branch_id, start, end, user=user)
        rows = [{'label': 'Tickets de venta', 'value': str(report['sales_count'])},
                {'label': 'Venta bruta MXN', 'value': report['gross']},
                {'label': 'Reembolsos confirmados MXN', 'value': report['refunds']},
                {'label': 'Ventas después de reembolsos MXN', 'value': report['total']},
                {'label': 'Utilidad calculada MXN', 'value': report['profit']}]
        warning = ' Hay partidas sin costo; revisa la utilidad.' if report['missing_cost_lines'] else ''
        return reply(f'Resumen del {start} al {end}, fechas de México. Los reembolsos corresponden a su fecha de confirmación.' + warning, '/api/reports/sales', rows)
    if words & {'minimo', 'minimos', 'alertas', 'reponer', 'agotados'}:
        rows = pos.stock_alerts(data.branch_id, user=user)
        return reply(f'{len(rows)} productos alcanzaron su mínimo configurado o están debajo de él. Los productos sin mínimo configurado no aparecen en esta consulta.', '/api/stock/alerts',
                     [{'label': f"{r['name']} · {r['sku']}", 'value': f"Existencias: {r['stock']}; mínimo: {r['minimum']}"} for r in rows[:20]], len(rows)>20)
    if words & {'caja', 'cajas', 'turno', 'turnos', 'efectivo'}:
        rows = pos.cash_sessions(data.branch_id, user=user)
        opened = [r for r in rows if r['status'] == 'open']
        return reply('Turnos abiertos dentro de tu acceso. El efectivo esperado debe compararse con un conteo físico. La consulta revisa los últimos 100 turnos.', '/api/cash/sessions',
                     [{'label': f"Turno {r['id']}", 'value': f"Efectivo esperado MXN: {r['expected']}"} for r in opened[:20]], len(opened)>20)
    match = re.fullmatch(r'(?:buscar|busca|consultar)\s+(?:producto\s+)?(.+)', text)
    if match:
        rows = pos.products(data.branch_id, user=user)
        query = match.group(1)
        rows = [r for r in rows if r['active'] and query in normalized(r['name']+' '+r['sku']+' '+(r['barcode'] or ''))]
        return reply(f'{len(rows)} productos coinciden. Existencias físicas; la disponibilidad para vender se valida al cobrar. El precio sigue la configuración de impuestos del producto.', '/api/products',
                     [{'label': f"{r['name']} · {r['sku']}", 'value': f"Existencias: {r['stock']}; precio MXN: {r['price']}"} for r in rows[:20]], len(rows)>20)
    return reply('No pude identificar una consulta compatible. Prueba «ayuda», «ventas de hoy», «productos bajo mínimo», «buscar producto nombre» o «turnos de caja».')

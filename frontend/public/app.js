const $ = id => document.getElementById(id);
const pesos = value => new Intl.NumberFormat('es-MX', {style:'currency', currency:'MXN'}).format(value);
const fecha = value => new Date(value).toLocaleString('es-MX');
let token=null, me=null, permissions=new Set(), branches=[], products=[], catalog=[], customersList=[];
let cart=new Map(), purchaseDraft=new Map(), sessions=[], cash={open:false}, myCash={open:false};
let editingProduct=null, countingProduct=null, quote=null, quoteVersion=0, busy=false, receiptText='';
const retryKeys=new Map();
let stockFilter='all';
const branchId=()=>Number($('branch').value);
const can=permission=>permissions.has(permission);
let toastTimer;
const notice=message=>{
 $('notice').textContent=message;$('actionToast').textContent=message;$('actionToast').hidden=!message;
 clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('actionToast').hidden=true,4500);
};
const run=fn=>async event=>{try{await fn(event);}catch(error){notice(error.message);}};
function node(tag, text, className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function button(text, action){const b=node('button',text);b.type='button';b.onclick=run(action);return b;}
function options(id, rows, label, selected){const prev=selected??$(id).value;$(id).replaceChildren(...rows.map(r=>{const o=node('option',label(r));o.value=r.id;return o;}));if(rows.some(r=>String(r.id)===String(prev)))$(id).value=String(prev);}
let pendingRequests=0;
async function request(url, opts={}){
 pendingRequests++;$('networkStatus').textContent='Actualizando…';$('networkStatus').classList.add('loading');
 try{
  const response=await fetch(url,{...opts,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{ }),...opts.headers}});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map(d=>`${d.loc.at(-1)}: ${d.msg}`).join('; '):'Error de conexión');
  return data;
 }finally{pendingRequests--;if(!pendingRequests){$('networkStatus').textContent='';$('networkStatus').classList.remove('loading');}}
}
async function post(url, data, withKey=false){
  const fingerprint=JSON.stringify([url,Object.fromEntries(Object.entries(data).filter(([key])=>key!=='approval'))]);
  if(withKey&&!retryKeys.has(fingerprint))retryKeys.set(fingerprint,crypto.randomUUID());
  const result=await request(url,{method:'POST',headers:withKey?{'Idempotency-Key':retryKeys.get(fingerprint)}:{},body:JSON.stringify(data)});
  if(withKey)retryKeys.delete(fingerprint);
  return result;
}
function panel(name){
 $('mobileCart').hidden=name!=='sales'||!can('sale')||!token;
 for(const p of ['sales','cash','purchases','inventory','reports','users'])$(p+'Panel').hidden=p!==name;
 for(const [id,p] of [['navSales','sales'],['navCash','cash'],['navPurchases','purchases'],['navInventory','inventory'],['navReports','reports'],['navUsers','users']]){
  $(id).classList.toggle('is-active',p===name);
  if(p===name)$(id).setAttribute('aria-current','page');else $(id).removeAttribute('aria-current');
 }
}
for(const [id,p] of [['navSales','sales'],['navCash','cash'],['navPurchases','purchases'],['navInventory','inventory'],['navReports','reports'],['navUsers','users']])$(id).onclick=()=>panel(p);
async function loadCustomers(selected=''){
  customersList=await request(`/api/customers?branch_id=${branchId()}&q=${encodeURIComponent($('customerSearch').value.trim())}`);
  options('customer',[{id:'',name:'Público general'},...customersList],c=>c.name+(c.phone?` · ${c.phone}`:''),selected);
  $('editCustomer').disabled=!$('customer').value;$('customerHistoryButton').disabled=!$('customer').value;
}
function salePayload(){return {branch_id:branchId(),cash_session_id:myCash.id??null,customer_id:Number($('customer').value)||null,
  discount_percent:$('discountPercent').value||'0',discount_reason:$('discountReason').value.trim()||null,
  items:[...cart].map(([product_id,quantity])=>({product_id,quantity})),payment_method:$('method').value,paid:$('paid').value||'0'};}

function metric(label,value){
 const card=node('div',undefined,'metric-card');card.append(node('span',label),node('strong',value));return card;
}
function paymentState(total,paid,method){
 const due=Math.round(Number(total)*100),received=Math.round(Number(paid)*100);
 if(!Number.isFinite(due)||!Number.isFinite(received)||received<0)return {valid:false,text:'Captura un importe válido.'};
 if(received<due)return {valid:false,text:'Faltan '+pesos((due-received)/100)+' para cubrir la venta.'};
 return {valid:true,text:method==='cash'?'Cambio: '+pesos((received-due)/100):'Registro manual de pago: '+pesos(received/100)+'. No confirma un cobro externo.'};
}
function updatePayment(){
 $('exactPayment').disabled=!quote||busy;
 if(!quote){$('paymentFeedback').textContent=cart.size?'Calculando total…':'Agrega productos para calcular el pago.';$('charge').disabled=true;return;}
 const state=paymentState(quote.total,$('paid').value||0,$('method').value);
 $('paymentFeedback').textContent=state.text;
 $('paymentFeedback').classList.toggle('needs-attention',!state.valid);
 $('charge').disabled=!state.valid||!myCash.open||busy;
}
function updateCashDifference(){
 const input=$('counted').value;
 if(!cash.open||input===''){$('cashDifference').textContent='Captura el efectivo contado para revisar la diferencia.';return;}
 const diff=Math.round(Number(input)*100)-Math.round(Number(cash.expected)*100);
 $('cashDifference').textContent=diff===0?'El efectivo coincide con el esperado.':(diff<0?'Faltante: ':'Sobrante: ')+pesos(Math.abs(diff)/100);
}
$('counted').addEventListener('input',updateCashDifference);
$('exactPayment').onclick=async()=>{if(!quote||busy)return;$('paid').value=Number(quote.total).toFixed(2);await drawCart();};

async function drawCart(){
  const version=++quoteVersion;quote=null;$('charge').disabled=true;updatePayment();
 const units=[...cart.values()].reduce((a,b)=>a+b,0);
 $('cartCount').textContent=units+' unidades';$('mobileCart').textContent='Ver venta · '+units+' unidades';
 $('clearCart').disabled=!units||busy;
  $('cart').replaceChildren(...[...cart].map(([id,qty])=>{const p=products.find(x=>x.id===id);const row=node('div',undefined,'cartline');
    row.append(node('span',`${p?.name??'Producto'} × ${qty}`),button('−',()=>{qty===1?cart.delete(id):cart.set(id,qty-1);return drawCart();}),button('+',()=>{if(qty>=p.stock)return notice('No hay más existencias');cart.set(id,qty+1);return drawCart();}));return row;}));
  for(const id of ['subtotal','tax','total','discountTotal'])$(id).textContent=pesos(0);
  if(!cart.size||!can('sale'))return;
  try{const result=await post('/api/sales/quote',salePayload());if(version!==quoteVersion)return;quote=result;
    $('subtotal').textContent=pesos(result.subtotal);$('tax').textContent=pesos(result.tax);$('total').textContent=pesos(result.total);$('discountTotal').textContent=pesos(result.discount_total);
    updatePayment();
    $('mobileCart').textContent='Ver venta · '+units+' unidades · '+pesos(result.total);
  }catch(error){if(version===quoteVersion)notice(error.message);}
}
function addToCart(p){if(!p.active||!can('sale'))return;if((cart.get(p.id)||0)>=p.stock)return notice('No hay más existencias');cart.set(p.id,(cart.get(p.id)||0)+1);return drawCart();}
function filterProducts(rows,q,filter,sort){
 return rows.filter(p=>[p.name,p.sku,p.barcode??''].some(v=>v.toLowerCase().includes(q))&&(filter==='all'||(filter==='available'?p.active&&p.stock>0:p.active&&p.stock<=0)))
 .sort((a,b)=>sort==='priceAsc'?Number(a.price)-Number(b.price):sort==='priceDesc'?Number(b.price)-Number(a.price):a.name.localeCompare(b.name,'es'));
}
function drawProducts(){const q=$('search').value.trim().toLowerCase();
  const visible=filterProducts(products,q,stockFilter,$('productSort').value);
  $('productResults').textContent=visible.length+' de '+products.length+' productos';
  $('products').replaceChildren(...visible.map(p=>{
    const card=node('article',undefined,'card');const buy=button(p.name,()=>addToCart(p));buy.disabled=!can('sale')||!p.active||p.stock<=0;
    card.append(buy,node('em',pesos(p.price)),node('small',`${p.sku} · ${p.unit} · Stock ${p.stock}${p.active?'':' · Inactivo'}`),node('small',p.tax_exempt?'Exento':`Impuesto ${Number(p.tax_rate)*100}% · Precio ${p.price_includes_tax?'con':'sin'} impuestos`));
    card.append(node('span',!p.active?'Inactivo':p.stock>0?'Disponible':'Sin existencias',p.active&&p.stock>0?'stock-badge available':'stock-badge'));
    if(can('catalog_write'))card.append(button('Editar',()=>openProduct(p)));return card;
  }));
  if(!visible.length)$('products').append(node('p','No hay productos con estos filtros. Prueba otra búsqueda.','catalog-empty'));
}
function drawInventory(){
 $('stockAlerts').replaceChildren(...products.filter(p=>p.low_stock).map(p=>node('div',`${p.stock===0?'AGOTADO':'BAJO MÍNIMO'} · ${p.sku} · ${p.name} · Existencia ${p.stock} · Mínimo ${p.minimum}`,'sale stock-alert')));
 const stocked=products.filter(p=>p.stock>0);
 $('inventoryMetrics').replaceChildren(metric('Productos en sucursal',String(products.length)),metric('Activos sin existencias',String(products.filter(p=>p.active&&p.stock<=0).length)),metric('Con existencias sin costo',String(stocked.filter(p=>Number(p.average_cost)<=0).length)),metric('Valor a costo registrado',pesos(stocked.reduce((sum,p)=>sum+p.stock*Number(p.average_cost||0),0))));

  $('inventory').replaceChildren(...products.map(p=>{const row=node('div',undefined,'sale');row.append(node('span',`${p.sku} · ${p.name} · ${p.stock} ${p.unit} · Costo promedio ${pesos(p.average_cost)}`));
    if(can('stock_write'))row.append(button('Mínimo',()=>openMinimum(p)));
    if(can('count_write'))row.append(button('Contar',()=>{countingProduct={...p};$('countProduct').textContent=`${p.name}: sistema ${p.stock} ${p.unit}`;$('countQty').value=p.stock;$('countReason').value='';$('countDialog').showModal();}));return row;}));
  options('transferProduct',products.filter(p=>p.stock>0),p=>`${p.name} (${p.stock})`);options('transferTarget',branches.filter(b=>b.id!==branchId()),b=>b.name);
  $('transferPanel').hidden=!can('stock_write')||branches.length<2;
}
async function refreshCash(){
  options('register',await request(`/api/cash/registers?branch_id=${branchId()}`),r=>r.name);
  sessions=await request(`/api/cash/sessions?branch_id=${branchId()}`);
  myCash=sessions.find(s=>s.open&&s.cashier_id===me.id)||{open:false};
  cash=sessions.find(s=>s.open&&s.register_id===Number($('register').value))||{open:false};
  const own=cash.cashier_id===me.id;const manager=can('cash_deposit');
 $('cashMetrics').replaceChildren(...(cash.open?[metric('Fondo inicial',pesos(cash.opening)),metric('Entradas',pesos(cash.deposited)),metric('Retiros',pesos(cash.withdrawn)),metric('Efectivo esperado',pesos(cash.expected))]:[metric('Turnos abiertos (consulta)',String(sessions.filter(s=>s.open).length))]));
 updateCashDifference();
  $('cashStatus').textContent=cash.open?`${cash.register_name} · Turno #${cash.id} · ${cash.cashier_name} · Esperado ${pesos(cash.expected)}`:'Caja sin turno abierto';
  $('checkoutCash').textContent=myCash.open?`${myCash.register_name} · Turno #${myCash.id}`:'Abre tu turno en Cajas y turnos para vender';
  $('openControls').hidden=cash.open||!can('cash_open');$('closeControls').hidden=!cash.open||!can('cash_close')||(!own&&!manager);
  $('cashMovementForm').hidden=!cash.open||!manager;$('newRegister').hidden=!manager;
  const moves=cash.open&&(own||manager)?await request(`/api/cash/${cash.id}/movements`):[];
  $('cashMovements').replaceChildren(...moves.map(m=>{const row=node('div',undefined,'sale');row.append(node('span',`#${m.id} · ${m.kind==='deposit'?'Entrada':m.kind==='refund'?'Reembolso':'Retiro'} · ${pesos(m.amount)} · ${m.reason}`),button('Comprobante',()=>showText(`LI PUNTO DE VENTA\n${branches.find(b=>b.id===branchId()).name}\n${cash.register_name} · Turno #${m.session_id}\nMovimiento #${m.id}\n${fecha(m.created_at)}\n${m.kind==='deposit'?'Entrada':m.kind==='refund'?'Reembolso':'Retiro'}: ${pesos(m.amount)}\nMotivo: ${m.reason}\nAutorizado por usuario #${m.actor_id}`)));return row;}));
  $('cashSessions').replaceChildren(...sessions.map(s=>{const row=node('div',undefined,'sale');row.append(node('span',`${s.register_name} · Turno #${s.id} · ${s.cashier_name} · ${s.open?'Abierto':'Cerrado'} · Esperado ${pesos(s.expected)}${s.counted===null?'':` · Diferencia ${pesos(Number(s.counted)-Number(s.expected))}`}`),button('Ver corte',()=>showCashCut(s.id)));return row;}));
}
function showText(text){receiptText=text;$('receiptContent').textContent=text;$('receiptDialog').showModal();}
async function showReceipt(id){const s=await request(`/api/sales/${id}`);showText(['LI PUNTO DE VENTA',s.branch_name,`Ticket ${s.folio??s.id}`,`Turno #${s.cash_session_id}`,fecha(s.created_at),s.customer_name??'Público general','',
 ...s.items.map(i=>`${i.quantity} ${i.unit} · ${i.name}\n  Base ${pesos(i.line_total)}${i.tax!==null?` · Impuesto ${pesos(i.tax)}`:''}`),'',`Descuento aplicado: ${pesos(s.discount_total)}`,`Subtotal después del descuento: ${pesos(s.subtotal)}`,`Impuestos: ${pesos(s.tax)}`,`Total: ${pesos(s.total)}`,`Pago: ${{cash:'Efectivo',card:'Tarjeta',transfer:'Transferencia',mercado_pago:'Mercado Pago'}[s.payment_method]}`,`Recibido: ${pesos(s.paid)}`,`Cambio: ${pesos(s.change)}`,'','Comprobante de venta. No es factura CFDI.'].join('\n'));}
function drawPurchaseDraft(){ $('purchaseDraft').replaceChildren(...[...purchaseDraft].map(([id,x])=>{const row=node('div',undefined,'sale');row.append(node('span',`${catalog.find(p=>p.id===id)?.name} · ${x.quantity} × ${pesos(x.unit_cost)}`),button('Quitar',()=>{purchaseDraft.delete(id);drawPurchaseDraft();}));return row;})); }
async function refreshPurchases(){
  const suppliers=await request(`/api/suppliers?branch_id=${branchId()}`);options('supplier',suppliers,s=>s.name);
  $('suppliers').replaceChildren(...suppliers.map(s=>{const row=node('div',undefined,'sale');row.append(node('span',`${s.name} · ${s.phone??''} · ${s.reference??''}`));if(can('purchase_write'))row.append(button('Editar',()=>openEntity('supplier',s)));return row;}));
  catalog=await request(`/api/products?branch_id=${branchId()}&include_unstocked=true`);options('purchaseProduct',catalog.filter(p=>p.active),p=>`${p.sku} · ${p.name}`);
  const purchases=await request(`/api/purchases?branch_id=${branchId()}`);$('purchases').replaceChildren(...purchases.map(p=>{
    const card=node('section',undefined,'purchase');card.append(node('h3',`Orden #${p.id} · ${p.reference} · ${p.supplier_name}`),node('p',`${{ordered:'Pendiente',partial:'Recepción parcial',received:'Recibida'}[p.status]} · Costo ${pesos(p.total_cost)} sin impuestos`));
    const form=node('form');const inputs=[];
    for(const x of p.items){const label=node('label',`${x.name} · Pedido ${x.quantity} · Recibido ${x.received} · Pendiente ${x.pending}`);
      if(x.pending&&(can('purchase_write')||can('purchase_receive'))){const input=node('input');input.type='number';input.min=0;input.max=x.pending;input.step=1;input.value=0;label.append(input);inputs.push([x.product_id,input]);}form.append(label);}
    if(inputs.length){const submit=node('button','Recibir cantidades capturadas');form.append(submit);form.onsubmit=run(async e=>{e.preventDefault();submit.disabled=true;try{const items=inputs.map(([product_id,input])=>({product_id,quantity:Number(input.value)})).filter(x=>x.quantity>0);if(!items.length)throw Error('Captura una cantidad a recibir');await post(`/api/purchases/${p.id}/receive`,{items},true);notice('Recepción registrada; inventario actualizado');await refresh();}finally{submit.disabled=false;}});}
    card.append(form);card.append(button('Ver recepciones',async()=>{const rows=await request(`/api/purchases/${p.id}/receipts`);showText(['LI PUNTO DE VENTA',`Recepciones de orden #${p.id} · ${p.reference}`, ...rows.map(r=>`Recepción #${r.id} · ${fecha(r.created_at)} · Usuario #${r.actor_id}\n`+r.items.map(i=>`${p.items.find(x=>x.product_id===i.product_id)?.name??i.product_id}: ${i.quantity}`).join('\n'))].join('\n'));}));return card;
  }));
}
async function refresh(){if(!branchId())return;
  products=await request(`/api/products?branch_id=${branchId()}`);drawProducts();drawInventory();
  const jobs=[];
  invalidateReport();
  if(can('report'))jobs.push(loadReportCashiers());
  if(can('users_write'))jobs.push(loadUsers());
  if(can('cash_open')||can('report'))jobs.push(refreshCash());
  if(can('sale'))jobs.push(loadIntegratedPayments());
  if(can('sale')||can('report'))jobs.push((async()=>{const sales=await request(`/api/sales?branch_id=${branchId()}`);$('sales').replaceChildren(...sales.map(s=>{const row=node('div',undefined,'sale');row.append(node('span',`${s.folio??'#'+s.id} · ${fecha(s.created_at)}${s.status==='cancelled'?' · CANCELADA':''}`),node('b',pesos(s.total)),button('Ticket',()=>showReceipt(s.id)),button('Devoluciones',()=>openReturn(s.id)),...(can('sale_cancel')&&s.status!=='cancelled'?[button('Cancelar venta',()=>openReturn(s.id,true))]:[]));return row;}));})());
  if(can('report'))jobs.push((async()=>{const s=await request(`/api/reports/summary?branch_id=${branchId()}`);$('summary').textContent=`${s.sales_count} ventas · ${pesos(s.total)} neto de devoluciones · Efectivo ${pesos(s.by_method.cash)}`;})());else $('summary').textContent='Disponible para supervisión';
  if(can('purchase_read')||can('purchase_write'))jobs.push(refreshPurchases());
  if(can('stock_write'))jobs.push((async()=>{const rows=await request(`/api/stock/movements?branch_id=${branchId()}`);$('movements').replaceChildren(...rows.map(m=>node('div',`Producto #${m.product_id} · ${m.change>0?'+':''}${m.change} · ${m.reason} · Referencia ${m.reference_id??'—'} · Usuario #${m.actor_id??'—'} · ${fecha(m.created_at)}`,'sale')));})());
  if(can('stock_write')||can('report'))jobs.push((async()=>{const rows=await request(`/api/stock/counts?branch_id=${branchId()}`);$('counts').replaceChildren(...rows.map(c=>node('div',`Conteo #${c.id} · Producto #${c.product_id} · Sistema ${c.expected} · Contado ${c.counted} · Diferencia ${c.difference} · ${c.reason}`,'sale')));})());
  const results=await Promise.allSettled(jobs);for(const r of results)if(r.status==='rejected')notice(r.reason.message);
  await drawCart();
}
function openProduct(p=null){editingProduct=p;$('form').reset();$('productTitle').textContent=p?'Editar producto (catálogo de la empresa)':'Nuevo producto';$('initialStock').hidden=!!p;$('productError').textContent='';
 if(p){for(const name of ['sku','barcode','name','unit','price'])$('form').elements[name].value=p[name]??'';$('form').elements.taxRate.value=Number(p.tax_rate)*100;
 $('form').elements.taxExempt.checked=p.tax_exempt;$('form').elements.priceIncludesTax.checked=p.price_includes_tax;$('form').elements.active.checked=p.active;}
 $('dialog').showModal();}
$('new').onclick=()=>openProduct();$('cancelProduct').onclick=()=>$('dialog').close();
$('form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const data={branch_id:branchId(),sku:f.get('sku'),barcode:f.get('barcode')||null,name:f.get('name'),unit:f.get('unit'),price:f.get('price'),tax_rate:(Number(f.get('taxRate'))/100).toFixed(4),tax_exempt:f.has('taxExempt'),price_includes_tax:f.has('priceIncludesTax'),active:f.has('active')};
 try{if(editingProduct)await request(`/api/products/${editingProduct.id}`,{method:'PUT',body:JSON.stringify(data)});else await post('/api/products',{...data,stock:Number(f.get('stock')),initial_cost:f.get('initialCost')});$('dialog').close();await refresh();notice('Producto guardado');}catch(err){$('productError').textContent=err.message;}};
document.querySelectorAll('[data-stock-filter]').forEach(b=>b.onclick=()=>{
 stockFilter=b.dataset.stockFilter;
 document.querySelectorAll('[data-stock-filter]').forEach(x=>{const active=x===b;x.classList.toggle('is-active',active);x.setAttribute('aria-pressed',String(active));});
 drawProducts();
});
$('productSort').onchange=drawProducts;
$('clearCart').onclick=run(async()=>{if(busy||!cart.size)return;if(!confirm('¿Vaciar los productos de esta venta?'))return;cart.clear();await drawCart();notice('Carrito vacío');});
$('mobileCart').onclick=()=>$('checkout').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
$('search').oninput=drawProducts;$('search').onkeydown=run(async e=>{if(e.key!=='Enter')return;e.preventDefault();const q=$('search').value.trim().toLowerCase();const p=products.find(p=>p.sku.toLowerCase()===q||(p.barcode??'').toLowerCase()===q);if(p){await addToCart(p);$('search').value='';drawProducts();}});
async function charge(approval=null){if(busy||!quote||!cart.size)return;if(!paymentState(quote.total,$('paid').value||0,$('method').value).valid)throw Error('El pago no cubre el total');const payload=salePayload();if(approval)payload.approval=approval;busy=true;$('charge').disabled=true;for(const id of ['salesPanel','cashPanel','purchasesPanel','inventoryPanel','approvalForm'])$(id).inert=true;document.querySelector('.toolbar').inert=true;
 try{const s=await post('/api/sales',payload,true);cart.clear();$('paid').value='';$('discountPercent').value='0';$('discountReason').value='';$('approvalDialog').close();$('approvalForm').reset();await refresh();notice(`Ticket ${s.folio} registrado. Cambio ${pesos(s.change)}`);await showReceipt(s.id);}finally{busy=false;for(const id of ['salesPanel','cashPanel','purchasesPanel','inventoryPanel','approvalForm'])$(id).inert=false;document.querySelector('.toolbar').inert=false;await drawCart();}}
$('charge').onclick=run(async()=>{if(!quote)return;if(!confirm(`¿Confirmar venta por ${pesos(quote.total)}?`))return;if(Number($('discountPercent').value)>0&&!can('discount')){$('approvalForm').reset();$('approvalDialog').showModal();return;}await charge();});
$('approvalForm').onsubmit=run(async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const approval={username:f.get('username'),password:f.get('password')};try{await charge(approval);}finally{$('approvalForm').reset();}});$('cancelApproval').onclick=()=>$('approvalDialog').close();
for(const id of ['discountPercent','discountReason','paid','method','customer'])$(id).oninput=()=>drawCart();
$('customer').onchange=()=>{$('editCustomer').disabled=!$('customer').value;$('customerHistoryButton').disabled=!$('customer').value;$('customerHistory').replaceChildren();};
$('customerSearch').onchange=run(()=>loadCustomers());
$('newCustomer').onclick=()=>openEntity('customer');
$('editCustomer').onclick=()=>{const c=customersList.find(c=>c.id===Number($('customer').value));if(c)openEntity('customer',c);};
$('customerHistoryButton').onclick=run(async()=>{if(!$('customer').value)return;const rows=await request(`/api/customers/${$('customer').value}/sales?branch_id=${branchId()}`);$('customerHistory').replaceChildren(...rows.map(s=>node('div',`#${s.id} · ${fecha(s.created_at)} · ${pesos(s.total)}`,'sale')));if(!rows.length)$('customerHistory').textContent='Sin compras en esta sucursal';});
$('newRegister').onclick=()=>openEntity('register');
$('register').onchange=run(async()=>{$('counted').value='';await refreshCash();});
$('openCash').onclick=run(async()=>{await post('/api/cash/open',{branch_id:branchId(),register_id:Number($('register').value),opening:$('opening').value});await refresh();notice('Turno abierto a tu nombre');});
$('closeCash').onclick=run(async()=>{if(!cash.open)return;if($('counted').value===''||Number($('counted').value)<0)throw Error('Captura el efectivo contado, incluso si es cero');if(!confirm('¿Cerrar el turno con el efectivo contado?'))return;const r=await post(`/api/cash/${cash.id}/close`,{counted:$('counted').value});await refresh();notice(`Corte registrado. Diferencia ${pesos(r.difference)}`);});
$('cashMovementForm').onsubmit=run(async e=>{e.preventDefault();await post(`/api/cash/${cash.id}/${$('cashMovementKind').value}`,{amount:$('cashAmount').value,reason:$('cashReason').value},true);$('cashAmount').value='';$('cashReason').value='';await refresh();notice('Movimiento autorizado registrado');});
$('newSupplier').onclick=()=>openEntity('supplier');
$('addPurchaseLine').onclick=()=>{const id=Number($('purchaseProduct').value),quantity=Number($('purchaseQty').value),unit_cost=$('purchaseCost').value;if(!id||!Number.isInteger(quantity)||quantity<1||Number(unit_cost)<0)return notice('Partida inválida');purchaseDraft.set(id,{product_id:id,quantity,unit_cost});drawPurchaseDraft();};
$('purchaseForm').onsubmit=run(async e=>{e.preventDefault();if(!purchaseDraft.size)throw Error('Agrega partidas a la compra');await post('/api/purchases',{branch_id:branchId(),supplier_id:Number($('supplier').value),reference:$('purchaseReference').value,items:[...purchaseDraft.values()]},true);purchaseDraft.clear();drawPurchaseDraft();$('purchaseReference').value='';await refresh();notice('Orden registrada; pendiente de recibir');});
$('transferForm').onsubmit=run(async e=>{e.preventDefault();await post('/api/stock/transfers',{source_branch_id:branchId(),target_branch_id:Number($('transferTarget').value),product_id:Number($('transferProduct').value),quantity:Number($('transferQuantity').value)},true);$('transferQuantity').value='';await refresh();notice('Traspaso registrado');});
$('countForm').onsubmit=run(async e=>{e.preventDefault();await post('/api/stock/counts',{branch_id:branchId(),product_id:countingProduct.id,expected:countingProduct.stock,counted:Number($('countQty').value),reason:$('countReason').value},true);$('countDialog').close();await refresh();notice('Conteo conciliado y registrado en kardex');});$('cancelCount').onclick=()=>$('countDialog').close();
$('printReceipt').onclick=()=>window.print();$('shareReceipt').onclick=()=>window.open(`https://wa.me/?text=${encodeURIComponent(receiptText)}`,'_blank','noopener,noreferrer');$('closeReceipt').onclick=()=>$('receiptDialog').close();
$('branch').onchange=run(async()=>{cart.clear();purchaseDraft.clear();drawPurchaseDraft();myCash={open:false};cash={open:false};$('customerSearch').value='';if(can('customer_read'))await loadCustomers();await refresh();});$('reload').onclick=run(async()=>{
 const b=$('reload');if(b.disabled)return;b.disabled=true;
 try{await refresh();}finally{b.disabled=false;}
});
async function start(){me=await request('/api/auth/me');permissions=new Set(me.permissions);branches=await request('/api/branches');options('branch',branches,b=>b.name);$('who').textContent=me.username;
 $('navReports').hidden=!can('report');$('navUsers').hidden=!can('users_write');
 $('newCustomer').hidden=!can('customer_write');$('editCustomer').hidden=!can('customer_write');
 $('new').hidden=!can('catalog_write');$('checkout').hidden=!can('sale');$('navCash').hidden=!can('cash_open')&&!can('report');$('navPurchases').hidden=!can('purchase_read')&&!can('purchase_write');$('navInventory').hidden=!can('stock_write')&&!can('report');$('newSupplier').hidden=!can('purchase_write');$('purchaseForm').hidden=!can('purchase_write');
 panel(can('sale')?'sales':can('purchase_read')?'purchases':'inventory');if(!branches.length)return notice('No tienes sucursales asignadas');if(can('customer_read'))await loadCustomers();await refresh();}

let entityContext=null,entitySaving=false;
const entitySettings={
 customer:{label:'CLIENTES',singular:'cliente',permission:'customer_write',url:'/api/customers',nameMax:160},
 supplier:{label:'PROVEEDORES',singular:'proveedor',permission:'purchase_write',url:'/api/suppliers',nameMax:160},
 register:{label:'CAJAS',singular:'caja',permission:'cash_deposit',url:'/api/cash/registers',nameMax:80}
};
function openEntity(kind,record=null){
 const config=entitySettings[kind];
 if(entitySaving||!can(config.permission)||!branchId())return;
 entityContext={kind,record,branch:branchId()};$('entityForm').reset();
 $('entityKind').textContent=config.label;
 $('entityTitle').textContent=(record?'Editar ':'Registrar ')+config.singular;
 $('entityHelp').textContent='Sucursal: '+(branches.find(b=>b.id===branchId())?.name??'Actual');
 $('entityName').maxLength=config.nameMax;$('entityName').minLength=kind==='register'?1:2;
 $('entityName').value=record?.name??'';$('entityPhone').value=record?.phone??'';$('entityReference').value=record?.reference??'';
 $('entityPhoneLabel').hidden=kind==='register';$('entityReferenceLabel').hidden=kind!=='supplier';
 $('entityError').textContent='';$('entitySave').textContent='Guardar';
 $('entityDialog').showModal();$('entityName').focus();
}
$('entityCancel').onclick=()=>{if(!entitySaving)$('entityDialog').close();};
$('entityDialog').addEventListener('cancel',e=>{if(entitySaving)e.preventDefault();});
$('entityForm').onsubmit=async e=>{
 e.preventDefault();if(entitySaving||!entityContext)return;
 const context=entityContext,config=entitySettings[context.kind];
 const name=$('entityName').value.trim();
 if(name.length<$('entityName').minLength){$('entityError').textContent='Escribe un nombre válido.';$('entityName').focus();return;}
 const data={branch_id:context.branch,name};
 if(context.kind!=='register')data.phone=$('entityPhone').value.trim()||null;
 if(context.kind==='supplier')data.reference=$('entityReference').value.trim()||null;
 entitySaving=true;$('entitySave').disabled=true;$('entityCancel').disabled=true;
 for(const id of ['entityName','entityPhone','entityReference'])$(id).disabled=true;
 $('entitySave').textContent='Guardando…';$('entityForm').setAttribute('aria-busy','true');$('entityError').textContent='';
 try{
  const result=context.record?await request(config.url+'/'+context.record.id,{method:'PUT',body:JSON.stringify(data)}):await post(config.url,data);
  $('entityDialog').close();entityContext=null;
  notice(config.singular.charAt(0).toUpperCase()+config.singular.slice(1)+(context.record?' actualizado':' registrado'));
  try{
   if(context.kind==='customer'){
    $('customerSearch').value=name;await loadCustomers(result.id??context.record?.id);await drawCart();
   }else if(context.kind==='supplier')await refreshPurchases();
   else{await refresh();$('register').value=result.id;await refreshCash();}
  }catch(error){notice('Registro guardado. No se pudo actualizar la vista: '+error.message);}
 }catch(error){$('entityError').textContent=error.message;}
 finally{
  entitySaving=false;$('entitySave').disabled=false;$('entityCancel').disabled=false;
  for(const id of ['entityName','entityPhone','entityReference'])$(id).disabled=false;
  $('entitySave').textContent='Guardar';$('entityForm').removeAttribute('aria-busy');
 }
};

let loginBusy=false;
function resetLogin(){ $('loginForm').reset();$('loginPassword').type='password';$('togglePassword').textContent='Mostrar';$('togglePassword').setAttribute('aria-pressed','false');$('loginError').textContent='';$('capsWarning').hidden=true; }
$('togglePassword').onclick=()=>{const show=$('loginPassword').type==='password';$('loginPassword').type=show?'text':'password';$('togglePassword').textContent=show?'Ocultar':'Mostrar';$('togglePassword').setAttribute('aria-pressed',String(show));};
for(const event of ['keydown','keyup'])$('loginPassword').addEventListener(event,e=>{$('capsWarning').hidden=!e.getModifierState('CapsLock');});
$('loginPassword').addEventListener('blur',()=>{$('capsWarning').hidden=true;});
$('loginForm').addEventListener('input',()=>{$('loginError').textContent='';});
$('loginForm').onsubmit=async e=>{
 e.preventDefault();if(loginBusy)return;
 const form=e.currentTarget;const f=new FormData(form);const username=String(f.get('username')).trim();
 if(username.length<3){$('loginError').textContent='Escribe un usuario de al menos 3 caracteres.';$('loginUsername').focus();return;}
 loginBusy=true;$('loginSubmit').disabled=true;$('loginSubmit').textContent='Entrando…';form.setAttribute('aria-busy','true');$('loginError').textContent='';
 try{const r=await post('/api/auth/login',{username,password:f.get('password')});token=r.access_token;await start();$('loginDialog').close();resetLogin();$('logout').hidden=false;}
 catch(error){token=null;me=null;permissions.clear();invalidateReport();$('usersList').replaceChildren();$('stockAlerts').replaceChildren();$('navUsers').hidden=true;$('navReports').hidden=true;$('who').textContent='Sin sesión';$('logout').hidden=true;$('loginError').textContent=error instanceof TypeError?'No se pudo conectar con el servidor. Comprueba que la aplicación siga abierta.':error.message;}
 finally{loginBusy=false;$('loginSubmit').disabled=false;$('loginSubmit').textContent='Entrar';form.removeAttribute('aria-busy');}
};
$('logout').onclick=()=>{token=null;me=null;permissions.clear();cart.clear();purchaseDraft.clear();retryKeys.clear();myCash={open:false};cash={open:false};quote=null;quoteVersion++;for(const id of ['products','sales','inventory','purchases','suppliers','cashSessions','cashMovements','cart','customerHistory','counts','movements','cashMetrics','inventoryMetrics'])$(id).replaceChildren();invalidateReport();$('usersList').replaceChildren();$('stockAlerts').replaceChildren();$('navUsers').hidden=true;$('navReports').hidden=true;$('who').textContent='Sin sesión';$('logout').hidden=true;$('charge').disabled=true;$('mobileCart').hidden=true;$('actionToast').hidden=true;$('notice').textContent='';resetLogin();$('loginDialog').showModal();};

function filterModule(input){
 const query=input.value.trim().toLocaleLowerCase('es');
 let total=0,shown=0;
 for(const id of input.dataset.listSearch.split(',')){
  const list=$(id);let visible=0;
  for(const row of list.children){
   total++;const match=!query||row.textContent.toLocaleLowerCase('es').includes(query);
   row.hidden=!match;if(match){shown++;visible++;}
  }
  list.classList.toggle('no-matches',!!list.children.length&&!visible);
 }
 $(input.id+'Count').textContent=shown+' de '+total+' registros visibles';
}
document.querySelectorAll('[data-list-search]').forEach(input=>{
 input.addEventListener('input',()=>filterModule(input));
 for(const id of input.dataset.listSearch.split(',')){
  new MutationObserver(()=>filterModule(input)).observe($(id),{childList:true,subtree:true,characterData:true});
 }
});
document.querySelectorAll('[data-reset-search]').forEach(button=>button.onclick=()=>{
 const input=$(button.dataset.resetSearch);input.value='';filterModule(input);input.focus();
});

$('loginDialog').addEventListener('cancel',e=>e.preventDefault());$('loginDialog').showModal();


let returnSale=null, savingReturn=false, cancellationMode=false;
async function openReturn(id,cancel=false){
 const sale=await request(`/api/sales/${id}`),history=await request(`/api/sales/${id}/returns`);
 if(!can('sale_return')){showText(['DEVOLUCIONES',`Ticket ${sale.folio??sale.id}`,...history.map(r=>`Devolución #${r.id} · ${fecha(r.created_at)} · ${pesos(r.total)} · ${r.reason}`),...(!history.length?['Sin devoluciones']:[])].join('\n'));return;}
 if(cancel&&history.length)throw Error('La venta tiene devoluciones. Devuelve las unidades pendientes.');
 if(sale.status==='cancelled'){showText(['VENTA CANCELADA',`Ticket ${sale.folio??sale.id}`,...history.map(r=>`Registro #${r.id} · ${pesos(r.total)} · ${r.reason}`)].join('\n'));return;}
 cancellationMode=cancel;returnSale=sale;$('returnTitle').textContent=cancel?'Cancelar venta completa':'Devolver productos';$('saveReturn').textContent=cancel?'Confirmar cancelación':'Confirmar devolución';$('returnForm').reset();$('returnError').textContent='';
 $('returnSaleInfo').textContent=`${sale.folio??'#'+sale.id} · Total original ${pesos(sale.total)} · ${history.length} devoluciones registradas`;
 $('returnHistory').replaceChildren(...history.map(r=>node('div',`Devolución #${r.id} · ${pesos(r.total)} · ${r.reason} · ${fecha(r.created_at)}`,'sale')));
 $('returnLines').replaceChildren(...sale.items.map(i=>{
  const remaining=i.quantity-i.returned_quantity,row=node('div',undefined,'return-line');
  const label=node('label',`${i.name} · Vendidos ${i.quantity} · Pendientes ${remaining}`),qty=node('input');
  qty.type='number';qty.min='0';qty.max=String(remaining);qty.step='1';qty.value=cancel?String(remaining):'0';qty.dataset.itemId=i.id;qty.disabled=cancel||!remaining||i.refundable_total===null;qty.addEventListener('input',updateReturnTotal);label.append(qty);
  const restockLabel=node('label','Reintegrar al inventario','check'),restock=node('input');restock.type='checkbox';restock.checked=true;restock.dataset.restockId=i.id;restock.disabled=cancel||!remaining;restockLabel.prepend(restock);
  row.append(label,restockLabel);return row;
 }));
 const cash=sale.payment_method==='cash';$('returnCashLabel').hidden=!cash;$('returnReferenceLabel').hidden=cash;$('returnReference').required=!cash;
 $('returnPaymentHelp').textContent=cash?'El efectivo se descontará del turno seleccionado. Revisa y entrega el reembolso al confirmar.':'Realiza primero el reembolso en el proveedor de pago y registra su referencia. Esta aplicación no envía dinero ni cancela CFDI.';
 if(cash){const turns=await request(`/api/cash/sessions?branch_id=${sale.branch_id}`);options('returnCash',turns.filter(t=>t.open),t=>`Turno #${t.id} · ${t.register_name} · ${t.cashier_name} · Disponible ${pesos(t.expected)}`);}
 updateReturnTotal();
 $('saveReturn').disabled=!sale.items.some(i=>i.quantity>i.returned_quantity&&i.refundable_total!==null)||(cash&&!$('returnCash').value);$('returnDialog').showModal();
}
$('cancelReturn').onclick=()=>{if(!savingReturn)$('returnDialog').close();};
$('returnDialog').addEventListener('cancel',e=>{if(savingReturn)e.preventDefault();});
$('returnForm').onsubmit=async e=>{
 e.preventDefault();if(savingReturn||!returnSale)return;
 const sale=returnSale,items=[...$('returnLines').querySelectorAll('[data-item-id]')].filter(i=>Number(i.value)>0).map(i=>({sale_item_id:Number(i.dataset.itemId),quantity:Number(i.value),restock:$('returnLines').querySelector(`[data-restock-id="${i.dataset.itemId}"]`).checked}));
 if(!items.length){$('returnError').textContent='Selecciona al menos una unidad.';return;}
 if(!confirm(cancellationMode?'¿Cancelar la venta completa, reintegrar productos y registrar el reembolso?':'¿Confirmar la devolución y registrar el reembolso?'))return;
 const data={reason:$('returnReason').value.trim(),items,cash_session_id:sale.payment_method==='cash'?Number($('returnCash').value):null,payment_reference:sale.payment_method==='cash'?null:$('returnReference').value.trim()};
 savingReturn=true;for(const el of $('returnForm').elements)el.disabled=true;$('returnError').textContent='';
 try{const action=cancellationMode?'cancel':'returns',payload=cancellationMode?Object.fromEntries(Object.entries(data).filter(([k])=>k!=='items')):data;const r=await post(`/api/sales/${sale.id}/${action}`,payload,true);$('returnDialog').close();returnSale=null;
  notice(`${r.kind==='cancellation'?'Cancelación':'Devolución'} #${r.id} registrada por ${pesos(r.total)}`);
  try{await refresh();}catch(error){notice('Operación guardada. Actualiza la pantalla: '+error.message);}
  showText(['LI PUNTO DE VENTA',`${r.kind==='cancellation'?'Cancelación':'Devolución'} #${r.id}`,`Ticket original ${sale.folio??sale.id}`,fecha(r.created_at),`Motivo: ${r.reason}`,`Autorizó usuario #${r.actor_id}`,
   ...r.items.map(i=>`${sale.items.find(x=>x.id===i.sale_item_id).name} · ${i.quantity} · ${pesos(i.total)} · ${i.restock?'Reintegrado':'Sin reintegro'}`),`Reembolso: ${pesos(r.total)}`,r.cash_session_id?`Efectivo · Turno #${r.cash_session_id}`:`Reembolso externo manual · ${r.payment_reference}`,'Comprobante interno sin CFDI'].join('\n'));
 }catch(error){$('returnError').textContent=error.message;}finally{savingReturn=false;for(const el of $('returnForm').elements)el.disabled=false;}
};

function updateReturnTotal(){
 if(!returnSale)return;let cents=0;
 for(const input of $('returnLines').querySelectorAll('[data-item-id]')){
  const item=returnSale.items.find(i=>i.id===Number(input.dataset.itemId)),qty=Number(input.value);
  if(!Number.isInteger(qty)||qty<0||qty>Number(input.max)){$('returnTotal').textContent='Revisa las cantidades seleccionadas.';return;}
  const original=Math.round(Number(item.refundable_total??0)*100),previous=item.returned_quantity;
  cents+=Math.round(original*(previous+qty)/item.quantity)-Math.round(original*previous/item.quantity);
 }
 $('returnTotal').textContent='Reembolso: '+pesos(cents/100);
}

async function showCashCut(id){
 const session=await request(`/api/cash/${id}/cut`),c=session.cut;
 const names={cash:'Efectivo',card:'Tarjeta (manual)',transfer:'Transferencia (manual)',mercado_pago:'Mercado Pago (integrado)'};
 showText(['LI PUNTO DE VENTA',session.open?'CORTE PROVISIONAL · TURNO ABIERTO':'CORTE DE CAJA',
  `${session.register_name} · Turno #${id}`,`Cajero: ${session.cashier_name}`,`Apertura: ${fecha(session.opened_at)}`,
  session.closed_at?`Cierre: ${fecha(session.closed_at)} · Usuario #${c.closed_by??'—'}`:'',
  !session.open&&!c.snapshot?'Corte anterior sin snapshot de desglose. Esperado conservado al cierre.':'',
  '',`Ventas: ${c.sales_count} · Importe bruto ${pesos(c.gross_sales)}`,
  ...Object.entries(c.payments).map(([method,p])=>`${names[method]}: ${p.count} ventas · ${pesos(p.gross)} · Reembolsos de estos tickets ${pesos(p.ticket_refunds)}`),
  '',`Fondo inicial: ${pesos(c.opening)}`,`Entradas: ${pesos(c.deposited)}`,`Retiros: ${pesos(c.withdrawn)}`,
  `Reembolsos efectivos entregados por este turno: ${pesos(c.refunded)}`,`Efectivo esperado: ${pesos(c.expected)}`,
  c.counted!==null?`Efectivo contado: ${pesos(c.counted)}`:'Pendiente de conteo',c.difference!==null?`Diferencia: ${pesos(c.difference)}`:'',
  '', 'Tarjeta y transferencia no forman parte del efectivo esperado.','Los reembolsos de tickets y las salidas de efectivo muestran conceptos distintos; no se suman entre sí.'].join('\n'));
}

const roleNames={admin_general:'Administrador general',admin_sucursal:'Administrador de sucursal',cajero:'Cajero',almacenista:'Almacenista',supervisor_inventarios:'Supervisor de inventarios',contabilidad:'Contabilidad',repartidor:'Repartidor',auditoria:'Auditoría / consulta'};
let minimumContext=null,editingUser=null,reportData=null,reportQuery=null,reportVersion=0;
function openMinimum(p){minimumContext={id:p.id,branch_id:branchId()};$('minimumProduct').textContent=p.name+' · '+branches.find(b=>b.id===branchId()).name;$('minimumValue').value=p.minimum;$('minimumError').textContent='';$('minimumDialog').showModal();}
$('minimumCancel').onclick=()=>$('minimumDialog').close();
$('minimumForm').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{await request(`/api/stock/${minimumContext.id}/minimum`,{method:'PUT',body:JSON.stringify({...minimumContext,minimum:Number($('minimumValue').value)})});$('minimumDialog').close();notice('Mínimo guardado');await refresh();}catch(err){$('minimumError').textContent=err.message;}finally{b.disabled=false;}};
async function loadUsers(){const rows=await request('/api/users');$('usersList').replaceChildren(...rows.map(u=>{const row=node('div',undefined,'sale');row.append(node('span',`${u.username} · ${roleNames[u.role]} · ${u.active?'Activo':'Inactivo'} · ${u.branch_ids.map(id=>branches.find(b=>b.id===id)?.name??id).join(', ')}`),button('Editar',()=>openUser(u)));return row;}));}
function openUser(u=null){editingUser=u;$('userForm').reset();$('userTitle').textContent=u?'Editar usuario':'Crear usuario';$('userError').textContent='';$('userName').value=u?.username??'';
 $('userRole').replaceChildren(...Object.entries(roleNames).map(([id,name])=>{const o=node('option',name);o.value=id;return o;}));$('userRole').value=u?.role??'cajero';$('userActive').checked=u?.active??true;$('userActive').disabled=!u;
 $('userPassword').required=!u;$('userPasswordHelp').textContent=u?'Deja la contraseña vacía para conservarla. Mínimo 12 caracteres si la cambias.':'Contraseña de 12 a 200 caracteres.';
 $('userBranches').replaceChildren(...branches.map(b=>{const label=node('label',b.name,'check'),input=node('input');input.type='checkbox';input.value=b.id;input.checked=u?u.branch_ids.includes(b.id):b.id===branchId();label.prepend(input);return label;}));$('userDialog').showModal();}
$('newUser').onclick=()=>openUser();$('userCancel').onclick=()=>$('userDialog').close();
$('userForm').onsubmit=async e=>{e.preventDefault();const branch_ids=[...$('userBranches').querySelectorAll('input:checked')].map(i=>Number(i.value));if(!branch_ids.length){$('userError').textContent='Selecciona al menos una sucursal.';return;}
 const data={username:$('userName').value.trim(),role:$('userRole').value,branch_ids,password:$('userPassword').value};if(editingUser){data.active=$('userActive').checked;if(!data.password)delete data.password;}
 const b=e.submitter;b.disabled=true;try{if(editingUser)await request(`/api/users/${editingUser.id}`,{method:'PUT',body:JSON.stringify(data)});else await post('/api/users',data);
  $('userDialog').close();$('userPassword').value='';if(editingUser?.id===me.id){$('logout').click();notice('Usuario actualizado. Inicia sesión de nuevo.');}else{await loadUsers();notice('Usuario guardado');}
 }catch(err){$('userError').textContent=err.message;}finally{b.disabled=false;}};
function invalidateReport(){reportVersion++;reportData=null;reportQuery=null;$('exportExcel').disabled=true;$('reportPdf').disabled=true;for(const id of ['reportMetrics','reportProducts','reportEvents'])$(id).replaceChildren();$('reportWarning').textContent='Selecciona filtros y consulta el reporte.';}
const localToday=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Mexico_City',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());$('reportStart').value=localToday;$('reportEnd').value=localToday;
async function loadReportCashiers(){const rows=await request(`/api/reports/cashiers?branch_id=${branchId()}`);$('reportCashier').replaceChildren(node('option','Todos'),...rows.map(r=>{const o=node('option',r.name);o.value=r.id;return o;}));$('reportCashier').firstChild.value='';}
for(const id of ['reportStart','reportEnd','reportCashier'])$(id).addEventListener('change',invalidateReport);
$('reportForm').onsubmit=async e=>{e.preventDefault();invalidateReport();const version=reportVersion,b=e.submitter;b.disabled=true;
 const query=new URLSearchParams({branch_id:branchId(),start:$('reportStart').value,end:$('reportEnd').value});if($('reportCashier').value)query.set('cashier_id',$('reportCashier').value);
 try{const r=await request('/api/reports/sales?'+query);if(version!==reportVersion)return;reportData=r;reportQuery=query.toString();
 $('reportMetrics').replaceChildren(metric('Ventas brutas',pesos(r.gross)),metric('Reembolsos',pesos(r.refunds)),metric('Total neto',pesos(r.total)),metric('Utilidad estimada',pesos(r.profit)));
 $('reportWarning').textContent=`${r.sales_count} ventas · ${r.return_count} reembolsos · ${r.missing_cost_lines} partidas vendidas sin costo registrado. Utilidad antes de gastos operativos.`;
 $('reportProducts').replaceChildren(...r.products.map(p=>node('div',`${p.name} · ${p.units} unidades netas · ${pesos(p.net)} sin impuesto`,'sale')));
 $('reportEvents').replaceChildren(...r.events.map(v=>node('div',`${v.type} #${v.id} · ${v.folio??'Sin folio'} · ${fecha(v.created_at)} · Cajero #${v.cashier_id??'Anterior'} · ${v.method} · ${pesos(v.amount)}`,'sale')));$('exportExcel').disabled=false;$('reportPdf').disabled=false;
 }catch(err){$('reportWarning').textContent=err.message;}finally{b.disabled=false;}};
$('exportExcel').onclick=run(async()=>{if(!reportQuery)return;const b=$('exportExcel');b.disabled=true;try{const response=await fetch('/api/reports/sales.xlsx?'+reportQuery,{headers:{Authorization:`Bearer ${token}`}});if(!response.ok){const err=await response.json();throw Error(err.detail??'No se pudo exportar');}const blob=await response.blob(),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='LI_Reporte_Ventas.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}finally{b.disabled=!reportData;}});
$('reportPdf').onclick=()=>{if(!reportData)return;const r=reportData;showText(['LI PUNTO DE VENTA','REPORTE DE VENTAS',`${r.start} a ${r.end} · ${r.timezone}`,`Sucursal #${r.branch_id} · Cajero ${r.cashier_id??'Todos'}`,`Bruto ${pesos(r.gross)} · Reembolsos ${pesos(r.refunds)} · Neto ${pesos(r.total)}`,`Utilidad estimada ${pesos(r.profit)} · ${r.missing_cost_lines} partidas sin costo`,'','PRODUCTOS',...r.products.map(p=>`${p.name}: ${p.units} unidades netas · ${pesos(p.net)}`),'','MOVIMIENTOS',...r.events.map(v=>`${v.type} #${v.id} · ${v.folio} · ${fecha(v.created_at)} · ${pesos(v.amount)}`),'','Los reembolsos corresponden a su fecha de registro. Utilidad antes de gastos operativos.'].join('\n'));};

$('mpCheckout').onclick=run(async()=>{
 if(!quote||!cart.size||!myCash.open)throw Error('Agrega productos y abre tu turno.');
 const b=$('mpCheckout');b.disabled=true;
 try{const result=await post('/api/payments/checkout',salePayload(),true);cart.clear();$('paid').value='';await refresh();notice('Checkout creado. Abre el enlace y confirma el pago en la lista.');}
 finally{b.disabled=false;}
});
async function loadIntegratedPayments(){
 const rows=await request(`/api/payments?branch_id=${branchId()}`);
 $('mpPayments').replaceChildren(...rows.map(p=>{const row=node('div',undefined,'sale');row.append(node('span',`Mercado Pago · ${pesos(p.amount)} · ${p.status} · ${fecha(p.created_at)}`));
 if(p.checkout_url&&['creating','pending','in_process','rejected'].includes(p.status)){const link=node('a','Abrir Checkout');link.href=p.checkout_url;link.target='_blank';link.rel='noopener noreferrer';row.append(link);}
 if(p.actor_id===me.id&&!p.review_reason&&p.payment_id&&['approved','completed'].includes(p.status))row.append(button(p.status==='completed'?'Ver ticket confirmado':'Confirmar pago y emitir ticket',async()=>{let confirmation={};if(p.status!=='completed'){
 if(!myCash.open)throw Error('Abre tu turno para emitir el ticket del pago aprobado.');
 if(myCash.id!==p.original_cash_session_id&&!confirm(`El turno original ${p.original_cash_session_id} debe estar cerrado. ¿Registrar la entrega en tu turno actual ${myCash.id}?`))return;
 confirmation={cash_session_id:myCash.id};
 }const sale=await post(`/api/payments/${p.id}/confirm`,confirmation);await refresh();await showReceipt(sale.id);}));
 row.append(button('Consultar proveedor',async()=>{await post(`/api/payments/${p.id}/reconcile`,{});await refresh();notice('Consulta del proveedor terminada.');}));
 if(!p.cancelled_at&&!p.review_reason&&!['approved','completed'].includes(p.status)&&(p.actor_id===me.id||['admin_general','admin_sucursal'].includes(me.role)))row.append(button(p.cancellation_pending?'Reintentar cancelación':'Cancelar checkout',async()=>{checkoutCancelId=p.id;$('checkoutCancelReason').value='';$('checkoutCancelError').textContent='';$('checkoutCancelDialog').showModal();}));
 if(p.cancelled_at)row.append(node('small','Checkout cancelado · reserva liberada'));
 if(p.cancellation_pending)row.append(node('small','Cancelación pendiente · reserva conservada'));
 if(p.delivery_cash_session_id)row.append(node('small',`Turno original ${p.original_cash_session_id} · Entrega en turno ${p.delivery_cash_session_id}`));
 if(p.reserved)row.append(node('small','Inventario reservado'));
 if(p.review_reason)row.append(node('strong',`Requiere revisión: ${p.review_reason}`));
 return row;}));
}

let checkoutCancelId=null, checkoutCancelling=false;
$('checkoutCancelBack').onclick=()=>{if(!checkoutCancelling)$('checkoutCancelDialog').close();};
$('checkoutCancelDialog').addEventListener('cancel',e=>{if(checkoutCancelling)e.preventDefault();});
$('checkoutCancelForm').onsubmit=async e=>{
 e.preventDefault();if(checkoutCancelling)return;checkoutCancelling=true;$('checkoutCancelSubmit').disabled=true;
 try{await post(`/api/payments/${checkoutCancelId}/cancel`,{reason:$('checkoutCancelReason').value.trim()});$('checkoutCancelDialog').close();await refresh();notice('Checkout cancelado. Reserva liberada.');}
 catch(err){$('checkoutCancelError').textContent=err.message;await refresh().catch(()=>{});}
 finally{checkoutCancelling=false;$('checkoutCancelSubmit').disabled=false;}
};

const $ = id => document.getElementById(id);
const pesos = value => new Intl.NumberFormat('es-MX', {style:'currency', currency:'MXN'}).format(value);
const fecha = value => new Date(value).toLocaleString('es-MX');
let token=null, me=null, permissions=new Set(), branches=[], products=[], catalog=[], customersList=[];
let cart=new Map(), purchaseDraft=new Map(), sessions=[], cash={open:false}, myCash={open:false};
let editingProduct=null, countingProduct=null, quote=null, quoteVersion=0, busy=false, receiptText='';
const retryKeys=new Map();
const branchId=()=>Number($('branch').value);
const can=permission=>permissions.has(permission);
const notice=message=>$('notice').textContent=message;
const run=fn=>async event=>{try{await fn(event);}catch(error){notice(error.message);}};
function node(tag, text, className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function button(text, action){const b=node('button',text);b.type='button';b.onclick=run(action);return b;}
function options(id, rows, label, selected){const prev=selected??$(id).value;$(id).replaceChildren(...rows.map(r=>{const o=node('option',label(r));o.value=r.id;return o;}));if(rows.some(r=>String(r.id)===String(prev)))$(id).value=String(prev);}
async function request(url, opts={}){
  const response=await fetch(url,{...opts,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{ }),...opts.headers}});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map(d=>`${d.loc.at(-1)}: ${d.msg}`).join('; '):'Error de conexión');
  return data;
}
async function post(url, data, withKey=false){
  const fingerprint=JSON.stringify([url,Object.fromEntries(Object.entries(data).filter(([key])=>key!=='approval'))]);
  if(withKey&&!retryKeys.has(fingerprint))retryKeys.set(fingerprint,crypto.randomUUID());
  const result=await request(url,{method:'POST',headers:withKey?{'Idempotency-Key':retryKeys.get(fingerprint)}:{},body:JSON.stringify(data)});
  if(withKey)retryKeys.delete(fingerprint);
  return result;
}
function panel(name){for(const p of ['sales','cash','purchases','inventory'])$(p+'Panel').hidden=p!==name;}
for(const [id,p] of [['navSales','sales'],['navCash','cash'],['navPurchases','purchases'],['navInventory','inventory']])$(id).onclick=()=>panel(p);
async function loadCustomers(selected=''){
  customersList=await request(`/api/customers?branch_id=${branchId()}&q=${encodeURIComponent($('customerSearch').value.trim())}`);
  options('customer',[{id:'',name:'Público general'},...customersList],c=>c.name+(c.phone?` · ${c.phone}`:''),selected);
  $('editCustomer').disabled=!$('customer').value;$('customerHistoryButton').disabled=!$('customer').value;
}
function salePayload(){return {branch_id:branchId(),cash_session_id:myCash.id??null,customer_id:Number($('customer').value)||null,
  discount_percent:$('discountPercent').value||'0',discount_reason:$('discountReason').value.trim()||null,
  items:[...cart].map(([product_id,quantity])=>({product_id,quantity})),payment_method:$('method').value,paid:$('paid').value||'0'};}
async function drawCart(){
  const version=++quoteVersion;quote=null;$('charge').disabled=true;
  $('cart').replaceChildren(...[...cart].map(([id,qty])=>{const p=products.find(x=>x.id===id);const row=node('div',undefined,'cartline');
    row.append(node('span',`${p?.name??'Producto'} × ${qty}`),button('−',()=>{qty===1?cart.delete(id):cart.set(id,qty-1);return drawCart();}),button('+',()=>{if(qty>=p.stock)return notice('No hay más existencias');cart.set(id,qty+1);return drawCart();}));return row;}));
  for(const id of ['subtotal','tax','total','discountTotal'])$(id).textContent=pesos(0);
  if(!cart.size||!can('sale'))return;
  try{const result=await post('/api/sales/quote',salePayload());if(version!==quoteVersion)return;quote=result;
    $('subtotal').textContent=pesos(result.subtotal);$('tax').textContent=pesos(result.tax);$('total').textContent=pesos(result.total);$('discountTotal').textContent=pesos(result.discount_total);
    $('charge').disabled=!myCash.open||busy;
  }catch(error){if(version===quoteVersion)notice(error.message);}
}
function addToCart(p){if(!p.active||!can('sale'))return;if((cart.get(p.id)||0)>=p.stock)return notice('No hay más existencias');cart.set(p.id,(cart.get(p.id)||0)+1);return drawCart();}
function drawProducts(){const q=$('search').value.trim().toLowerCase();
  $('products').replaceChildren(...products.filter(p=>[p.name,p.sku,p.barcode??''].some(v=>v.toLowerCase().includes(q))).map(p=>{
    const card=node('article',undefined,'card');const buy=button(p.name,()=>addToCart(p));buy.disabled=!can('sale')||!p.active||p.stock<=0;
    card.append(buy,node('em',pesos(p.price)),node('small',`${p.sku} · ${p.unit} · Stock ${p.stock}${p.active?'':' · Inactivo'}`),node('small',p.tax_exempt?'Exento':`Impuesto ${Number(p.tax_rate)*100}% · Precio ${p.price_includes_tax?'con':'sin'} impuestos`));
    if(can('catalog_write'))card.append(button('Editar',()=>openProduct(p)));return card;
  }));
}
function drawInventory(){
  $('inventory').replaceChildren(...products.map(p=>{const row=node('div',undefined,'sale');row.append(node('span',`${p.sku} · ${p.name} · ${p.stock} ${p.unit} · Costo promedio ${pesos(p.average_cost)}`));
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
  $('cashStatus').textContent=cash.open?`${cash.register_name} · Turno #${cash.id} · ${cash.cashier_name} · Esperado ${pesos(cash.expected)}`:'Caja sin turno abierto';
  $('checkoutCash').textContent=myCash.open?`${myCash.register_name} · Turno #${myCash.id}`:'Abre tu turno en Cajas y turnos para vender';
  $('openControls').hidden=cash.open||!can('cash_open');$('closeControls').hidden=!cash.open||!can('cash_close')||(!own&&!manager);
  $('cashMovementForm').hidden=!cash.open||!manager;$('newRegister').hidden=!manager;
  const moves=cash.open&&(own||manager)?await request(`/api/cash/${cash.id}/movements`):[];
  $('cashMovements').replaceChildren(...moves.map(m=>{const row=node('div',undefined,'sale');row.append(node('span',`#${m.id} · ${m.kind==='deposit'?'Entrada':'Retiro'} · ${pesos(m.amount)} · ${m.reason}`),button('Comprobante',()=>showText(`LI PUNTO DE VENTA\n${branches.find(b=>b.id===branchId()).name}\n${cash.register_name} · Turno #${m.session_id}\nMovimiento #${m.id}\n${fecha(m.created_at)}\n${m.kind==='deposit'?'Entrada':'Retiro'}: ${pesos(m.amount)}\nMotivo: ${m.reason}\nAutorizado por usuario #${m.actor_id}`)));return row;}));
  $('cashSessions').replaceChildren(...sessions.map(s=>{const row=node('div',undefined,'sale');row.append(node('span',`${s.register_name} · Turno #${s.id} · ${s.cashier_name} · ${s.open?'Abierto':'Cerrado'} · Esperado ${pesos(s.expected)}${s.counted===null?'':` · Diferencia ${pesos(Number(s.counted)-Number(s.expected))}`}`),button('Ver corte',()=>showText(`LI PUNTO DE VENTA\nTurno #${s.id} · ${s.register_name}\nCajero: ${s.cashier_name}\nApertura: ${fecha(s.opened_at)}\n${s.closed_at?`Cierre: ${fecha(s.closed_at)}`:'Turno abierto'}\nFondo: ${pesos(s.opening)}\nEntradas: ${pesos(s.deposited)}\nRetiros: ${pesos(s.withdrawn)}\nEsperado: ${pesos(s.expected)}\nContado: ${s.counted===null?'Pendiente':pesos(s.counted)}\nDiferencia: ${s.counted===null?'Pendiente':pesos(Number(s.counted)-Number(s.expected))}`)));return row;}));
}
function showText(text){receiptText=text;$('receiptContent').textContent=text;$('receiptDialog').showModal();}
async function showReceipt(id){const s=await request(`/api/sales/${id}`);showText(['LI PUNTO DE VENTA',s.branch_name,`Ticket ${s.folio??s.id}`,`Turno #${s.cash_session_id}`,fecha(s.created_at),s.customer_name??'Público general','',
 ...s.items.map(i=>`${i.quantity} ${i.unit} · ${i.name}\n  Base ${pesos(i.line_total)}${i.tax!==null?` · Impuesto ${pesos(i.tax)}`:''}`),'',`Descuento aplicado: ${pesos(s.discount_total)}`,`Subtotal después del descuento: ${pesos(s.subtotal)}`,`Impuestos: ${pesos(s.tax)}`,`Total: ${pesos(s.total)}`,`Pago: ${{cash:'Efectivo',card:'Tarjeta',transfer:'Transferencia'}[s.payment_method]}`,`Recibido: ${pesos(s.paid)}`,`Cambio: ${pesos(s.change)}`,'','Comprobante de venta. No es factura CFDI.'].join('\n'));}
function drawPurchaseDraft(){ $('purchaseDraft').replaceChildren(...[...purchaseDraft].map(([id,x])=>{const row=node('div',undefined,'sale');row.append(node('span',`${catalog.find(p=>p.id===id)?.name} · ${x.quantity} × ${pesos(x.unit_cost)}`),button('Quitar',()=>{purchaseDraft.delete(id);drawPurchaseDraft();}));return row;})); }
async function refreshPurchases(){
  const suppliers=await request(`/api/suppliers?branch_id=${branchId()}`);options('supplier',suppliers,s=>s.name);
  $('suppliers').replaceChildren(...suppliers.map(s=>{const row=node('div',undefined,'sale');row.append(node('span',`${s.name} · ${s.phone??''} · ${s.reference??''}`));if(can('purchase_write'))row.append(button('Editar',async()=>{const name=prompt('Nombre del proveedor',s.name);if(name===null)return;const phone=prompt('Teléfono',s.phone??'');if(phone===null)return;const reference=prompt('Referencia',s.reference??'');if(reference===null)return;await request(`/api/suppliers/${s.id}`,{method:'PUT',body:JSON.stringify({branch_id:branchId(),name,phone,reference})});await refreshPurchases();notice('Proveedor actualizado');}));return row;}));
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
  if(can('cash_open')||can('report'))jobs.push(refreshCash());
  if(can('sale')||can('report'))jobs.push((async()=>{const sales=await request(`/api/sales?branch_id=${branchId()}`);$('sales').replaceChildren(...sales.map(s=>{const row=node('div',undefined,'sale');row.append(node('span',`${s.folio??'#'+s.id} · ${fecha(s.created_at)}`),node('b',pesos(s.total)),button('Ticket',()=>showReceipt(s.id)));return row;}));})());
  if(can('report'))jobs.push((async()=>{const s=await request(`/api/reports/summary?branch_id=${branchId()}`);$('summary').textContent=`${s.sales_count} ventas · ${pesos(s.total)} · Efectivo ${pesos(s.by_method.cash)}`;})());else $('summary').textContent='Disponible para supervisión';
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
$('search').oninput=drawProducts;$('search').onkeydown=run(async e=>{if(e.key!=='Enter')return;e.preventDefault();const q=$('search').value.trim().toLowerCase();const p=products.find(p=>p.sku.toLowerCase()===q||(p.barcode??'').toLowerCase()===q);if(p){await addToCart(p);$('search').value='';drawProducts();}});
async function charge(approval=null){if(busy||!quote||!cart.size)return;const payload=salePayload();if(approval)payload.approval=approval;busy=true;$('charge').disabled=true;for(const id of ['salesPanel','cashPanel','purchasesPanel','inventoryPanel','approvalForm'])$(id).inert=true;document.querySelector('.toolbar').inert=true;
 try{const s=await post('/api/sales',payload,true);cart.clear();$('paid').value='';$('discountPercent').value='0';$('discountReason').value='';$('approvalDialog').close();$('approvalForm').reset();await refresh();notice(`Ticket ${s.folio} registrado. Cambio ${pesos(s.change)}`);await showReceipt(s.id);}finally{busy=false;for(const id of ['salesPanel','cashPanel','purchasesPanel','inventoryPanel','approvalForm'])$(id).inert=false;document.querySelector('.toolbar').inert=false;await drawCart();}}
$('charge').onclick=run(async()=>{if(!quote)return;if(!confirm(`¿Confirmar venta por ${pesos(quote.total)}?`))return;if(Number($('discountPercent').value)>0&&!can('discount')){$('approvalForm').reset();$('approvalDialog').showModal();return;}await charge();});
$('approvalForm').onsubmit=run(async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const approval={username:f.get('username'),password:f.get('password')};try{await charge(approval);}finally{$('approvalForm').reset();}});$('cancelApproval').onclick=()=>$('approvalDialog').close();
for(const id of ['discountPercent','discountReason','paid','method','customer'])$(id).oninput=()=>drawCart();
$('customer').onchange=()=>{$('editCustomer').disabled=!$('customer').value;$('customerHistoryButton').disabled=!$('customer').value;$('customerHistory').replaceChildren();};
$('customerSearch').onchange=run(()=>loadCustomers());
$('newCustomer').onclick=run(async()=>{const name=prompt('Nombre del cliente');if(name===null)return;const phone=prompt('Teléfono (opcional)')??'';const c=await post('/api/customers',{branch_id:branchId(),name,phone});$('customerSearch').value=c.name;await loadCustomers(c.id);await drawCart();notice('Cliente registrado');});
$('editCustomer').onclick=run(async()=>{const c=customersList.find(c=>c.id===Number($('customer').value));if(!c)return;const name=prompt('Nombre',c.name);if(name===null)return;const phone=prompt('Teléfono',c.phone??'');if(phone===null)return;await request(`/api/customers/${c.id}`,{method:'PUT',body:JSON.stringify({branch_id:branchId(),name,phone})});$('customerSearch').value=name;await loadCustomers(c.id);notice('Cliente actualizado');});
$('customerHistoryButton').onclick=run(async()=>{if(!$('customer').value)return;const rows=await request(`/api/customers/${$('customer').value}/sales?branch_id=${branchId()}`);$('customerHistory').replaceChildren(...rows.map(s=>node('div',`#${s.id} · ${fecha(s.created_at)} · ${pesos(s.total)}`,'sale')));if(!rows.length)$('customerHistory').textContent='Sin compras en esta sucursal';});
$('newRegister').onclick=run(async()=>{const name=prompt('Nombre de la caja');if(name===null)return;const r=await post('/api/cash/registers',{branch_id:branchId(),name});await refresh();$('register').value=r.id;await refreshCash();});
$('register').onchange=run(()=>refreshCash());
$('openCash').onclick=run(async()=>{await post('/api/cash/open',{branch_id:branchId(),register_id:Number($('register').value),opening:$('opening').value});await refresh();notice('Turno abierto a tu nombre');});
$('closeCash').onclick=run(async()=>{if(!cash.open||!confirm('¿Cerrar el turno con el efectivo contado?'))return;const r=await post(`/api/cash/${cash.id}/close`,{counted:$('counted').value});await refresh();notice(`Corte registrado. Diferencia ${pesos(r.difference)}`);});
$('cashMovementForm').onsubmit=run(async e=>{e.preventDefault();await post(`/api/cash/${cash.id}/${$('cashMovementKind').value}`,{amount:$('cashAmount').value,reason:$('cashReason').value},true);$('cashAmount').value='';$('cashReason').value='';await refresh();notice('Movimiento autorizado registrado');});
$('newSupplier').onclick=run(async()=>{const name=prompt('Nombre o razón social del proveedor');if(name===null)return;const phone=prompt('Teléfono (opcional)')??'';const reference=prompt('Referencia o RFC (opcional)')??'';await post('/api/suppliers',{branch_id:branchId(),name,phone,reference});await refreshPurchases();notice('Proveedor registrado');});
$('addPurchaseLine').onclick=()=>{const id=Number($('purchaseProduct').value),quantity=Number($('purchaseQty').value),unit_cost=$('purchaseCost').value;if(!id||!Number.isInteger(quantity)||quantity<1||Number(unit_cost)<0)return notice('Partida inválida');purchaseDraft.set(id,{product_id:id,quantity,unit_cost});drawPurchaseDraft();};
$('purchaseForm').onsubmit=run(async e=>{e.preventDefault();if(!purchaseDraft.size)throw Error('Agrega partidas a la compra');await post('/api/purchases',{branch_id:branchId(),supplier_id:Number($('supplier').value),reference:$('purchaseReference').value,items:[...purchaseDraft.values()]},true);purchaseDraft.clear();drawPurchaseDraft();$('purchaseReference').value='';await refresh();notice('Orden registrada; pendiente de recibir');});
$('transferForm').onsubmit=run(async e=>{e.preventDefault();await post('/api/stock/transfers',{source_branch_id:branchId(),target_branch_id:Number($('transferTarget').value),product_id:Number($('transferProduct').value),quantity:Number($('transferQuantity').value)},true);$('transferQuantity').value='';await refresh();notice('Traspaso registrado');});
$('countForm').onsubmit=run(async e=>{e.preventDefault();await post('/api/stock/counts',{branch_id:branchId(),product_id:countingProduct.id,expected:countingProduct.stock,counted:Number($('countQty').value),reason:$('countReason').value},true);$('countDialog').close();await refresh();notice('Conteo conciliado y registrado en kardex');});$('cancelCount').onclick=()=>$('countDialog').close();
$('printReceipt').onclick=()=>window.print();$('shareReceipt').onclick=()=>window.open(`https://wa.me/?text=${encodeURIComponent(receiptText)}`,'_blank','noopener,noreferrer');$('closeReceipt').onclick=()=>$('receiptDialog').close();
$('branch').onchange=run(async()=>{cart.clear();purchaseDraft.clear();drawPurchaseDraft();myCash={open:false};cash={open:false};$('customerSearch').value='';if(can('customer_read'))await loadCustomers();await refresh();});$('reload').onclick=run(()=>refresh());
async function start(){me=await request('/api/auth/me');permissions=new Set(me.permissions);branches=await request('/api/branches');options('branch',branches,b=>b.name);$('who').textContent=me.username;
 $('new').hidden=!can('catalog_write');$('checkout').hidden=!can('sale');$('navCash').hidden=!can('cash_open')&&!can('report');$('navPurchases').hidden=!can('purchase_read')&&!can('purchase_write');$('navInventory').hidden=!can('stock_write')&&!can('report');$('newSupplier').hidden=!can('purchase_write');$('purchaseForm').hidden=!can('purchase_write');
 panel(can('sale')?'sales':can('purchase_read')?'purchases':'inventory');if(!branches.length)return notice('No tienes sucursales asignadas');if(can('customer_read'))await loadCustomers();await refresh();}
$('loginForm').onsubmit=async e=>{e.preventDefault();try{const f=new FormData(e.currentTarget);const r=await post('/api/auth/login',{username:f.get('username'),password:f.get('password')});token=r.access_token;await start();$('loginDialog').close();$('loginForm').reset();$('logout').hidden=false;$('loginError').textContent='';}catch(error){$('loginError').textContent=error.message;}};
$('logout').onclick=()=>{token=null;me=null;permissions.clear();cart.clear();purchaseDraft.clear();retryKeys.clear();myCash={open:false};cash={open:false};quote=null;quoteVersion++;for(const id of ['products','sales','inventory','purchases','suppliers','cashSessions','cashMovements','cart','customerHistory','counts','movements'])$(id).replaceChildren();$('who').textContent='Sin sesión';$('logout').hidden=true;$('charge').disabled=true;$('loginForm').reset();$('loginDialog').showModal();};
$('loginDialog').addEventListener('cancel',e=>e.preventDefault());$('loginDialog').showModal();

const $ = id => document.getElementById(id);
const pesos = n => new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(n);
let products = [], cart = new Map(), cash = {open:false}, pendingKey = null, pendingTransferKey = null, token = null, role = null, branches = [], customersList = [];
const branchId = () => Number($('branch').value);
const notice = message => { $('notice').textContent = message; };
async function request(url, options={}) {
  const response = await fetch(url, {...options, headers:{'Content-Type':'application/json',...(token?{'Authorization':`Bearer ${token}`}:{}) ,...options.headers}});
  if (!response.ok) {const error=await response.json().catch(()=>({}));throw Error(error.detail || 'Error de conexión');}
  return response.json();
}
async function loadCustomers(selected=''){
  const previous=$('customer').value;
  const query=encodeURIComponent($('customerSearch').value.trim());
  const rows=await request(`/api/customers?branch_id=${branchId()}&q=${query}`);
  customersList=rows;
  $('customer').replaceChildren();
  const publicOption=document.createElement('option');publicOption.value='';publicOption.textContent='Público general';$('customer').append(publicOption);
  for(const customer of rows){const option=document.createElement('option');option.value=customer.id;option.textContent=customer.name+(customer.phone?` · ${customer.phone}`:'');$('customer').append(option);}
  $('customer').value=String(selected);
  if($('customer').selectedIndex<0)$('customer').value='';
  if(previous!==$('customer').value){pendingKey=null;$('customerHistory').replaceChildren();}
  $('editCustomer').disabled=!$('customer').value;
  $('customerHistoryButton').disabled=!$('customer').value;
}
async function refresh(){
  products = await request(`/api/products?branch_id=${branchId()}`);
  drawProducts();
  const transferable=products.filter(p=>p.stock>0);
  $('transferProduct').replaceChildren(...transferable.map(p=>{const opt=document.createElement('option');opt.value=p.id;opt.textContent=`${p.sku} · ${p.name} (${p.stock})`;return opt;}));
  $('transferTarget').replaceChildren(...branches.filter(b=>b.id!==branchId()).map(b=>{const opt=document.createElement('option');opt.value=b.id;opt.textContent=b.name;return opt;}));
  $('transferPanel').hidden=!['admin_general','admin_sucursal'].includes(role)||!transferable.length||!$('transferTarget').options.length;
  const sales = await request(`/api/sales?branch_id=${branchId()}`);
  cash = await request(`/api/cash/current?branch_id=${branchId()}`);
  if (role !== 'cajero') { const summary = await request(`/api/reports/summary?branch_id=${branchId()}`); $('summary').textContent = `${summary.sales_count} ventas · ${pesos(summary.total)} total · Efectivo ${pesos(summary.by_method.cash)}`; } else $('summary').textContent = 'Resumen disponible para supervisión';
  $('cashStatus').textContent = cash.open ? `Caja #${cash.id} abierta · Esperado ${pesos(cash.expected)}` : 'Caja cerrada';
  $('openControls').hidden = cash.open || !['admin_general','admin_sucursal','cajero'].includes(role); $('closeControls').hidden = !cash.open || !['admin_general','admin_sucursal','cajero'].includes(role); $('withdrawCash').hidden = !['admin_general','admin_sucursal'].includes(role); drawCart();
  $('sales').replaceChildren(...sales.map(s => {
    const row=document.createElement('div');row.className='sale';
    const label=document.createElement('span');label.textContent=`Venta #${s.id} · ${new Date(s.created_at).toLocaleString('es-MX')}`;
    const total=document.createElement('b');total.textContent=pesos(s.total);
    const ticket=document.createElement('button');ticket.textContent='Ticket';ticket.onclick=()=>showReceipt(s.id).catch(err=>notice(err.message));
    row.append(label,total,ticket);return row;
  }));
}
let receiptText = '';
async function showReceipt(id){
  const sale=await request(`/api/sales/${id}`);
  const lines=[`LI PUNTO DE VENTA`,sale.branch_name,`Venta #${sale.id}`,new Date(sale.created_at).toLocaleString('es-MX'),sale.customer_name?`Cliente: ${sale.customer_name}`:'Público general','',
    ...sale.items.map(item=>`${item.quantity} × ${item.name} — ${pesos(item.line_total)}`),'',
    `Subtotal: ${pesos(sale.subtotal)}`,`IVA: ${pesos(sale.tax)}`,`Total: ${pesos(sale.total)}`,
    `Forma de pago: ${{cash:'Efectivo',card:'Tarjeta',transfer:'Transferencia'}[sale.payment_method] || sale.payment_method}`,
    `Recibido: ${pesos(sale.paid)}`,`Cambio: ${pesos(sale.change)}`,'','Comprobante de venta. No es factura CFDI.'];
  receiptText=lines.join('\n');
  $('receiptContent').textContent=receiptText;
  $('receiptDialog').showModal();
}
$('printReceipt').onclick=()=>window.print();
$('shareReceipt').onclick=()=>window.open(`https://wa.me/?text=${encodeURIComponent(receiptText)}`,'_blank','noopener,noreferrer');
$('closeReceipt').onclick=()=>$('receiptDialog').close();
function drawProducts(){
  const q=$('search').value.trim().toLowerCase();
  $('products').replaceChildren(...products.filter(p=>p.name.toLowerCase().includes(q)||p.sku.toLowerCase().includes(q)).map(p=>{
    const b=document.createElement('button');b.className='card';b.disabled=p.stock<=0;
    const title=document.createElement('b');title.textContent=p.name;
    const price=document.createElement('em');price.textContent=pesos(p.price);
    const meta=document.createElement('small');meta.textContent=`${p.sku} · Disponible: ${p.stock}`;
    b.append(title,price,meta);b.onclick=()=>{let count=cart.get(p.id)||0;if(count>=p.stock)return notice('No hay más existencias');cart.set(p.id,count+1);drawCart();};return b;
  }));
}
function drawCart(){
  $('cart').replaceChildren(...[...cart].map(([id,qty])=>{
    const p=products.find(x=>x.id===id);const row=document.createElement('div');row.className='cartline';
    const label=document.createElement('span');label.textContent=`${p.name} × ${qty}`;
    const controls=document.createElement('div');const minus=document.createElement('button');minus.textContent='−';minus.onclick=()=>{qty<=1?cart.delete(id):cart.set(id,qty-1);drawCart();};
    const plus=document.createElement('button');plus.textContent='+';plus.onclick=()=>{if(qty>=p.stock)return notice('No hay más existencias');cart.set(id,qty+1);drawCart();};
    controls.append(minus,plus);row.append(label,controls);return row;
  }));
  const subtotal=[...cart].reduce((s,[id,q])=>s+Number(products.find(p=>p.id===id).price)*q,0);
  const tax=Math.round(subtotal*16)/100; $('subtotal').textContent=pesos(subtotal);$('tax').textContent=pesos(tax);$('total').textContent=pesos(subtotal+tax);
  $('charge').disabled=cart.size===0 || !cash.open;
}
$('customer').onchange=()=>{pendingKey=null;$('editCustomer').disabled=!$('customer').value;$('customerHistoryButton').disabled=!$('customer').value;$('customerHistory').replaceChildren();};
$('customerSearch').oninput=()=>{loadCustomers().catch(err=>notice(err.message));};
$('newCustomer').onclick=async()=>{const name=prompt('Nombre del cliente');if(name===null)return;const phone=prompt('Teléfono (opcional)') ?? '';try{const created=await request('/api/customers',{method:'POST',body:JSON.stringify({branch_id:branchId(),name,phone})});$('customerSearch').value=created.name;await loadCustomers(created.id);pendingKey=null;notice('Cliente registrado');}catch(err){notice(err.message);}};
$('editCustomer').onclick=async()=>{const selected=customersList.find(c=>c.id===Number($('customer').value));if(!selected)return;const name=prompt('Nombre del cliente',selected.name);if(name===null)return;const phone=prompt('Teléfono (opcional)',selected.phone||'');if(phone===null)return;try{const updated=await request(`/api/customers/${selected.id}`,{method:'PUT',body:JSON.stringify({branch_id:branchId(),name,phone})});$('customerSearch').value=updated.name;await loadCustomers(updated.id);notice('Cliente actualizado');}catch(err){notice(err.message);}};
$('customerHistoryButton').onclick=async()=>{const id=Number($('customer').value);if(!id)return;try{const sales=await request(`/api/customers/${id}/sales?branch_id=${branchId()}`);const rows=sales.map(s=>{const item=document.createElement('div');item.className='sale';item.textContent=`#${s.id} · ${new Date(s.created_at).toLocaleString('es-MX')} · ${pesos(s.total)}`;return item;});$('customerHistory').replaceChildren(...rows);if(!rows.length)$('customerHistory').textContent='Sin compras en esta sucursal';}catch(err){notice(err.message);}};
$('search').oninput=drawProducts;
$('search').onkeydown=e=>{if(e.key==='Enter'){const sku=products.find(p=>p.sku.toLowerCase()===$('search').value.trim().toLowerCase());if(sku){if((cart.get(sku.id)||0)<sku.stock){cart.set(sku.id,(cart.get(sku.id)||0)+1);drawCart();}$('search').value='';drawProducts();}}};
$('new').onclick=()=>$('dialog').showModal();
$('form').onsubmit=async e=>{if(e.submitter?.value!=='save')return;e.preventDefault();const f=new FormData(e.currentTarget);try{await request('/api/products',{method:'POST',body:JSON.stringify({sku:f.get('sku'),name:f.get('name'),price:f.get('price'),stock:Number(f.get('stock')),branch_id:branchId()})});$('dialog').close();$('form').reset();await refresh();notice('Producto agregado');}catch(err){notice(err.message);$('dialog').close();}};
$('charge').onclick=async()=>{if(!cart.size)return;const subtotal=[...cart].reduce((s,[id,q])=>s+Number(products.find(p=>p.id===id).price)*q,0);const total=Math.round((subtotal+Math.round(subtotal*16)/100)*100)/100;const method=$('method').value;const paid=Number($('paid').value);if(!Number.isFinite(paid)||paid<total){notice(`Pago insuficiente. Total: ${pesos(total)}`);return;}if(method!=='cash'&&paid!==total){notice('Tarjeta o transferencia debe coincidir con el total');return;}if(!confirm(`Confirmar venta por ${pesos(total)}?`))return;try{const s=await request('/api/sales',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':pendingKey ??= crypto.randomUUID()},body:JSON.stringify({branch_id:branchId(),customer_id:$('customer').value?Number($('customer').value):null,items:[...cart].map(([product_id,quantity])=>({product_id,quantity})),payment_method:method,paid})});pendingKey=null;cart.clear();$('paid').value='';$('customer').value='';await refresh();drawCart();notice(`Venta #${s.id} registrada. Cambio: ${pesos(s.change)}`);await showReceipt(s.id);}catch(err){notice(err.message);}};
$('branch').onchange=()=>{cart.clear();pendingKey=null;pendingTransferKey=null;loadCustomers().then(refresh).catch(err=>notice(err.message));};
$('transferForm').oninput=()=>{pendingTransferKey=null;};
$('transferForm').onsubmit=async e=>{e.preventDefault();const quantity=Number($('transferQuantity').value);if(!Number.isInteger(quantity)||quantity<1)return notice('Cantidad inválida');const target=Number($('transferTarget').value);const product=Number($('transferProduct').value);if(!confirm(`¿Traspasar ${quantity} unidades a ${$('transferTarget').selectedOptions[0].textContent}?`))return;try{const result=await request('/api/stock/transfers',{method:'POST',headers:{'Idempotency-Key':pendingTransferKey ??= crypto.randomUUID()},body:JSON.stringify({source_branch_id:branchId(),target_branch_id:target,product_id:product,quantity})});pendingTransferKey=null;$('transferQuantity').value='';await refresh();notice(`Traspaso #${result.id} registrado`);}catch(err){notice(err.message);}};
$('openCash').onclick=async()=>{try{await request('/api/cash/open',{method:'POST',body:JSON.stringify({branch_id:branchId(),opening:$('opening').value})});await refresh();notice('Caja abierta');}catch(err){notice(err.message);}};
$('withdrawCash').onclick=async()=>{try{const result=await request(`/api/cash/${cash.id}/withdraw`,{method:'POST',body:JSON.stringify({amount:$('withdrawAmount').value,reason:$('withdrawReason').value})});$('withdrawAmount').value='';$('withdrawReason').value='';await refresh();notice(`Retiro registrado: ${pesos(result.amount)}`);}catch(err){notice(err.message);}};
$('closeCash').onclick=async()=>{if(!confirm('¿Cerrar esta caja y registrar el efectivo contado?'))return;try{const result=await request(`/api/cash/${cash.id}/close`,{method:'POST',body:JSON.stringify({counted:$('counted').value})});await refresh();notice(`Corte registrado. Diferencia: ${pesos(result.difference)}`);}catch(err){notice(err.message);}};
async function start(){ $('branch').replaceChildren(); branches=await request('/api/branches'); for(const b of branches){const opt=document.createElement('option');opt.value=b.id;opt.textContent=b.name;$('branch').append(opt);} $('new').hidden = !['admin_general','admin_sucursal'].includes(role); if(branches.length){await loadCustomers();await refresh();}else notice('No tienes sucursales asignadas'); }
$('loginForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{const result=await request('/api/auth/login',{method:'POST',body:JSON.stringify({username:f.get('username'),password:f.get('password')})});token=result.access_token;role=result.role;$('who').textContent=f.get('username');$('logout').hidden=false;$('loginDialog').close();if(!['admin_general','admin_sucursal','cajero'].includes(role)){notice('Tu rol no usa esta pantalla de caja. Los módulos de tu área están en desarrollo.');return;}await start();}catch(err){$('loginError').textContent=err.message;}};
$('logout').onclick=()=>{token=null;role=null;cart.clear();products=[];$('products').replaceChildren();$('sales').replaceChildren();$('who').textContent='Sin sesión';$('logout').hidden=true;$('loginForm').reset();$('loginDialog').showModal();};
$('loginDialog').showModal();

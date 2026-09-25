const $ = id => document.getElementById(id);
const pesos = n => new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(n);
let products = [], cart = new Map();
const notice = message => { $('notice').textContent = message; };
async function request(url, options={}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json'},...options});
  if (!response.ok) {const error=await response.json().catch(()=>({}));throw Error(error.detail || 'Error de conexión');}
  return response.json();
}
async function refresh(){
  products = await request('/api/products?branch_id=1');
  drawProducts();
  const sales = await request('/api/sales?branch_id=1');
  $('sales').replaceChildren(...sales.map(s => {
    const row=document.createElement('div');row.className='sale';
    const label=document.createElement('span');label.textContent=`Venta #${s.id} · ${new Date(s.created_at).toLocaleString('es-MX')}`;
    const total=document.createElement('b');total.textContent=pesos(s.total);row.append(label,total);return row;
  }));
}
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
  $('charge').disabled=cart.size===0;
}
$('search').oninput=drawProducts;
$('search').onkeydown=e=>{if(e.key==='Enter'){const sku=products.find(p=>p.sku.toLowerCase()===$('search').value.trim().toLowerCase());if(sku){if((cart.get(sku.id)||0)<sku.stock){cart.set(sku.id,(cart.get(sku.id)||0)+1);drawCart();}$('search').value='';drawProducts();}}};
$('new').onclick=()=>$('dialog').showModal();
$('form').onsubmit=async e=>{if(e.submitter?.value!=='save')return;e.preventDefault();const f=new FormData(e.currentTarget);try{await request('/api/products',{method:'POST',body:JSON.stringify({sku:f.get('sku'),name:f.get('name'),price:f.get('price'),stock:Number(f.get('stock')),branch_id:1})});$('dialog').close();$('form').reset();await refresh();notice('Producto agregado');}catch(err){notice(err.message);$('dialog').close();}};
$('charge').onclick=async()=>{if(!cart.size)return;const subtotal=[...cart].reduce((s,[id,q])=>s+Number(products.find(p=>p.id===id).price)*q,0);const total=Math.round((subtotal+Math.round(subtotal*16)/100)*100)/100;const method=$('method').value;const paid=Number($('paid').value);if(!Number.isFinite(paid)||paid<total){notice(`Pago insuficiente. Total: ${pesos(total)}`);return;}if(method!=='cash'&&paid!==total){notice('Tarjeta o transferencia debe coincidir con el total');return;}if(!confirm(`Confirmar venta por ${pesos(total)}?`))return;try{const s=await request('/api/sales',{method:'POST',body:JSON.stringify({branch_id:1,items:[...cart].map(([product_id,quantity])=>({product_id,quantity})),payment_method:method,paid})});cart.clear();$('paid').value='';await refresh();drawCart();notice(`Venta #${s.id} registrada. Cambio: ${pesos(s.change)}`);}catch(err){notice(err.message);}};
refresh().then(drawCart).catch(err=>notice(err.message));

import { useEffect, useRef, useState } from 'react';

type Product = {sku:string;name:string;price_cents:number;available:number};
type Attempt = {key:string;sku:string;quantity:number};
export function Shop() {
  const [products,setProducts]=useState<Product[]>([]);
  const [sku,setSku]=useState('darwin-notebook');
  const [quantity,setQuantity]=useState(1);
  const [busy,setBusy]=useState(false);
  const [online,setOnline]=useState(false);
  const [message,setMessage]=useState('');
  const [attempt,setAttempt]=useState<Attempt|null>(null);
  const [confirmed,setConfirmed]=useState(false);
  const [settled,setSettled]=useState(false);
  const pending=useRef(false);
  async function load() {
    try {const r=await fetch('/shop/catalog');if(!r.ok)throw Error();setProducts(await r.json());setOnline(true);}
    catch {setOnline(false);}
  }
  useEffect(()=>{void load()},[]);
  async function checkout() {
    if(pending.current)return;
    pending.current=true;setBusy(true);setMessage('');
    const current=attempt??{key:crypto.randomUUID(),sku,quantity};
    setAttempt(current);
    try {
      const r=await fetch('/shop/checkout',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':current.key},body:JSON.stringify({sku:current.sku,quantity:current.quantity})});
      const data=await r.json();
      if(!r.ok){if(r.status===409&&data.status==='failed')setSettled(true);setMessage(`${data.detail??'Checkout unavailable'}. Retrying reuses this request key.`);return;}
      setConfirmed(true);setSettled(true);setMessage(`Order confirmed · ${data.order_id} · ${(data.amount_cents/100).toFixed(2)} demo credits`);
    } catch {setMessage('Connection interrupted. Retry with this request key to resolve the order.');}
    finally {await load();pending.current=false;setBusy(false);}
  }
  return <section className="panel shop-panel">
    <div className="section-title"><h2>Try the live shop</h2><span className={online?'online':'muted'}>{online?'SHOP CONNECTED':'SHOP OFFLINE'}</span></div>
    <p className="muted">Synthetic products and payments. Submit an order, then replay it to check that stock and payment effects happen once.</p>
    {!online?<p role="alert">The shop is unavailable. <button onClick={load}>Refresh connection</button></p>:<>
      <div className="shop-controls"><div><label htmlFor="product">Product</label><select id="product" disabled={!!attempt||busy} value={sku} onChange={e=>setSku(e.target.value)}>{products.map(p=><option key={p.sku} value={p.sku}>{p.name} · {p.available} left · {(p.price_cents/100).toFixed(2)} credits</option>)}</select></div>
      <div><label htmlFor="quantity">Quantity</label><input id="quantity" type="number" min="1" max="100" value={quantity} disabled={!!attempt||busy} onChange={e=>setQuantity(Number(e.target.value))}/></div></div>
      <div className="shop-actions"><button className="primary" disabled={busy||!Number.isInteger(quantity)||quantity<1||quantity>100} onClick={checkout}>{busy?'Processing…':attempt?(confirmed?'Replay same request':'Retry same request'):'Place demo order'}</button>
      {settled&&<button disabled={busy} onClick={()=>{setAttempt(null);setConfirmed(false);setSettled(false);setMessage('')}}>New order</button>}</div>
      {attempt&&<p className="muted">Request key: <code>{attempt.key}</code></p>}
    </>}
    <p className="result" role="status">{message}</p>
  </section>;
}

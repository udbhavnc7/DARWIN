import {useEffect, useRef, useState} from 'react';
import {Status} from './Status';
import {Action, Icon} from './Action';
import {isLive, localOnly, showcase} from './showcase';

type Product = {sku: string; name: string; price_cents: number; available: number};
type Receipt = {order_id: string; status: 'confirmed'; sku: string; quantity: number; amount_cents: number};
type Attempt = {key: string; sku: string; name: string; quantity: number; stockBefore: number | null};
type Observation = {receipt: Receipt; stock: number | null};
type Ledger = {orders: number; captures: number; payment_effects: number; outbox: number; deliveries: number;
  for_request?: {orders: number; captures: number; payment_effects: number}};

const credits = (cents: number) => `${(cents / 100).toFixed(2)} credits`;
const stockFor = (catalog: Product[] | null, sku: string) => catalog?.find(product => product.sku === sku)?.available ?? null;
const stockLabel = (stock: number | null) => stock === null ? 'Unavailable' : `${stock} left`;

export function Shop() {
  const [products, setProducts] = useState<Product[]>([]);
  const [sku, setSku] = useState('darwin-notebook');
  const [quantity, setQuantity] = useState('1');
  const [catalogState, setCatalogState] = useState<'loading' | 'connected' | 'offline'>('loading');
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [original, setOriginal] = useState<Observation | null>(null);
  const [replay, setReplay] = useState<Observation | null>(null);
  const [rejected, setRejected] = useState(false);
  const [error, setError] = useState('');
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [resetting, setResetting] = useState(false);
  const pending = useRef(false);
  const recorded = showcase && !isLive();
  const product = products.find(item => item.sku === sku) ?? products[0];
  const units = Number(quantity);
  const validQuantity = Number.isInteger(units) && units >= 1 && units <= 100;
  const canOrder = !recorded && catalogState === 'connected' && product && validQuantity && units <= product.available;

  async function loadCatalog(): Promise<Product[] | null> {
    try {
      const response = await fetch('/shop/catalog', {cache: 'no-store', signal: AbortSignal.timeout(7000)});
      if (!response.ok) throw Error();
      const catalog: Product[] = await response.json();
      setProducts(catalog);
      setCatalogState('connected');
      return catalog;
    } catch {
      setCatalogState('offline');
      return null;
    }
  }

  useEffect(() => {void loadCatalog();}, []);

  async function loadLedger(key?: string) {
    try {
      const response = await fetch(`/shop/ledger${key ? `?request_key=${encodeURIComponent(key)}` : ''}`, {cache: 'no-store', signal: AbortSignal.timeout(5000)});
      return response.ok ? await response.json() as Ledger : null;
    } catch {
      return null;
    }
  }

  async function resetDemo() {
    setResetting(true); setError('');
    try {
      const response = await fetch('/shop/reset', {method: 'POST', signal: AbortSignal.timeout(7000)});
      if (!response.ok) throw Error();
      newOrder();
      setLedger(null);
      await loadCatalog();
    } catch {
      setError('The demo shop could not be reset. Check that the shop is running, then try again.');
    } finally {
      setResetting(false);
    }
  }

  async function checkout() {
    if (pending.current || rejected || (!attempt && !canOrder)) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      let current = attempt;
      if (!current && product) {
        const before = await loadCatalog();
        const available = stockFor(before, product.sku);
        if (available === null || units > available) {
          setError(available === null ? 'The catalog is unavailable. Refresh it before placing an order.' : 'Stock changed. Choose a smaller quantity and try again.');
          return;
        }
        current = {key: crypto.randomUUID(), sku: product.sku, name: product.name, quantity: units, stockBefore: available};
        setAttempt(current);
      }
      if (!current) return;

      const response = await fetch('/shop/checkout', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'Idempotency-Key': current.key},
        body: JSON.stringify({sku: current.sku, quantity: current.quantity}), signal: AbortSignal.timeout(8000),
      });
      const data = await response.json();
      if (!response.ok || data.status !== 'confirmed') {
        if (!original && response.status === 409 && data.detail === 'out_of_stock') {
          setRejected(true);
          setError('The item ran out before checkout completed. Start a new order and choose an available item.');
          await loadCatalog();
        } else {
          setError('The shop could not confirm this request. Try again to send the same request ID and items.');
        }
        return;
      }

      const observation = {receipt: data as Receipt, stock: stockFor(await loadCatalog(), current.sku)};
      setLedger(await loadLedger(current.key));
      if (original) setReplay(observation);
      else setOriginal(observation);
    } catch {
      setError('The request could not be confirmed. If a request ID was created, retry with that same ID.');
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  function newOrder() {
    setAttempt(null);
    setOriginal(null);
    setReplay(null);
    setRejected(false);
    setError('');
    setLedger(null);
    setQuantity('1');
  }

  const sameReceipt = !!(original && replay && original.receipt.order_id === replay.receipt.order_id
    && original.receipt.sku === replay.receipt.sku && original.receipt.quantity === replay.receipt.quantity
    && original.receipt.amount_cents === replay.receipt.amount_cents);
  const stockAvailable = original?.stock != null && replay?.stock != null;
  const stockUnchanged = stockAvailable && original.stock === replay.stock;
  const step = replay ? 3 : original ? 2 : 1;

  return <section id="shop" className="page-content shop-demo" aria-label="Demo shop walkthrough">
    <div className="shop-intro">
      <p className="page-intro"><strong>Step 5 · Verify correctness.</strong> {recorded
        ? 'DARWIN’s test shop sells sample products with simulated payments. On a local install you can place an order, then resend it to see how the backend handles a duplicate request.'
        : 'Try a real checkout in DARWIN’s test shop with sample products and simulated payments. Then resend the order to see whether the backend keeps the duplicate-payment rule intact.'}</p>
      <div className="shop-intro-actions">
        <Status value={catalogState === 'loading' ? 'running' : catalogState}
          label={catalogState === 'loading' ? 'Checking shop' : catalogState === 'connected' ? (recorded ? 'Recorded catalog' : 'Shop connected') : 'Catalog unavailable'}/>
        <Action variant="quiet" icon="refresh" pending={resetting} disabled={recorded || busy || catalogState !== 'connected'}
          onClick={() => void resetDemo()}>{resetting ? 'Resetting…' : 'Reset demo shop'}</Action>
      </div>
    </div>
    <ol className="shop-steps" aria-label="Checkout walkthrough">
      {['Place a demo order', 'Resend the same request', 'Compare the results'].map((label, index) =>
        <li key={label} aria-current={step === index + 1 ? 'step' : undefined}>
          <span aria-hidden="true">{step > index + 1 ? <Icon name="check"/> : index + 1}</span>{label}
        </li>)}
    </ol>

    <div className="shop-demo-grid">
      <div className="panel shop-checkout">
        <div className="section-title"><div className="panel-heading"><span className="section-kicker">Your test order</span><h2>Checkout</h2></div><span className="baseline-badge">Simulated payments</span></div>
        {catalogState === 'offline' && <p role="alert">The catalog is offline. {attempt ? 'You can still retry the saved request.' : 'Start the local shop if it’s stopped, then refresh the catalog.'}</p>}
        {catalogState === 'loading' && <p className="muted" role="status">Loading sample products…</p>}
        {recorded && <p className="field-help">This is the recorded catalog. Placing and resending orders needs the local demo shop. Follow the README quickstart to try the duplicate-request check yourself.</p>}
        {!attempt && <div className="shop-controls">
          <div><label htmlFor="product">Product</label><select id="product" disabled={busy || catalogState !== 'connected'} value={product?.sku ?? ''} onChange={event => setSku(event.target.value)}>
            {!products.length && <option value="">No products loaded</option>}
            {products.map(item => <option key={item.sku} value={item.sku}>{item.name}{item.available === 0 ? ' (sold out)' : ''}</option>)}
          </select></div>
          <div><label htmlFor="quantity">Quantity</label><input id="quantity" type="number" min="1" max="100" step="1" value={quantity}
            disabled={busy || catalogState !== 'connected'} onChange={event => setQuantity(event.target.value)}/></div>
        </div>}
        {attempt ? <p className="shop-order-summary"><strong>{attempt.name}</strong><span>Quantity {attempt.quantity}</span></p>
          : product && <p className="shop-order-summary"><span>{credits(product.price_cents)} each · {stockLabel(product.available)}</span><strong>{validQuantity ? `Total ${credits(product.price_cents * units)}` : 'Enter 1–100 units'}</strong></p>}
        {!attempt && product && validQuantity && units > product.available && <p className="muted">Only {product.available} in stock. Choose a smaller quantity or another product.</p>}
        {original && <p className="muted">Resend the same request to simulate a retry after a slow or lost reply. DARWIN reuses the original request ID and items.</p>}
        <div className="shop-actions">
          {!rejected && <Action variant="primary" icon={attempt ? 'refresh' : 'shop'} pending={busy} disabled={!attempt && !canOrder} onClick={checkout}>
            {busy ? 'Sending…' : original ? 'Resend same request' : attempt ? 'Retry same request' : 'Place demo order'}
          </Action>}
          {(original || rejected) && <Action disabled={busy} onClick={newOrder}>Start a new order</Action>}
          {catalogState === 'offline' && <Action icon="refresh" disabled={busy} onClick={loadCatalog}>Refresh catalog</Action>}
        </div>
        {error && <p role="alert">{error}</p>}
        {attempt && <details><summary>Request details</summary><p className="muted">Request ID (idempotency key)</p><code>{attempt.key}</code></details>}
      </div>

      <div className="panel shop-observations">
        <div className="section-title"><div className="panel-heading"><span className="section-kicker">Watch the backend respond</span><h2>What the shop returned</h2></div>
          {original && <Status value="completed" label="Order confirmed"/>}
        </div>
        {!original ? <div className="empty-state"><span className="empty-state-icon"><Icon name="shop"/></span><div className="empty-state-copy"><h3>Your receipt will appear here</h3><p>Place a demo order to see its confirmation, simulated payment, and remaining stock. Then send it again to compare.</p></div><span className="empty-state-hint"><Icon name="shield"/> No real payments</span></div> : <>
          <table className="shop-comparison">
            <thead><tr><th scope="col">Result</th><th scope="col">First confirmation</th><th scope="col">Repeat request</th></tr></thead>
            <tbody>
              <tr><th scope="row">Order ID</th><td><code>{original.receipt.order_id.slice(0, 8)}</code></td><td>{replay ? <code>{replay.receipt.order_id.slice(0, 8)}</code> : '—'}</td></tr>
              <tr><th scope="row">Simulated payment</th><td>{credits(original.receipt.amount_cents)}</td><td>{replay ? credits(replay.receipt.amount_cents) : '—'}</td></tr>
              <tr><th scope="row">Catalog stock</th><td>{stockLabel(original.stock)}</td><td>{replay ? stockLabel(replay.stock) : '—'}</td></tr>
            </tbody>
          </table>
          <p className="muted">Stock before the order: {stockLabel(attempt?.stockBefore ?? null)}.</p>
          <div className="shop-verdict" role="status">
            {replay ? <>
              <strong>{sameReceipt ? 'Same receipt returned' : 'The receipt changed'}</strong>
              <p>{stockUnchanged ? 'Catalog stock stayed the same after the repeat request.' : stockAvailable
                ? 'Catalog stock changed between checks. Other checkouts can affect this count.' : 'A catalog reading was unavailable, so stock could not be compared.'}</p>
            </> : <p><strong>Next:</strong> Select <em>Resend same request</em> to compare the two responses.</p>}
          </div>
          {ledger?.for_request && <p className="shop-ledger" role="status">
            <strong>Payment ledger for this request:</strong>{' '}
            {ledger.for_request.orders} order · {ledger.for_request.captures} capture · {ledger.for_request.payment_effects} payment {ledger.for_request.payment_effects === 1 ? 'effect' : 'effects'}.
            {replay && ledger.for_request.payment_effects === 1 ? ' The repeat added no second effect.' : ''}
          </p>}
          <details><summary>Full order IDs</summary><p><code>{original.receipt.order_id}</code></p>
            {replay && <p><code>{replay.receipt.order_id}</code></p>}
          </details>
        </>}
      </div>
    </div>

    <details className="panel shop-explainer">
      <summary>How this connects to DARWIN’s architecture</summary>
      <p>The gateway sends your checkout to the Checkout API. The API reserves stock, verifies the simulated payment, and saves the order. Reusing the same request ID lets it return the existing order when a client retries. This behavior is called <strong>idempotency</strong>.</p>
      <p>Use <a href="#configuration">Alternatives</a> to see how these services fit together, or <a href="#experiments">Test &amp; break</a> to test checkout and verify payment records in an isolated run.</p>
    </details>
  </section>;
}

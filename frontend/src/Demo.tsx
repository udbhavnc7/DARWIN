import {useEffect, useRef, useState, type ReactNode} from 'react';
import {Action, Icon, type IconName} from './Action';
import {BrandMark} from './Brand';

type Step = {
  kicker: string;
  title: string;
  lede: string;
  points: {icon: IconName; text: string}[];
  visual: ReactNode;
};

function GrowthVisual() {
  return <div className="tour-growth">
    <div className="tour-growth-bars" role="img" aria-label="Growth from 100 customers on one server to 10,000 customers">
      <div><span>100</span><i className="low"/><small>one server</small></div>
      <div><span>10,000</span><i className="high"/><small>2,000 at once</small></div>
    </div>
    <div className="tour-test-group"><span className="tour-test-label">What starts to fail</span>
      <div className="tour-chips"><span className="tour-chip fault">Slow pages</span><span className="tour-chip fault">Timeouts</span><span className="tour-chip fault">Database overload</span><span className="tour-chip fault">Failed payments</span></div>
    </div>
    <div className="tour-evidence"><Icon name="settings"/>
      <span><strong>More capacity is not a decision.</strong><small>One cache, one queue or no change — it depends on the workload.</small></span>
    </div>
  </div>;
}

function ToolsVisual() {
  return <div className="tour-tools">
    <span className="tour-test-label">Existing tools provide the pieces</span>
    <div className="tour-tool-grid">
      <span className="tour-tool">AWS<small>infrastructure</small></span>
      <span className="tour-tool">Kubernetes<small>instance scaling</small></span>
      <span className="tour-tool">Redis<small>caching</small></span>
      <span className="tour-tool">Locust<small>load tests</small></span>
      <span className="tour-tool">Prometheus<small>metrics</small></span>
      <span className="tour-tool">Chaos<small>failures</small></span>
    </div>
    <span className="tour-connector"/>
    <div className="tour-gate"><Icon name="configuration"/>
      <span><strong>DARWIN coordinates one decision</strong><small>alternatives → traffic → failures → correctness → search</small></span>
    </div>
    <div className="tour-outcomes">
      <span className="tour-outcome good"><Icon name="check"/>Measured recommendation</span>
      <span className="tour-outcome bad"><Icon name="close"/>Correctness failure rejected</span>
    </div>
  </div>;
}

function MapVisual() {
  return <div className="tour-stack">
    <span className="tour-node">Public repo · pinned commit</span>
    <span className="tour-connector"/>
    <span className="tour-node accent">Backend API</span>
    <span className="tour-connector"/>
    <div className="tour-stack-row"><span className="tour-node">Database</span><span className="tour-node muted-node">Cache · optional</span><span className="tour-node muted-node">Worker · optional</span></div>
    <div className="tour-controls">
      <span className="tour-control"><b>Proven</b> from source</span>
      <span className="tour-control"><b>Guesses</b> stay labelled</span>
      <span className="tour-control"><b>Unsupported</b> stays unsupported</span>
    </div>
  </div>;
}

function AlternativesVisual() {
  return <div className="tour-alternatives">
    <div className="tour-alt"><span>A</span><strong>Basic</strong><small>1 API · no cache</small></div>
    <div className="tour-alt best"><span>B</span><strong>Cached</strong><small>2 APIs · Redis</small></div>
    <div className="tour-alt fail"><span>C</span><strong>Distributed</strong><small>services · queues</small></div>
    <div className="tour-controls">
      <span className="tour-control"><b>1–3</b> replicas</span>
      <span className="tour-control"><b>0 / 10 / 30 s</b> cache</span>
      <span className="tour-control"><b>Sync / queued</b> alerts</span>
      <span className="tour-control"><b>None / idempotent</b> retries</span>
    </div>
    <div className="tour-test-group"><span className="tour-test-label">Simulated traffic</span>
      <div className="tour-chips"><span className="tour-chip">100 users</span><span className="tour-chip">1,000 users</span><span className="tour-chip">5,000 users</span></div>
    </div>
  </div>;
}

function GateVisual() {
  return <div className="tour-gates">
    <div className="tour-test-group"><span className="tour-test-label">Faults injected</span>
      <div className="tour-chips"><span className="tour-chip fault">DB delay</span><span className="tour-chip fault">Service outage</span><span className="tour-chip fault">Payment timeout</span><span className="tour-chip fault">Duplicate delivery</span></div>
    </div>
    <div className="tour-gate"><Icon name="shield"/>
      <span><strong>Correctness gates run first</strong><small>5 business invariants · no double charge · no overselling</small></span>
    </div>
    <div className="tour-candidate"><span>C · Distributed</span><b>Fastest</b><s>Fails duplicate-payment</s><strong>Rejected</strong></div>
    <div className="tour-outcomes">
      <span className="tour-outcome good"><Icon name="check"/>Feasible → ranked</span>
      <span className="tour-outcome bad"><Icon name="close"/>Broken → rejected</span>
    </div>
  </div>;
}

function ChartVisual() {
  const points = [
    {x: 94, y: 74, on: false},
    {x: 132, y: 96, on: true},
    {x: 176, y: 88, on: false},
    {x: 214, y: 112, on: true},
    {x: 248, y: 104, on: false},
    {x: 286, y: 134, on: true},
    {x: 310, y: 124, on: false},
  ];
  return <>
    <svg viewBox="0 0 340 212" className="tour-chart" role="img"
      aria-label="Measured candidates plotted by latency and CPU. Three filled points form the Pareto front.">
      {[0, 1, 2, 3].map(index => <line key={index} className="grid" x1="46" x2="324" y1={36 + index * 42} y2={36 + index * 42}/>)}
      {[0, 1, 2, 3, 4].map(index => <line key={index} className="grid" x1={46 + index * 69.5} x2={46 + index * 69.5} y1="36" y2="162"/>)}
      <path className="axis" d="M46 22V162H330"/>
      <text x="8" y="30">p95</text>
      <text x="168" y="188">CPU seconds</text>
      <path className="pareto" d="M132 96 L214 112 L286 134"/>
      {points.map(point => <circle key={`${point.x}-${point.y}`} className={point.on ? 'on' : undefined} cx={point.x} cy={point.y} r="6"/>)}
    </svg>
    <div className="tour-legend"><span><i className="on"/>Pareto front</span><span><i/>Measured feasible</span></div>
    <div className="tour-evidence"><Icon name="book"/>
      <span><strong>Evidence-backed recommendation</strong><small>Seeds · artifacts · hashes · replay command</small></span>
    </div>
  </>;
}

const steps: Step[] = [
  {
    kicker: 'The decision',
    title: 'One server works. Then the traffic arrives.',
    lede: 'At 100 customers, one backend and one database are enough. At 10,000, requests time out, the database saturates and payments fail. Scaling adds capacity; it does not tell you which architecture is right.',
    points: [
      {icon: 'check', text: 'Vertical scaling makes one machine bigger; it eventually reaches a limit.'},
      {icon: 'check', text: 'Horizontal scaling adds servers, but the database, queue and cost still need decisions.'},
      {icon: 'check', text: 'AWS, Kubernetes, Redis and load tests provide the pieces — not the answer.'},
    ],
    visual: <GrowthVisual/>,
  },
  {
    kicker: 'Positioning',
    title: 'A lab, not a replacement for your stack.',
    lede: 'DARWIN sits alongside AWS, Kubernetes, Redis, Locust and Prometheus. It coordinates them into one experiment: generate alternatives, run traffic, inject failures, verify business rules, then search.',
    points: [
      {icon: 'check', text: 'It does not replace infrastructure, caching, monitoring or load generation.'},
      {icon: 'check', text: 'It did not invent load testing, fault injection or architecture optimization.'},
      {icon: 'check', text: 'The differentiator is the combined workflow with correctness gates and NSGA-II search.'},
    ],
    visual: <ToolsVisual/>,
  },
  {
    kicker: 'Step 1 · Understand',
    title: 'Understand the backend before changing it.',
    lede: 'Connect a pinned public repository, or use the controlled checkout lab. DARWIN maps the services, data stores, cache and workers, and separates proven facts from guesses.',
    points: [
      {icon: 'check', text: 'One exact commit is resolved before anything is downloaded.'},
      {icon: 'check', text: 'The architecture map is source-backed, not a name match.'},
      {icon: 'check', text: 'Unsupported features stay unsupported instead of being invented.'},
    ],
    visual: <MapVisual/>,
  },
  {
    kicker: 'Steps 2–3 · Generate and test',
    title: 'Build alternatives. Run them at 100, 1,000 and 5,000 users.',
    lede: 'A candidate is a deployable configuration, not a diagram. The checkout lab varies replicas, cache TTL, notification delivery and retry policy. Each candidate is deployed and measured under simulated traffic.',
    points: [
      {icon: 'check', text: 'One, two or three API replicas behind the gateway.'},
      {icon: 'check', text: 'Catalog cache off, 10 seconds or 30 seconds.'},
      {icon: 'check', text: 'Notifications sent inline or queued to a worker.'},
      {icon: 'check', text: 'Retries disabled, or idempotent only in the safe path.'},
    ],
    visual: <AlternativesVisual/>,
  },
  {
    kicker: 'Steps 4–5 · Break and verify',
    title: 'The fastest configuration can still lose.',
    lede: 'DARWIN injects database delays, service outages, payment timeouts and duplicate requests. Five invariants run before performance counts. A configuration that double-charges a customer is rejected, however fast it is.',
    points: [
      {icon: 'shield', text: 'No duplicate payment for one request key.'},
      {icon: 'shield', text: 'No overselling; confirmed orders were paid.'},
      {icon: 'shield', text: 'Replayed requests add no extra business effects.'},
    ],
    visual: <GateVisual/>,
  },
  {
    kicker: 'Step 6 · Evolve',
    title: 'Search the trade-offs. Keep the evidence.',
    lede: 'NSGA-II, random search and hill climbing propose configurations. The simulator screens them cheaply; only promoted candidates are measured. Pareto ranking weighs latency, CPU time and recovery — after correctness gates remove failures.',
    points: [
      {icon: 'experiments', text: 'Simulated results are labelled NOT_MEASURED and can never win.'},
      {icon: 'search', text: 'Pareto ranking across latency, CPU time and recovery.'},
      {icon: 'book', text: 'Lineage, seeds and per-run evidence stay attached to each candidate.'},
      {icon: 'project', text: 'Today: a controlled checkout lab plus two public backends. General-purpose repository optimization is the roadmap, not shipped functionality.'},
    ],
    visual: <ChartVisual/>,
  },
];

export function Tour({open, onClose}: {open: boolean; onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [step, setStep] = useState(0);
  const last = steps.length - 1;
  const current = steps[step];

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) {
      setStep(0);
      node.showModal();
    } else if (!open && node.open) {
      node.close();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => heading.current?.focus({preventScroll: true}));
    return () => cancelAnimationFrame(frame);
  }, [open, step]);

  function go(next: number) {
    setStep(Math.max(0, Math.min(last, next)));
  }

  return <dialog ref={dialog} className="tour" aria-labelledby="tour-title" onClose={onClose}
    onClick={event => {
      if ((event.target as HTMLElement).closest('a[href^="#"]')) dialog.current?.close();
    }}
    onKeyDown={event => {
      if (event.key === 'ArrowRight') {event.preventDefault(); go(step + 1);}
      if (event.key === 'ArrowLeft') {event.preventDefault(); go(step - 1);}
    }}>
    <div className="tour-shell">
      <header className="tour-head">
        <span className="tour-brand"><BrandMark/><span>DARWIN</span><em>Product tour</em></span>
        <span className="tour-count">Step {step + 1} of {steps.length}</span>
        <Action variant="quiet" icon="close" onClick={() => dialog.current?.close()}>Close</Action>
      </header>
      <div className="tour-body">
        <div className="tour-copy" key={`copy-${step}`}>
          <p className="section-kicker">{current.kicker}</p>
          <h2 id="tour-title" ref={heading} tabIndex={-1}>{current.title}</h2>
          <p className="tour-lede">{current.lede}</p>
          {current.points.length > 0 && <ul className="tour-points">{current.points.map(point =>
            <li key={point.text}><Icon name={point.icon}/><span>{point.text}</span></li>)}</ul>}
        </div>
        <div className="tour-visual" key={`visual-${step}`}>{current.visual}</div>
      </div>
      <footer className="tour-foot">
        <div className="tour-dots" role="group" aria-label="Tour steps">
          {steps.map((item, index) => <button key={item.title} type="button"
            aria-label={`Step ${index + 1}: ${item.title}`} aria-current={index === step ? 'step' : undefined}
            onClick={() => go(index)}/>)}
        </div>
        <div className="tour-nav">
          <Action disabled={step === 0} onClick={() => go(step - 1)}>Back</Action>
          {step === last
            ? <Action variant="primary" icon="check" onClick={() => dialog.current?.close()}>Done</Action>
            : <Action variant="primary" icon="arrow" onClick={() => go(step + 1)}>Next</Action>}
        </div>
      </footer>
    </div>
  </dialog>;
}

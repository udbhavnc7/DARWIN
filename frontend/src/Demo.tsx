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

const pipeline = [
  ['configuration', 'Design', 'Pick supported controls'],
  ['experiments', 'Measure', 'Run load, time every request'],
  ['shield', 'Verify', 'Check five business invariants'],
  ['search', 'Evolve', 'Keep the best feasible tradeoff'],
] as const;

function PipelineVisual() {
  return <div className="tour-pipeline">
    {pipeline.map(([icon, title, detail]) => <div className="tour-step" key={title}>
      <span className="tour-step-icon"><Icon name={icon}/></span>
      <span><strong>{title}</strong><small>{detail}</small></span>
    </div>)}
    <div className="tour-evidence"><Icon name="book"/>
      <span><strong>Evidence record</strong><small>Seeds · artifacts · hashes · replay commands</small></span>
    </div>
  </div>;
}

function StackVisual() {
  return <div className="tour-stack">
    <span className="tour-node">Gateway</span>
    <span className="tour-connector"/>
    <span className="tour-node accent">Checkout API 1</span>
    <span className="tour-connector"/>
    <div className="tour-stack-row"><span className="tour-node">Inventory</span><span className="tour-node">Mock payment</span></div>
    <span className="tour-connector"/>
    <div className="tour-stack-row"><span className="tour-node">PostgreSQL</span><span className="tour-node muted-node">Redis · optional</span></div>
    <div className="tour-controls">
      <span className="tour-control"><b>1–3</b> replicas</span>
      <span className="tour-control"><b>0 / 10 / 30 s</b> cache</span>
      <span className="tour-control"><b>Sync / queued</b> alerts</span>
      <span className="tour-control"><b>Idempotent</b> retries</span>
    </div>
  </div>;
}

function GateVisual() {
  return <div className="tour-gates">
    <div className="tour-test-group"><span className="tour-test-label">Workloads</span>
      <div className="tour-chips"><span className="tour-chip">Normal traffic</span><span className="tour-chip">Flash sale</span><span className="tour-chip">Checkout heavy</span></div>
    </div>
    <div className="tour-test-group"><span className="tour-test-label">Faults</span>
      <div className="tour-chips"><span className="tour-chip fault">DB delay</span><span className="tour-chip fault">Service outage</span><span className="tour-chip fault">Duplicate delivery</span></div>
    </div>
    <div className="tour-gate"><Icon name="shield"/>
      <span><strong>Correctness gate</strong><small>5 invariants · 3 isolated repetitions</small></span>
    </div>
    <div className="tour-outcomes">
      <span className="tour-outcome good"><Icon name="check"/>Feasible → ranked</span>
      <span className="tour-outcome bad"><Icon name="close"/>Rejected → evidence</span>
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
  </>;
}

const starts = [
  {page: 'configuration', icon: 'configuration', title: 'Architecture', detail: 'Shape replicas, cache, notifications, retries.'},
  {page: 'experiments', icon: 'experiments', title: 'Experiments', detail: 'Measure performance or inject failures.'},
  {page: 'search', icon: 'search', title: 'Search', detail: 'Compare candidates with measured evidence.'},
  {page: 'shop', icon: 'shop', title: 'Demo shop', detail: 'Place a checkout and resend the same request.'},
] as const;

function StartVisual() {
  return <div className="tour-start">{starts.map(item => <a className="tour-start-link" href={`#${item.page}`} key={item.page}>
    <Icon name={item.icon}/>
    <span><strong>{item.title}</strong><small>{item.detail}</small></span>
    <Icon name="arrow"/>
  </a>)}</div>;
}

const steps: Step[] = [
  {
    kicker: 'The big picture',
    title: 'A lab for backend decisions.',
    lede: 'DARWIN builds working versions of a checkout backend, runs them under realistic traffic and injected failures, then keeps the best configuration that still obeys the business rules.',
    points: [
      {icon: 'check', text: 'Every candidate is deployed and measured, not just drawn.'},
      {icon: 'check', text: 'Correctness gates override raw speed.'},
      {icon: 'check', text: 'Every result is reproducible from saved evidence.'},
    ],
    visual: <PipelineVisual/>,
  },
  {
    kicker: 'The system under test',
    title: 'One backend. Four controls.',
    lede: 'All candidates share the same checkout stack. Only four supported controls change between them, so comparisons stay fair.',
    points: [
      {icon: 'check', text: 'API replicas: one, two, or three behind the gateway.'},
      {icon: 'check', text: 'Catalog cache: off, 10 seconds, or 30 seconds with Redis.'},
      {icon: 'check', text: 'Notifications: sent during checkout or queued to a worker.'},
      {icon: 'check', text: 'Retries: none, or idempotent-only in the safe path.'},
    ],
    visual: <StackVisual/>,
  },
  {
    kicker: 'How it decides',
    title: 'Performance never outranks correctness.',
    lede: 'Each candidate faces three workloads and three fault classes. Five business invariants run against recorded state before any timing is allowed to count.',
    points: [
      {icon: 'shield', text: 'No duplicate payment for one request key.'},
      {icon: 'shield', text: 'No overselling; confirmed orders were paid.'},
      {icon: 'shield', text: 'Replayed requests add no extra business effects.'},
    ],
    visual: <GateVisual/>,
  },
  {
    kicker: 'How it searches',
    title: 'Propose. Screen. Prove.',
    lede: 'NSGA-II, random search, and hill climbing propose configurations. A calibrated simulator screens them cheaply; only promoted candidates get real measured runs.',
    points: [
      {icon: 'experiments', text: 'Simulated results are labeled and never presented as winners.'},
      {icon: 'search', text: 'Pareto ranking across latency, CPU time, and recovery.'},
      {icon: 'book', text: 'Lineage and per-repetition evidence stay attached to each candidate.'},
    ],
    visual: <ChartVisual/>,
  },
  {
    kicker: 'Where to start',
    title: 'Start with one run.',
    lede: 'Change a configuration, run a measured experiment, or inspect a saved search. The demo shop shows idempotency in action with a safe, simulated checkout.',
    points: [],
    visual: <StartVisual/>,
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

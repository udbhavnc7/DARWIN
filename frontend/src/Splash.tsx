import {useCallback, useEffect, useRef, useState} from 'react';
import {Action, Icon} from './Action';
import {BrandMark} from './Brand';
import SplashScene from './SplashScene';
import type {Theme} from './themes';

const gates = [
  {id: 'I-01', label: 'One payment effect per key'},
  {id: 'I-02', label: 'Stock reconciles with orders'},
  {id: 'I-03', label: 'Order carries payment evidence'},
  {id: 'I-04', label: 'Replay changes nothing'},
  {id: 'I-05', label: 'Delivery survives a restart'},
];

/**
 * The bench opens the way an instrument does: the gate stack assembles, a
 * measuring beam verifies each level, and the workspace takes over. It is a
 * short, skippable intro — never a gate in front of real work.
 */
export function Splash({theme, onDone}: {theme: Theme; onDone: () => void}) {
  const [exiting, setExiting] = useState(false);
  const leaving = useRef(false);
  const timer = useRef<number | null>(null);
  const skip = useRef<HTMLButtonElement>(null);

  const finish = useCallback(() => {
    if (leaving.current) return;
    leaving.current = true;
    if (timer.current !== null) window.clearTimeout(timer.current);
    setExiting(true);
    timer.current = window.setTimeout(onDone, 360);
  }, [onDone]);

  useEffect(() => {
    skip.current?.focus({preventScroll: true});
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    timer.current = window.setTimeout(finish, reduced ? 1600 : 3800);
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') finish();
    }
    window.addEventListener('keydown', onKey);
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      window.removeEventListener('keydown', onKey);
    };
  }, [finish]);

  return <div className="splash" role="dialog" aria-modal="true" aria-label="DARWIN bench calibration"
    data-exiting={exiting || undefined}>
    <header className="splash-top">
      <span className="splash-brand"><BrandMark/><span>DARWIN<small>Architecture lab</small></span></span>
      <span className="splash-filing" aria-hidden="true">Bench schematic / 01</span>
      <Action ref={skip} variant="quiet" icon="arrow" className="splash-skip" onClick={finish}>Skip to workspace</Action>
    </header>

    <div className="splash-body">
      <div className="splash-copy">
        <p className="splash-kicker"><span/>Calibration</p>
        <h1 className="splash-title">No claim<br/>without a <em>measurement.</em></h1>
        <p className="splash-lede">Four genome controls. Five invariant gates. One reproducible verdict — every architecture is measured before it is ranked.</p>
        <ol className="splash-gates" aria-label="Invariant gates verified by the lab">
          {gates.map((gate, index) => <li key={gate.id}
            style={{animationDelay: `${.62 + index * .33}s`}}>
            <span className="splash-gate-id">{gate.id}</span>
            <span className="splash-gate-label">{gate.label}</span>
            <Icon name="check"/>
          </li>)}
        </ol>
      </div>
      <div className="splash-rig">
        <span className="splash-rig-label">Gate stack · measured top-down</span>
        <span className="splash-rig-label">I-01 → I-05</span>
        <SplashScene theme={theme}/>
      </div>
    </div>

    <footer className="splash-bottom">
      <div>
        <div className="splash-track" aria-hidden="true"><span/></div>
        <p className="splash-note">Opening the workspace · Esc to skip</p>
      </div>
      <p className="splash-stamp"><Icon name="check"/> Bench ready</p>
    </footer>
  </div>;
}

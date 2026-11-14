import {useEffect, useRef} from 'react';
import {ArchitectureArt} from './ArchitectureArt';
import {Action} from './Action';
import type {Theme} from './themes';

export function BrandMark() {
  return <span className="brand-mark" aria-hidden="true"><i/><i/><i/><i/></span>;
}

export function Startup({dismiss, theme}: {dismiss: () => void; theme: Theme}) {
  const skip = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    skip.current?.focus({preventScroll: true});
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const timer = window.setTimeout(dismiss, reduced ? 500 : 2600);
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') dismiss();
    }
    window.addEventListener('keydown', onKey);
    return () => {clearTimeout(timer); window.removeEventListener('keydown', onKey);};
  }, [dismiss]);

  return <div className="startup" role="dialog" aria-modal="true" aria-label="DARWIN startup">
    <div className="startup-frame">
      <div className="startup-visual"><ArchitectureArt theme={theme} animate/></div>
      <div className="startup-content">
        <div className="startup-brand"><BrandMark/><span>DARWIN</span></div>
        <p className="startup-title">Backend<br/>architecture lab</p>
        <div className="startup-track" aria-hidden="true"><span/></div>
      </div>
    </div>
    <Action ref={skip} icon="arrow" className="startup-skip" onClick={dismiss}>Skip intro</Action>
  </div>;
}

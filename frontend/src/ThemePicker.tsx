import {useRef, type CSSProperties} from 'react';
import {themes, type ThemeId} from './themes';
import {Action, Icon} from './Action';

export function ThemePicker({theme, onChange, onReplay}: {
  theme: ThemeId; onChange: (id: ThemeId) => void; onReplay: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  return <>
    <button ref={trigger} className="theme-trigger" aria-haspopup="dialog" onClick={() => dialog.current?.showModal()}>
      <span className="theme-swatch current-swatch" aria-hidden="true"/><span><small>Theme</small><strong>{themes[theme].name}</strong></span>
      <Icon name="chevron" className="theme-chevron"/>
    </button>
    <dialog ref={dialog} className="theme-dialog" aria-labelledby="theme-title" onClose={() => trigger.current?.focus()}>
      <div className="section-title"><div className="panel-heading"><span className="section-kicker">Make it yours</span><h2 id="theme-title">Workspace appearance</h2></div><Action variant="quiet" icon="close" aria-label="Close appearance settings" onClick={() => dialog.current?.close()}>Close</Action></div>
      <p className="muted">A different palette. The same space to build.</p>
      <fieldset className="theme-grid">
        <legend className="visually-hidden">Color palette</legend>
        {(Object.keys(themes) as ThemeId[]).map(id => {
          const option = themes[id];
          return <label key={id} className="theme-option" style={{'--sample-bg': option.page, '--sample-accent': option.accent} as CSSProperties}>
            <span className="theme-preview" aria-hidden="true"><span className="theme-preview-rail"><i/><i/><i/></span><span className="theme-preview-content"><i/><span><i/><i/></span><b/></span></span>
            <span className="theme-option-caption"><span><strong>{option.name}</strong><small>{option.colors}</small></span><input aria-label={option.name} type="radio" name="workspace-theme" value={id} checked={theme === id} onChange={() => onChange(id)}/></span>
          </label>;
        })}
      </fieldset>
      <div className="theme-dialog-footer"><span className="muted"><Icon name="check"/> Saved on this device</span><Action variant="quiet" icon="play" onClick={() => {dialog.current?.close(); onReplay();}}>Replay intro</Action></div>
    </dialog>
  </>;
}

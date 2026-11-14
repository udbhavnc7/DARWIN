import type {ComponentProps} from 'react';

const paths = {
  overview: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  configuration: 'm12 3 9 5-9 5-9-5 9-5Z M3 12l9 5 9-5 M3 16l9 5 9-5',
  experiments: 'M3 3v18h18 M6 15h3l3-7 3 5h5',
  search: 'M10.5 17.5a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z M16 16l4.5 4.5',
  shop: 'M5 7h14l2 14H3L5 7Z M9 9V6a3 3 0 1 1 6 0v3',
  arrow: 'M4 12h15 M13 6l6 6-6 6',
  refresh: 'M20 4v5h-5 M19.5 9a8 8 0 0 0-13-3L4 9 M4 20v-5h5 M4.5 15a8 8 0 0 0 13 3L20 15',
  play: 'm8 5 12 7-12 7V5Z',
  stop: 'M6 6h12v12H6z',
  check: 'm5 12 4 4L19 6',
  close: 'm6 6 12 12 M18 6 6 18',
  download: 'M12 3v12 M7 10l5 5 5-5 M4 16v4h16v-4',
  chevron: 'm6 9 6 6 6-6',
  server: 'M4 3h16v7H4z M4 14h16v7H4z M8 6.5h.01 M8 17.5h.01 M12 6.5h5 M12 17.5h5',
  database: 'M20 6c0 2-3.6 3-8 3S4 8 4 6s3.6-3 8-3 8 1 8 3Z M4 6v12c0 2 3.6 3 8 3s8-1 8-3V6 M4 12c0 2 3.6 3 8 3s8-1 8-3',
  settings: 'M4 7h9 M17 7h3 M4 17h3 M11 17h9 M13 4v6 M7 14v6',
  shield: 'm12 3 8 3v6c0 4-5 7-8 9-3-2-8-5-8-9V6l8-3Z m-4 9 3 3 5-6',
  book: 'M12 5v15 M3 4c4-1 7 0 9 1 2-1 5-2 9-1v15c-4-1-7 0-9 1-2-1-5-2-9-1V4Z',
} as const;

export type IconName = keyof typeof paths;

export function Icon({name, className}: {name: IconName; className?: string}) {
  return <svg className={className ? `ui-icon ${className}` : 'ui-icon'} aria-hidden="true" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <path d={paths[name]}/>
  </svg>;
}

export function Action({variant = 'secondary', icon, pending, className = '', children, disabled, ref, ...props}:
  ComponentProps<'button'> & {variant?: 'primary' | 'secondary' | 'quiet' | 'danger'; icon?: IconName; pending?: boolean}) {
  return <button ref={ref} type="button" {...props} className={`action action-${variant} ${className}`} disabled={disabled || pending} aria-busy={pending || undefined}>
    {pending ? <span className="button-spinner" aria-hidden="true"/> : icon && <Icon name={icon}/>}
    <span>{children}</span>
  </button>;
}

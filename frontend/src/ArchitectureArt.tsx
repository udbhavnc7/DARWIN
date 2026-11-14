import {lazy, Suspense, type ComponentType} from 'react';
import type {Theme} from './themes';

const ArchitectureScene = lazy<ComponentType<{theme: Theme; animate: boolean}>>(
  () => import('./ArchitectureScene').catch(() => ({default: () => null})),
);

export function ArchitectureArt({theme, animate = false}: {theme: Theme; animate?: boolean}) {
  return <div className={`architecture-art${animate ? ' assembling' : ''}`} aria-hidden="true">
    <div className="art-fallback"><i/><i/><i/><i/><i/><i/></div>
    <Suspense fallback={null}><ArchitectureScene theme={theme} animate={animate}/></Suspense>
  </div>;
}

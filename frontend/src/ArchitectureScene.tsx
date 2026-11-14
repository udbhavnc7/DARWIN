import {useEffect, useRef} from 'react';
import {
  AmbientLight, BoxGeometry, BufferGeometry, Color, DirectionalLight, EdgesGeometry,
  Group, Line, LineBasicMaterial, LineSegments, Mesh, MeshBasicMaterial, MeshStandardMaterial,
  OrthographicCamera, Scene, Vector3, WebGLRenderer,
} from 'three';
import type {Theme} from './themes';

export default function ArchitectureScene({theme, animate}: {theme: Theme; animate: boolean}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!host.current) return;
    const container: HTMLDivElement = host.current;
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('webgl2', {alpha: true, antialias: true, powerPreference: 'low-power'});
    if (!context) return;

    let renderer: WebGLRenderer;
    try {renderer = new WebGLRenderer({canvas, context, alpha: true, antialias: true});} catch {return;}
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
    renderer.setClearColor(0, 0);

    const scene = new Scene();
    const camera = new OrthographicCamera(-4, 4, 3, -3, .1, 50);
    camera.position.set(8, 6, 9);
    camera.lookAt(0, .92, 0);
    const light = new DirectionalLight('#fffaf1', 2.1);
    light.position.set(-3, 7, 4);
    scene.add(light, new AmbientLight('#ffffff', 1.45));

    const system = new Group();
    scene.add(system);
    const box = new BoxGeometry(1, 1, 1);
    const edges = new EdgesGeometry(box);
    const palette = {
      base: new MeshStandardMaterial({color: theme.plate, roughness: .73}),
      model: new MeshStandardMaterial({color: theme.model, roughness: .61}),
      inset: new MeshStandardMaterial({color: new Color(theme.plate).lerp(new Color(theme.model), .46), roughness: .72}),
      signal: new MeshBasicMaterial({color: theme.accent}),
      line: new LineBasicMaterial({color: theme.trace, transparent: true, opacity: .44}),
    };
    const traces: BufferGeometry[] = [];
    function block(parent: Group, material: MeshStandardMaterial | MeshBasicMaterial,
                   size: [number, number, number], position: [number, number, number], outlined = true) {
      const mesh = new Mesh(box, material);
      mesh.position.set(...position);
      mesh.scale.set(...size);
      if (outlined) mesh.add(new LineSegments(edges, palette.line));
      parent.add(mesh);
    }

    block(system, palette.base, [6.2, .16, 4.5], [0, -.08, 0]);
    block(system, palette.inset, [6, .09, 4.3], [0, -.2, 0]);
    function path(points: [number, number][]) {
      const geometry = new BufferGeometry().setFromPoints(points.map(([x, z]) => new Vector3(x, .012, z)));
      traces.push(geometry);
      system.add(new Line(geometry, palette.line));
    }
    for (const z of [-1.94, -1.72, 1.68, 1.92]) path([[-2.8, z], [2.8, z]]);
    for (const x of [-2.77, -2.4, 2.4, 2.77]) path([[x, -1.94], [x, 1.92]]);

    const modules: {part: Group; height: number; delay: number}[] = [];
    function server(x: number, z: number, width: number, depth: number, y: number, height: number, delay: number) {
      const part = new Group();
      part.position.set(x, y, z);
      block(part, palette.model, [width, height, depth], [0, 0, 0]);
      block(part, palette.inset, [width * .82, .04, depth * .77], [0, height / 2 + .022, 0]);
      for (let i = 0; i < 3; i++) {
        block(part, palette.signal, [.075, .041, .035], [width * .3 - i * .14, .028, depth / 2], false);
      }
      system.add(part);
      modules.push({part, height: y, delay});
    }
    const targets = [-2.05, 0, 2.05];
    targets.forEach((x, index) => {
      path([[0, -.55], [0, .55], [x, .55], [x, 1.47]]);
      for (const z of [.6, .75, .9]) block(system, palette.signal, [.06, .012, .065], [x, .016, z], false);
      server(x, 1.26, 1.02, .76, .22, .4, index * .09);
    });
    server(0, -.68, 2.82, 1.86, .29, .48, .15);
    server(0, -.68, 2.5, 1.61, .92, .44, .24);
    server(0, -.68, 2.22, 1.34, 1.54, .38, .36);
    server(0, -.68, 1.84, 1.07, 2.08, .24, .46);

    const motion = animate && !matchMedia('(prefers-reduced-motion: reduce)').matches;
    const beginning = performance.now();
    function render(time: number) {
      const elapsed = (time - beginning) / 1000;
      system.rotation.y = motion ? -.22 * Math.max(0, 1 - elapsed / 1.15) ** 2 : 0;
      for (const {part, height, delay} of modules) {
        const remaining = motion ? 1 - Math.min(1, Math.max(0, (elapsed - delay) / .68)) : 0;
        part.position.y = height + remaining ** 3 * 1.15;
      }
      renderer.render(scene, camera);
      if (elapsed >= 1.2) renderer.setAnimationLoop(null);
    }

    function resize() {
      const {width, height} = container.getBoundingClientRect();
      if (!width || !height) return;
      const aspect = width / height;
      const halfHeight = Math.max(2.75, 4.1 / aspect);
      camera.left = -halfHeight * aspect;
      camera.right = halfHeight * aspect;
      camera.top = halfHeight;
      camera.bottom = -halfHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      render(performance.now());
    }

    function lost(event: Event) {
      event.preventDefault();
      renderer.setAnimationLoop(null);
      container.removeAttribute('data-rendered');
    }
    function restored() {resize(); container.dataset.rendered = 'true';}

    container.append(canvas);
    canvas.addEventListener('webglcontextlost', lost);
    canvas.addEventListener('webglcontextrestored', restored);
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    container.dataset.rendered = 'true';
    if (motion) renderer.setAnimationLoop(render);

    return () => {
      observer.disconnect();
      canvas.removeEventListener('webglcontextlost', lost);
      canvas.removeEventListener('webglcontextrestored', restored);
      renderer.setAnimationLoop(null);
      box.dispose(); edges.dispose();
      traces.forEach(geometry => geometry.dispose());
      Object.values(palette).forEach(material => material.dispose());
      renderer.dispose(); renderer.forceContextLoss();
      canvas.remove();
      container.removeAttribute('data-rendered');
    };
  }, [theme, animate]);

  return <div className="architecture-canvas" ref={host}/>;
}

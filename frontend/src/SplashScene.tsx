import {useEffect, useRef} from 'react';
import {
  AmbientLight, BoxGeometry, BufferGeometry, Color, CylinderGeometry, DirectionalLight, Group,
  LineBasicMaterial, LineSegments, Mesh, MeshBasicMaterial, MeshStandardMaterial, OrthographicCamera,
  Scene, Vector3, WebGLRenderer,
} from 'three';
import type {Theme} from './themes';

const gateLevels = [1.02, 1.62, 2.22, 2.82, 3.42];

/**
 * The calibration rig: five horizontal gate frames stacked over the test
 * deck, four genome controls on the bench, and a measuring beam that rises
 * through the stack. It is a schematic of how DARWIN works, not a status feed.
 */
export default function SplashScene({theme}: {theme: Theme}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = host.current;
    if (!container) return;
    const mount = container;
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('webgl2', {alpha: true, antialias: true, powerPreference: 'low-power'});
    if (!context) return;

    let renderer: WebGLRenderer;
    try {renderer = new WebGLRenderer({canvas, context, alpha: true, antialias: true});} catch {return;}
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.setClearColor(0, 0);

    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const accentColor = new Color(theme.accent);
    const traceColor = new Color(theme.trace);
    const latentColor = new Color(theme.trace).lerp(new Color(theme.plate), .42);

    const scene = new Scene();
    const camera = new OrthographicCamera(-4, 4, 3.2, -3.2, .1, 60);
    camera.position.set(8.2, 6.4, 10.4);
    camera.lookAt(0, 1.95, 0);
    const ambient = new AmbientLight('#ffffff', 1.55);
    const key = new DirectionalLight('#fffaf1', 2.05);
    scene.add(ambient, key);
    key.position.set(-4, 9, 6);
    scene.add(key);

    const rig = new Group();
    scene.add(rig);

    const box = new BoxGeometry(1, 1, 1);
    const cylinder = new CylinderGeometry(1, 1, 1, 20);
    const geometries: BufferGeometry[] = [box, cylinder];
    const materials: (MeshStandardMaterial | MeshBasicMaterial | LineBasicMaterial)[] = [];
    const standard = (color: string | Color, roughness = .68) => {
      const material = new MeshStandardMaterial({color, roughness});
      materials.push(material);
      return material;
    };
    const basic = (color: string | Color, opacity = 1) => {
      const material = new MeshBasicMaterial({color, transparent: true, opacity});
      materials.push(material);
      return material;
    };

    function block(parent: Group, material: MeshStandardMaterial | MeshBasicMaterial,
                   size: [number, number, number], position: [number, number, number]) {
      const mesh = new Mesh(box, material);
      mesh.scale.set(...size);
      mesh.position.set(...position);
      parent.add(mesh);
      return mesh;
    }

    const plate = standard(theme.plate, .84);
    const deck = standard(new Color(theme.plate).lerp(new Color(theme.model), .32), .8);
    const model = standard(theme.model, .54);
    const accent = basic(theme.accent);
    const trace = new LineBasicMaterial({color: theme.trace, transparent: true, opacity: .32});
    materials.push(trace);

    block(rig, plate, [6, .16, 4.6], [0, -.08, 0]);
    block(rig, deck, [5.78, .06, 4.38], [0, .006, 0]);

    // Graph-paper deck: the same measured field the workspace sits on.
    const gridPoints: Vector3[] = [];
    for (let x = -2.6; x <= 2.61; x += .52) gridPoints.push(new Vector3(x, .04, -2.1), new Vector3(x, .04, 2.1));
    for (let z = -2.1; z <= 2.11; z += .42) gridPoints.push(new Vector3(-2.65, .04, z), new Vector3(2.65, .04, z));
    const gridGeometry = new BufferGeometry().setFromPoints(gridPoints);
    geometries.push(gridGeometry);
    rig.add(new LineSegments(gridGeometry, trace));

    // Four genome controls, each at a different setting.
    const controls: {body: Mesh; cap: Mesh; marker: Mesh; height: number; delay: number}[] = [];
    const settings = [[-2.15, .34], [-.72, .47], [.72, .39], [2.15, .53]] as const;
    const ringMaterial = basic(theme.trace, .3);
    settings.forEach(([x, height], index) => {
      block(rig, ringMaterial, [.62, .03, .62], [x, .03, 1.55]);
      const body = new Mesh(cylinder, model);
      body.position.set(x, height / 2 + .04, 1.55);
      rig.add(body);
      const cap = new Mesh(cylinder, accent);
      cap.scale.set(.17, .045, .17);
      cap.position.set(x, height + .06, 1.55);
      rig.add(cap);
      const marker = block(rig, accent, [.06, .19, .02], [x, height * .58, 1.79]);
      controls.push({body, cap, marker, height, delay: .08 + index * .07});
    });

    // Gate frames, called out one level at a time by the beam.
    const gates: {frame: Group; material: MeshBasicMaterial; level: number}[] = [];
    const seamMaterial = new LineBasicMaterial({color: theme.trace, transparent: true, opacity: .16});
    materials.push(seamMaterial);
    gateLevels.forEach((level, index) => {
      const width = 3.05 - index * .12;
      const depth = 2.25 - index * .09;
      const material = basic(latentColor, .3);
      const frame = new Group();
      frame.position.y = level;
      block(frame, material, [width, .055, .055], [0, 0, depth / 2]);
      block(frame, material, [width, .055, .055], [0, 0, -depth / 2]);
      block(frame, material, [.055, .055, depth], [width / 2, 0, 0]);
      block(frame, material, [.055, .055, depth], [-width / 2, 0, 0]);
      for (const [x, z] of [[width / 2, depth / 2], [-width / 2, depth / 2], [width / 2, -depth / 2], [-width / 2, -depth / 2]]) {
        block(frame, material, [.1, .13, .1], [x, 0, z]);
      }
      rig.add(frame);
      gates.push({frame, material, level});
      const seams = new BufferGeometry().setFromPoints([
        new Vector3(width / 2, 0, depth / 2), new Vector3(width / 2, -.6, depth / 2),
        new Vector3(-width / 2, 0, depth / 2), new Vector3(-width / 2, -.6, depth / 2),
        new Vector3(width / 2, 0, -depth / 2), new Vector3(width / 2, -.6, -depth / 2),
        new Vector3(-width / 2, 0, -depth / 2), new Vector3(-width / 2, -.6, -depth / 2),
      ]);
      geometries.push(seams);
      rig.add(new LineSegments(seams, seamMaterial));
    });

    // The measuring rail turns the beam height into a readable scale.
    const rail = new Group();
    rig.add(rail);
    block(rail, basic(theme.trace, .45), [.035, 3.95, .035], [-2.68, 2.03, -2.06]);
    for (let y = .16; y <= 3.95; y += .32) {
      const long = gateLevels.some(level => Math.abs(level - y) < .17);
      block(rail, basic(theme.trace, long ? .8 : .35), [long ? .2 : .11, .015, .015], [-2.68 + (long ? .08 : .04), y, -2.06]);
    }
    const railMarker = block(rail, accent, [.26, .035, .09], [-2.68, .72, -2.06]);
    const controlMarker = block(rail, accent, [.09, .035, .26], [-2.68, .72, -2.06]);

    // Beam: a wide, faint plane with a bright edge, rising through the frames.
    const beamGroup = new Group();
    rig.add(beamGroup);
    const beamMaterial = basic(theme.accent, .09);
    beamMaterial.depthWrite = false;
    const beamEdge = basic(theme.accent, .9);
    block(beamGroup, beamMaterial, [4, .008, 3], [0, 0, 0]);
    block(beamGroup, beamEdge, [4, .012, .015], [0, 0, 1.5]);
    block(beamGroup, beamEdge, [4, .012, .015], [0, 0, -1.5]);
    block(beamGroup, beamEdge, [.015, .012, 3], [2, 0, 0]);
    block(beamGroup, beamEdge, [.015, .012, 3], [-2, 0, 0]);
    beamGroup.visible = false;

    const clamp01 = (value: number) => Math.min(1, Math.max(0, value));
    const easeOut = (value: number) => 1 - (1 - clamp01(value)) ** 3;
    const easeInOut = (value: number) => {
      const t = clamp01(value);
      return t < .5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2;
    };

    function settle() {
      for (const control of controls) {
        control.body.scale.set(.24, control.height, .24);
        control.body.position.y = control.height / 2 + .04;
        control.cap.scale.set(.17, .045, .17);
        control.cap.position.y = control.height + .06;
        control.marker.position.y = control.height * .58;
      }
      for (const gate of gates) {
        gate.frame.position.y = gate.level;
        gate.frame.scale.setScalar(1);
        gate.material.color.copy(accentColor);
        gate.material.opacity = 1;
      }
      rig.rotation.y = 0;
    }

    function resize() {
      const {width, height} = mount.getBoundingClientRect();
      if (!width || !height) return;
      const aspect = width / height;
      const halfHeight = Math.max(3, 4.15 / aspect);
      camera.left = -halfHeight * aspect;
      camera.right = halfHeight * aspect;
      camera.top = halfHeight;
      camera.bottom = -halfHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      if (reduced) {settle(); renderer.render(scene, camera);}
    }

    const started = performance.now();
    function render(now: number) {
      const elapsed = (now - started) / 1000;
      rig.rotation.y = -.34 * (1 - easeOut(elapsed / 1.5)) + .014 * Math.sin(elapsed * .62);

      for (const control of controls) {
        const rise = easeOut((elapsed - control.delay) / .6);
        const height = Math.max(.02, control.height * rise);
        control.body.scale.set(.24, height, .24);
        control.body.position.y = height / 2 + .04;
        control.cap.scale.set(.17, .045, .17);
        control.cap.position.y = height + .06;
        control.marker.position.y = height * .58;
      }

      for (let index = 0; index < gates.length; index++) {
        const gate = gates[index];
        const drop = easeOut((elapsed - .12 - index * .07) / .62);
        gate.frame.position.y = gate.level + (1 - drop) * 1.05;
        const level = beamHeight(elapsed);
        const lit = clamp01((level - (gate.level - .18)) / .34);
        gate.material.color.lerpColors(latentColor, accentColor, lit);
        gate.material.opacity = .3 + .7 * lit;
        gate.frame.scale.setScalar(1 + .045 * Math.sin(Math.PI * lit));
      }

      const level = beamHeight(elapsed);
      beamGroup.position.y = level;
      railMarker.position.y = level;
      controlMarker.position.y = level;
      const beamFade = clamp01((elapsed - .35) / .35) * (1 - clamp01((elapsed - 2.72) / .3));
      beamGroup.visible = beamFade > .01;
      beamMaterial.opacity = .09 * beamFade;
      beamEdge.opacity = .9 * beamFade;

      renderer.render(scene, camera);
      if (elapsed >= 3.6) renderer.setAnimationLoop(null);
    }

    function beamHeight(elapsed: number) {
      const travel = easeInOut((elapsed - .62) / 2.0);
      return .72 + travel * 3.18;
    }

    function lost(event: Event) {
      event.preventDefault();
      renderer.setAnimationLoop(null);
      mount.removeAttribute('data-rendered');
    }
    function restored() {resize(); mount.dataset.rendered = 'true';}

    container.append(canvas);
    canvas.addEventListener('webglcontextlost', lost);
    canvas.addEventListener('webglcontextrestored', restored);
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    container.dataset.rendered = 'true';
    if (reduced) {settle(); renderer.render(scene, camera);}
    else renderer.setAnimationLoop(render);

    return () => {
      observer.disconnect();
      canvas.removeEventListener('webglcontextlost', lost);
      canvas.removeEventListener('webglcontextrestored', restored);
      renderer.setAnimationLoop(null);
      geometries.forEach(geometry => geometry.dispose());
      materials.forEach(material => material.dispose());
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
      mount.removeAttribute('data-rendered');
    };
  }, [theme]);

  return <div className="splash-canvas" ref={host} aria-hidden="true"/>;
}

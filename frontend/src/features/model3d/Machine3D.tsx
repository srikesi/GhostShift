import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Component, ComponentHealth, Severity } from "../../api/types";
import { MODELS, type Prim } from "./models";
import "./model3d.css";

interface Props {
  drawing: string;
  components: Component[];
  health: Record<string, ComponentHealth | undefined>;
  affectedId: string | null;
  selectedId: string | null;
  onSelect: (componentId: string) => void;
  /** Called when WebGL is not available, so the page can show the 2D drawing instead. */
  onUnsupported: () => void;
  /** Word for what happens to the flagged part, e.g. "Replace" or "Clean". */
  actionVerb?: string;
}

const FILL: Record<Severity, string> = { normal: "#efede7", watch: "#f0d39a", warning: "#e3a446", critical: "#d4625a" };
const EDGE = "#474c53";
const EDGE_AFFECTED = "#a65f00";
const EDGE_SELECTED = "#1d2024";

interface PartEntry {
  componentId: string;
  meshes: THREE.Mesh[];
  edges: THREE.LineSegments[];
  center: THREE.Vector3;
}

function geometry(p: Prim): THREE.BufferGeometry {
  if (p.kind === "box") return new THREE.BoxGeometry(...p.size);
  if (p.kind === "cyl") return new THREE.CylinderGeometry(p.rTop ?? p.r, p.r, p.h, 40);
  return new THREE.TorusGeometry(p.r, p.tube, 16, 48);
}

function place(obj: THREE.Object3D, p: Prim) {
  obj.position.set(...p.pos);
  if (p.rot) obj.rotation.set(...p.rot);
}

/** Tappable 3D model: drag to rotate, pinch to zoom, tap a part to select it. Renders only on change. */
export default function Machine3D({
  drawing,
  components,
  health,
  affectedId,
  selectedId,
  onSelect,
  onUnsupported,
  actionVerb = "Replace",
}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const api = useRef<{ parts: Map<string, PartEntry>; render: () => void } | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Build the scene once per drawing.
  useEffect(() => {
    const model = MODELS[drawing];
    const el = host.current;
    if (!model || !el) {
      onUnsupported();
      return;
    }
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      onUnsupported();
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight("#ffffff", "#bdb6a8", 2.2));
    const sun = new THREE.DirectionalLight("#ffffff", 1.6);
    sun.position.set(4, 7, 5);
    scene.add(sun);

    const floor = new THREE.Mesh(new THREE.CircleGeometry(3.6, 64), new THREE.MeshStandardMaterial({ color: "#e6e2da" }));
    floor.rotation.x = -Math.PI / 2;
    scene.add(floor);

    const addSolid = (p: Prim, color: string, edgeColor: string) => {
      const geo = geometry(p);
      const see = p.opacity !== undefined && p.opacity < 1;
      const mesh = new THREE.Mesh(
        geo,
        new THREE.MeshStandardMaterial({
          color: p.color ?? color,
          roughness: 0.75,
          metalness: 0.05,
          transparent: see,
          opacity: p.opacity ?? 1,
          depthWrite: !see,
        }),
      );
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geo, 25),
        new THREE.LineBasicMaterial({ color: edgeColor, transparent: see, opacity: see ? 0.35 : 1 }),
      );
      place(mesh, p);
      place(edges, p);
      scene.add(mesh, edges);
      return { mesh, edges };
    };

    model.structure.forEach((p) => addSolid(p, "#d8d4cb", "#8a8f94"));
    const frameLines: THREE.LineSegments[] = [];
    model.frames?.forEach((p) => {
      const lines = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry(p)),
        new THREE.LineBasicMaterial({ color: "#b9b3a6", transparent: true, opacity: 0.6 }),
      );
      place(lines, p);
      scene.add(lines);
      frameLines.push(lines);
    });

    const parts = new Map<string, PartEntry>();
    for (const c of components) {
      const prims = model.parts[c.visualization_id];
      if (!prims) continue;
      const entry: PartEntry = { componentId: c.id, meshes: [], edges: [], center: new THREE.Vector3() };
      const box = new THREE.Box3();
      for (const p of prims) {
        const { mesh, edges } = addSolid(p, FILL.normal, EDGE);
        mesh.userData.componentId = c.id;
        mesh.updateMatrixWorld();
        box.expandByObject(mesh);
        entry.meshes.push(mesh);
        entry.edges.push(edges);
      }
      box.getCenter(entry.center);
      parts.set(c.id, entry);
    }

    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.enableDamping = false;
    controls.maxPolarAngle = Math.PI * 0.49;

    // Fit the whole unit in view from the model's preferred direction, for any screen shape.
    // Fit to the unit (its cabinet/enclosure outline and parts), not the floor around it.
    const bounds = new THREE.Box3();
    frameLines.forEach((l) => bounds.expandByObject(l));
    parts.forEach((p) => p.meshes.forEach((m) => bounds.expandByObject(m)));
    const sphere = bounds.getBoundingSphere(new THREE.Sphere());
    const direction = new THREE.Vector3(...model.camera).sub(new THREE.Vector3(...model.target)).normalize();
    const fit = () => {
      const vFov = THREE.MathUtils.degToRad(camera.fov);
      const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
      const distance = (sphere.radius / Math.sin(Math.min(vFov, hFov) / 2)) * 0.92;
      controls.target.copy(sphere.center);
      camera.position.copy(sphere.center).addScaledVector(direction, distance);
      controls.minDistance = distance * 0.45;
      controls.maxDistance = distance * 1.6;
      controls.update();
    };

    const v = new THREE.Vector3();
    const render = () => {
      renderer.render(scene, camera);
      const label = labelRef.current;
      const target = label?.dataset.componentId ? parts.get(label.dataset.componentId) : undefined;
      if (label && target) {
        v.copy(target.center).project(camera);
        const w = renderer.domElement.clientWidth;
        const h = renderer.domElement.clientHeight;
        label.style.transform = `translate(${((v.x + 1) / 2) * w}px, ${((1 - v.y) / 2) * h}px)`;
        label.style.visibility = v.z < 1 ? "visible" : "hidden";
      }
    };
    controls.addEventListener("change", render);

    const resize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = `${w}px`;
      renderer.domElement.style.height = `${h}px`;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      fit();
      render();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    // Tap (not drag) selects a part.
    const ray = new THREE.Raycaster();
    let down: { x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => (down = { x: e.clientX, y: e.clientY });
    const onUp = (e: PointerEvent) => {
      if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) return;
      const r = renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
      const hit = ray.intersectObjects([...parts.values()].flatMap((p) => p.meshes))[0];
      if (hit) onSelectRef.current(hit.object.userData.componentId);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    api.current = { parts, render };
    return () => {
      ro.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments) {
          o.geometry.dispose();
          (o.material as THREE.Material).dispose();
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
      api.current = null;
    };
    // Components are fixed per machine; rebuild only when the drawing changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawing]);

  // Recolor when status, the flagged part or the selection changes.
  const labelFor = selectedId ?? affectedId;
  useEffect(() => {
    const a = api.current;
    if (!a) return;
    for (const [id, entry] of a.parts) {
      const status = health[id]?.status ?? "normal";
      const edge = id === selectedId ? EDGE_SELECTED : id === affectedId ? EDGE_AFFECTED : EDGE;
      entry.meshes.forEach((m) => (m.material as THREE.MeshStandardMaterial).color.set(FILL[status]));
      entry.edges.forEach((l) => (l.material as THREE.LineBasicMaterial).color.set(edge));
    }
    if (labelRef.current) labelRef.current.dataset.componentId = labelFor ?? "";
    a.render();
  }, [health, affectedId, selectedId, labelFor]);

  const label = components.find((c) => c.id === labelFor);
  return (
    <div className="machine3d" ref={host} role="img" aria-label={`3D model${label ? `; ${label.name} highlighted` : ""}`}>
      <div ref={labelRef} className={`m3d-label ${labelFor === affectedId ? "affected" : ""}`} aria-hidden>
        <span>{label ? (labelFor === affectedId ? `${actionVerb}: ${label.name}` : label.name) : ""}</span>
      </div>
    </div>
  );
}

import { lazy, Suspense, useState } from "react";
import type { Component, ComponentHealth } from "../../api/types";
import { AssemblyDiagram } from "../assembly/AssemblyDiagram";
import { MODELS } from "../model3d/models";
import { hasPhoto, PhotoGallery } from "./MachinePhoto";
import "./machine.css";

// three.js loads only when the 3D view is opened.
const Machine3D = lazy(() => import("../model3d/Machine3D"));

type View = "drawing" | "3d" | "photo";

interface Props {
  drawing: string;
  components: Component[];
  health: Record<string, ComponentHealth | undefined>;
  affectedId: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  actionVerb?: string;
}

/** The machine as a drawing, a 3D model or a real photo. */
export function PartsViews({ drawing, components, health, affectedId, selectedId, onSelect, actionVerb }: Props) {
  const [view, setView] = useState<View>("drawing");
  const [no3d, setNo3d] = useState(false);
  const has3d = drawing in MODELS && !no3d;
  const views: { id: View; label: string }[] = [
    { id: "drawing", label: "Drawing" },
    ...(has3d ? [{ id: "3d" as View, label: "3D" }] : []),
    ...(hasPhoto(drawing) ? [{ id: "photo" as View, label: "Photo" }] : []),
  ];
  const current = views.some((v) => v.id === view) ? view : "drawing";
  return (
    <div className="parts-views">
      <div className="seg" role="group" aria-label="Machine view">
        {views.map((v) => (
          <button key={v.id} aria-pressed={current === v.id} onClick={() => setView(v.id)}>
            {v.label}
          </button>
        ))}
      </div>
      {current === "drawing" && (
        <AssemblyDiagram
          drawing={drawing}
          components={components}
          health={health}
          affectedId={affectedId}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      )}
      {current === "3d" && (
        <Suspense fallback={<div className="machine3d" />}>
          <Machine3D
            drawing={drawing}
            components={components}
            health={health}
            affectedId={affectedId}
            selectedId={selectedId}
            onSelect={onSelect}
            onUnsupported={() => setNo3d(true)}
            actionVerb={actionVerb}
          />
        </Suspense>
      )}
      {current === "photo" && <PhotoGallery drawing={drawing} />}
    </div>
  );
}

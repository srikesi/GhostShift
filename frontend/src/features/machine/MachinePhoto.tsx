import "./machine.css";

interface Photo {
  src: string;
  alt: string;
  caption: string;
}

/** Real photos of similar equipment (see public/images/CREDITS.md). They are references, not photos of this unit. */
const PHOTOS: Record<string, Photo[]> = {
  rack: [
    {
      src: "/images/mainframe-front.jpg",
      alt: "Two tall black mainframe cabinets with angular doors and blue vents",
      caption: "Front of a mainframe cabinet (IBM Z-class)",
    },
    {
      src: "/images/server-rack-rear.jpg",
      alt: "Rear of a server rack with network cables, power supplies and fans",
      caption: "Rear of a server rack: cables, power supplies and fans",
    },
  ],
  chiller: [
    {
      src: "/images/chiller-air-cooled.jpg",
      alt: "An air-cooled chiller on a rooftop frame, with compressors behind a mesh guard",
      caption: "An air-cooled chiller: compressors below, condenser coils and fans above",
    },
  ],
};

export const hasPhoto = (drawing: string) => drawing in PHOTOS;

/** Small photo for headers and the phone page. */
export function MachineThumb({ drawing, wide = false }: { drawing: string; wide?: boolean }) {
  const p = PHOTOS[drawing]?.[0];
  if (!p) return null;
  return (
    <figure className={`machine-thumb ${wide ? "wide" : ""}`}>
      <img src={p.src} alt={p.alt} loading="lazy" />
      {wide && <figcaption className="xs muted">{p.caption}. Reference photo of similar equipment.</figcaption>}
    </figure>
  );
}

export function PhotoGallery({ drawing }: { drawing: string }) {
  const photos = PHOTOS[drawing];
  if (!photos) return <p className="small muted">No photo for this machine.</p>;
  return (
    <div className="photo-gallery">
      <div className="photo-grid">
        {photos.map((p) => (
          <figure key={p.src}>
            <img src={p.src} alt={p.alt} loading="lazy" />
            <figcaption className="xs muted">{p.caption}</figcaption>
          </figure>
        ))}
      </div>
      <p className="xs muted">
        Reference photos of similar equipment, not this exact unit.
      </p>
    </div>
  );
}

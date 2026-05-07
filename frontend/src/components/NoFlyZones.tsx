import { Polygon, Popup, Tooltip } from "react-leaflet";
import { useFleet } from "../context/FleetContext";

const STYLE = {
  color: "#dc2626",
  weight: 1.5,
  fillColor: "#dc2626",
  fillOpacity: 0.15,
};

const HOVER_STYLE = { ...STYLE, fillOpacity: 0.3 };

export function NoFlyZones() {
  const { state } = useFleet();
  if (state.zones.length === 0) return null;

  return (
    <>
      {state.zones.map((z) => (
        <Polygon
          key={z.name}
          positions={z.latlngs}
          pathOptions={STYLE}
          eventHandlers={{
            mouseover: (e) => e.target.setStyle(HOVER_STYLE),
            mouseout: (e) => e.target.setStyle(STYLE),
          }}
        >
          <Tooltip sticky>{z.name}</Tooltip>
          <Popup>
            <div className="text-sm">
              <div className="font-semibold">{z.name}</div>
              <div className="mt-1 text-xs text-red-700">No-Fly Zone</div>
            </div>
          </Popup>
        </Polygon>
      ))}
    </>
  );
}

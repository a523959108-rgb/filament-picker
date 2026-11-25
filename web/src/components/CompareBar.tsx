import type { JSX } from "react";
import { hexDelta, swatchBackgroundStyle } from "../color";
import type { WebEntry } from "../types";

function compareLabel(entry: WebEntry, brandNames: Map<string, string>): string {
  const brand = brandNames.get(entry.b) ?? entry.b;
  const color = entry.zh ?? entry.en ?? entry.id;
  return `${brand} ${color}`;
}

export function CompareBar(props: {
  entries: WebEntry[];
  brands?: { slug: string; name: string }[];
  onRemove: (id: string) => void;
  onClear?: () => void;
}): JSX.Element {
  const entries = props.entries.slice(0, 4);
  const brandNames = new Map((props.brands ?? []).map((brand) => [brand.slug, brand.name]));
  return (
    <aside className="compare-bar" aria-label="对比栏">
      <h2>对比</h2>
      <ul>
        {entries.map((entry) => (
          <li key={entry.id}>
            <span
              className={entry.hex.length === 0 ? "compare-dot swatch-empty" : "compare-dot"}
              style={swatchBackgroundStyle(entry.hex)}
              aria-hidden="true"
            />
            <span>{entry.zh ?? entry.en ?? entry.id}</span>
            <button type="button" onClick={() => props.onRemove(entry.id)}>移除</button>
          </li>
        ))}
      </ul>
      {entries.length > 1 && (
        <ul>
          {entries.flatMap((a, index) =>
            entries.slice(index + 1).map((b) => {
              const delta =
                a.hex[0] === undefined || b.hex[0] === undefined
                  ? "—"
                  : hexDelta(a.hex[0], b.hex[0]).toFixed(1);
              return (
                <li key={`${a.id}-${b.id}`}>
                  {compareLabel(a, brandNames)} / {compareLabel(b, brandNames)}: <span>{delta}</span>
                </li>
              );
            }),
          )}
        </ul>
      )}
      {props.onClear && (
        <button type="button" className="compare-clear" onClick={props.onClear}>
          清空
        </button>
      )}
    </aside>
  );
}

import type { JSX } from "react";
import { hexDelta } from "../color";
import type { WebEntry } from "../types";

export function CompareBar(props: { entries: WebEntry[]; onRemove: (id: string) => void }): JSX.Element {
  const entries = props.entries.slice(0, 4);
  return (
    <aside className="compare-bar" aria-label="对比栏">
      <h2>对比</h2>
      <ul>
        {entries.map((entry) => (
          <li key={entry.id}>
            <span>{entry.en ?? entry.zh ?? entry.id}</span>
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
                  {a.id} / {b.id}: <span>{delta}</span>
                </li>
              );
            }),
          )}
        </ul>
      )}
    </aside>
  );
}

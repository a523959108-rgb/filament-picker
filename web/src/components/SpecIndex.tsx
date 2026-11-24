import type { JSX } from "react";
import type { WebCatalog } from "../types";

function text(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "未知";
  return String(value);
}

function range(value: [number, number] | undefined): string {
  if (!value) return "未知";
  return `${value[0]}–${value[1]}`;
}

export function SpecIndex({ catalog }: { catalog: WebCatalog | null }): JSX.Element {
  if (catalog === null) return <p className="panel">目录加载中…</p>;
  return (
    <section className="panel spec-index">
      <h2>规格索引</h2>
      <p className="spec-note">以下来自色卡目录的参考值，不是仪器实测，也不是打印机当前温度。</p>
      <div className="spec-table-wrap">
        <table>
          <thead>
            <tr>
              <th>颜色</th>
              <th>材料</th>
              <th>喷嘴 °C</th>
              <th>热床 °C</th>
              <th>密度</th>
              <th>线径</th>
            </tr>
          </thead>
          <tbody>
            {catalog.entries.map((entry) => (
              <tr key={entry.id}>
                <td>{entry.zh ?? entry.en ?? entry.id}</td>
                <td>{entry.m || "未知"}</td>
                <td>{range(entry.print?.nozzle_c)}</td>
                <td>{range(entry.print?.bed_c)}</td>
                <td>{text(entry.print?.density_g_cm3)}</td>
                <td>{text(entry.print?.diameter_mm)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

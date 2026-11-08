import type { JSX } from "react";
import { formatNumber, formatTemperature, hasPrintParams } from "../print";
import type { PrintParams as PrintParamsData } from "../types";

export function PrintParams(props: { print: PrintParamsData | null | undefined }): JSX.Element | null {
  if (!hasPrintParams(props.print)) return null;
  const print = props.print;
  const nozzle = formatTemperature(print?.nozzle_c);
  const bed = formatTemperature(print?.bed_c);
  return (
    <section className="print-params" aria-label="打印参数">
      <h3>打印参数</h3>
      <dl className="detail-meta">
        {nozzle !== null && (
          <div>
            <dt>喷嘴温度</dt>
            <dd>{nozzle}</dd>
          </div>
        )}
        {bed !== null && (
          <div>
            <dt>热床温度</dt>
            <dd>{bed}</dd>
          </div>
        )}
        {print?.density_g_cm3 != null && (
          <div>
            <dt>密度</dt>
            <dd>{formatNumber(print.density_g_cm3)} g/cm³</dd>
          </div>
        )}
        {print?.diameter_mm != null && (
          <div>
            <dt>线径</dt>
            <dd>{formatNumber(print.diameter_mm)} mm</dd>
          </div>
        )}
        {print?.orca_url && (
          <div>
            <dt>OrcaSlicer</dt>
            <dd>
              <a href={print.orca_url} target="_blank" rel="noreferrer">
                下载耗材预设
              </a>
            </dd>
          </div>
        )}
      </dl>
      <p className="print-credit">打印参数来自 Open Filament Database（MIT）。</p>
    </section>
  );
}

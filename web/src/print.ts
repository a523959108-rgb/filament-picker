import type { PrintParams } from "./types";

export function hasPrintParams(print: PrintParams | null | undefined): boolean {
  if (print == null) return false;
  return (
    print.nozzle_c != null ||
    print.bed_c != null ||
    print.density_g_cm3 != null ||
    print.diameter_mm != null ||
    Boolean(print.orca_url)
  );
}

export function formatTemperature(range: [number, number] | undefined): string | null {
  if (range == null) return null;
  const [min, max] = range;
  if (min === max) return `${formatNumber(min)} °C`;
  return `${formatNumber(min)}–${formatNumber(max)} °C`;
}

export function formatNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  return String(value);
}

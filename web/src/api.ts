import type { PlanResult } from "./types";

export async function postPlan(
  file: File,
  note: string,
  constraints?: Record<string, unknown>,
): Promise<PlanResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("note", note);
  if (constraints !== undefined) {
    form.append("constraints", JSON.stringify(constraints));
  }
  const response = await fetch("/api/plan", { method: "POST", body: form });
  if (response.status === 413) {
    throw new Error("图片超过 10MB");
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as PlanResult;
}

export function cardSrc(result: PlanResult): string | null {
  if (result.card_path === null) {
    return null;
  }
  const name = result.card_path.split(/[\\/]/).pop();
  return name === undefined || name === "" ? null : `/api/cards/${name}`;
}

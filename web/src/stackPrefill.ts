/** Hash prefill for #/stack?colors=RRGGBB,AABBCC&mode=RYBW. No image bytes. */

import { stackEntryHref } from "./config";
import type { StackLutMode } from "./stackJob";

const HEX = /^#?[0-9a-fA-F]{6}$/;

export function normalizeHex(value: string): string | null {
  const trimmed = value.trim();
  if (!HEX.test(trimmed)) return null;
  return `#${trimmed.replace(/^#/, "").toUpperCase()}`;
}

function hashQuery(hash: string): URLSearchParams {
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  return new URLSearchParams(query);
}

export function colorsFromHash(hash: string): string[] {
  const raw = hashQuery(hash).get("colors");
  if (raw === null || raw.trim() === "") return [];
  const colors: string[] = [];
  for (const part of raw.split(",")) {
    const hex = normalizeHex(part);
    if (hex === null || colors.includes(hex)) continue;
    colors.push(hex);
    if (colors.length >= 6) break;
  }
  return colors;
}

export function modeFromHash(hash: string): StackLutMode | null {
  const mode = (hashQuery(hash).get("mode") ?? "").toUpperCase();
  if (mode === "RYBW" || mode === "CMYW") return mode;
  return null;
}

/** In-app hash, or the stack subdomain when the visitor is on the main site. */
export function stackHrefForColors(hostname: string, colors: readonly string[]): string {
  const base = stackEntryHref(hostname);
  const hexes: string[] = [];
  for (const color of colors) {
    const hex = normalizeHex(color);
    if (hex === null || hexes.includes(hex)) continue;
    hexes.push(hex);
    if (hexes.length >= 6) break;
  }
  if (hexes.length === 0) return base;
  const query = `colors=${hexes.map((hex) => hex.slice(1)).join(",")}&mode=RYBW`;
  return `${base}?${query}`;
}

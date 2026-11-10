import { describe, expect, it } from "vitest";
import {
  MAIN_SITE_HOST,
  STACK_HASH,
  STACK_SITE_ORIGIN,
  defaultStackHash,
  isStackHost,
  stackEntryHref,
  stackHostFromOrigin,
} from "../config";

describe("stack subdomain entry", () => {
  it("points production main host to the stack subdomain", () => {
    expect(STACK_SITE_ORIGIN).toBe("https://stack.filament.ibaozi.com");
    expect(stackEntryHref(MAIN_SITE_HOST)).toBe(
      "https://stack.filament.ibaozi.com/#/stack",
    );
  });

  it("keeps in-app hash on localhost and on the stack host", () => {
    expect(stackEntryHref("localhost")).toBe(STACK_HASH);
    expect(stackEntryHref("127.0.0.1")).toBe(STACK_HASH);
    expect(stackEntryHref(stackHostFromOrigin())).toBe(STACK_HASH);
    expect(isStackHost("stack.filament.ibaozi.com")).toBe(true);
    expect(isStackHost(MAIN_SITE_HOST)).toBe(false);
  });

  it("defaults an empty hash on stack.* hosts to #/stack", () => {
    expect(defaultStackHash("stack.filament.ibaozi.com", "")).toBe("#/stack");
    expect(defaultStackHash("STACK.preview.internal", "#")).toBe("#/stack");
    expect(defaultStackHash("stack.filament.ibaozi.com", "#/plan")).toBeNull();
    expect(defaultStackHash("stack.filament.ibaozi.com", "#/cost")).toBeNull();
    expect(defaultStackHash("stack.filament.ibaozi.com", "#/")).toBeNull();
    expect(defaultStackHash("filament.ibaozi.com", "")).toBeNull();
    expect(defaultStackHash("localhost", "")).toBeNull();
    expect(defaultStackHash("notstack.example.com", "")).toBeNull();
  });
});

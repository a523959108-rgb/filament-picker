import { describe, expect, it } from "vitest";
import {
  buildJobPackageZip,
  buildStackJob,
  buildZip,
  crc32,
  type TrayPalette,
} from "../stackJob";

const palette: TrayPalette = {
  label: "青-品红-黄-白",
  lut_hints: ["bambulab_pla_basic_cmyw"],
  slots: [
    {
      slot: "C",
      name_zh: "青",
      name_en: "Cyan",
      catalog_id: "bambu-lab/pla-basic/cyan-10603",
      hex: "#0086D6",
      code: "10603",
      status: "pending_manual_confirm",
    },
  ],
};

describe("stackJob", () => {
  it("builds a local lumina job with CMYW metadata", () => {
    const job = buildStackJob({
      mode: "CMYW",
      palette,
      widthMm: 120,
      heightMm: 80,
      imageFilename: "sample.png",
      createdAt: "2026-11-09T16:56:46+09:00",
    });
    expect(job.kind).toBe("lumina-stack-job");
    expect(job.lut_mode).toBe("CMYW");
    expect(job.size_mm).toEqual({ width: 120, height: 80 });
    expect(job.slots[0]?.catalog_id).toBe("bambu-lab/pla-basic/cyan-10603");
    expect(job.engine.run_on).toBe("local-lumina");
    expect(job.smoke_preview).toBeNull();
  });

  it("builds a zip containing job.json and optional image", async () => {
    const job = buildStackJob({
      mode: "RYBW",
      palette,
      widthMm: 100,
      heightMm: 100,
      imageFilename: "photo.jpg",
      createdAt: "2026-11-09T16:56:46+09:00",
    });
    const image = new File([new Uint8Array([1, 2, 3, 4])], "photo.jpg", { type: "image/jpeg" });
    const zip = await buildJobPackageZip(job, image);
    expect(zip.type).toBe("application/zip");
    expect(zip.size).toBeGreaterThan(40);

    const empty = buildZip([{ name: "job.json", data: new TextEncoder().encode("{}\n") }]);
    const bytes = new Uint8Array(await empty.arrayBuffer());
    expect(bytes[0]).toBe(0x50);
    expect(bytes[1]).toBe(0x4b);
    expect(crc32(new TextEncoder().encode("hello"))).toBe(0x3610a686);
  });
});

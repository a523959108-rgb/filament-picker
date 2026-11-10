/** filament-picker adapter. Not upstream Lumina code.
 * ImageUpload.tsx calls useI18n(); this shim supplies the two strings it renders.
 */

const STRINGS: Record<string, string> = {
  upload_drag_hint: "拖拽图片到这里，或点击选择",
  common_preview_alt: "已选原图",
};

export function useI18n(): { t: (key: string) => string } {
  return {
    t: (key: string) => STRINGS[key] ?? key,
  };
}

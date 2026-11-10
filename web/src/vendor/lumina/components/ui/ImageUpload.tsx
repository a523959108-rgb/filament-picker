/* Lumina-Layers frontend/src/components/ui/ImageUpload.tsx
 * AGPL-3.0-only. Upstream commit b89af08226a88c9c9b3e2934ea1838c449923858.
 * filament-picker change: import the event types explicitly. This toolchain
 * uses the react-jsx runtime, which does not provide a global React namespace.
 */
import { useState, useRef, useCallback } from "react";
import type { ChangeEvent, DragEvent, KeyboardEvent } from "react";
import { useI18n } from "../../i18n/context";

interface ImageUploadProps {
  onFileSelect: (file: File) => void;
  accept: string;
  preview?: string;
  disabled?: boolean;
}

export default function ImageUpload({
  onFileSelect,
  accept,
  preview,
  disabled = false,
}: ImageUploadProps) {
  const { t } = useI18n();
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      if (disabled) return;
      setIsDragging(true);
    },
    [disabled],
  );

  const handleDragLeave = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      if (disabled) return;
      setIsDragging(false);
    },
    [disabled],
  );

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) {
        onFileSelect(file);
      }
    },
    [disabled, onFileSelect],
  );

  const handleClick = useCallback(() => {
    if (disabled) return;
    inputRef.current?.click();
  }, [disabled]);

  const handleChange = useCallback(
      (e: ChangeEvent<HTMLInputElement>) => {
      if (disabled) return;
      const file = e.target.files?.[0];
      if (file) {
        onFileSelect(file);
      }
    },
    [disabled, onFileSelect],
  );

  const borderClass = isDragging
    ? "border-blue-400 bg-blue-500/10"
    : "border-slate-300/80 border-dashed bg-[var(--surface-well)] dark:border-slate-700/80";

  return (
    <div
      data-local-file-drop-zone="true"
      role="button"
      aria-disabled={disabled}
      tabIndex={disabled ? -1 : 0}
      onClick={handleClick}
      onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => {
        if (e.key === "Enter" || e.key === " ") handleClick();
      }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex min-h-[140px] items-center justify-center rounded-[10px] border-2 px-4 py-5 text-center transition-colors ${borderClass} ${
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={handleChange}
        className="hidden"
      />
      {preview ? (
        <div
          data-testid="checkerboard-bg"
          className="rounded-[10px] bg-slate-100/80 p-3 dark:bg-slate-950/70"
          style={{
            backgroundImage:
              "linear-gradient(45deg, #e0e0e0 25%, transparent 25%), " +
              "linear-gradient(-45deg, #e0e0e0 25%, transparent 25%), " +
              "linear-gradient(45deg, transparent 75%, #e0e0e0 75%), " +
              "linear-gradient(-45deg, transparent 75%, #e0e0e0 75%)",
            backgroundSize: "16px 16px",
            backgroundPosition: "0 0, 0 8px, 8px -8px, -8px 0px",
          }}
        >
          <img
            src={preview}
            alt={t("common_preview_alt")}
            className="max-h-[180px] max-w-full rounded-[10px] object-contain"
          />
        </div>
      ) : (
        <span className="select-none text-sm font-medium text-slate-500 dark:text-slate-400">
          {t("upload_drag_hint")}
        </span>
      )}
    </div>
  );
}

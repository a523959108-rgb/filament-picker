import { useState } from "react";
import type { ChangeEvent, FormEvent, JSX } from "react";
import { cardSrc, postPlan } from "../api";
import type { PlanResult } from "../types";

export function PlanPage(props: { post?: typeof postPlan }): JSX.Element {
  const post = props.post ?? postPlan;
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [result, setResult] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
    setError(null);
    setResult(null);
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (file === null) {
      setError("请先选择图片");
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      setResult(await post(file, note));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSubmitting(false);
    }
  };

  const imageSource = result === null ? null : cardSrc(result);

  return (
    <section className="plan-page">
      <h1>图片配色（T24）</h1>
      <form onSubmit={onSubmit}>
        <label>
          图片
          <input type="file" accept="image/*" onChange={onFileChange} />
        </label>
        <label>
          备注
          <textarea
            placeholder="例：4 色，AMS 一台，只要拓竹 PLA"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? "配色中…" : "开始配色"}
        </button>
      </form>

      {error !== null && <p className="plan-error">{error}</p>}
      {result?.status === "error" && <p className="plan-error">{result.error?.message_zh}</p>}
      {result?.status === "ok" && (
        <section className="plan-result">
          <h2>配色方案（{result.palette.length} 色）</h2>
          {result.palette.map((target) => {
            const match = result.matches.find((item) => item.target_index === target.index);
            return (
              <article key={target.index} className="plan-target">
                <div className="plan-target-heading">
                  <span
                    className="plan-target-swatch"
                    style={{ backgroundColor: target.hex }}
                    aria-label={target.hex}
                  />
                  <span>{target.hex}</span>
                  <span>{Math.round(target.share * 100)}%</span>
                </div>
                {match !== undefined && (
                  <ul>
                    {match.picks.map((pick) => (
                      <li key={pick.id}>
                        <span>
                          {pick.brand_name} {pick.series_name} · {pick.name_display}
                        </span>{" "}
                        <span>ΔE {pick.delta_e.toFixed(1)}</span>{" "}
                        <span>{pick.label}</span>
                        {pick.is_approx && <span> 近似色</span>}{" "}
                        <a href={pick.url}>购买</a>
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            );
          })}
          {result.single_series_option !== null && (
            <p>
              同系列方案：{result.single_series_option.brand_name} {result.single_series_option.series_name}（最大 ΔE {result.single_series_option.max_delta_e.toFixed(1)}）
            </p>
          )}
          <p>需要 {result.slots_used} 个料槽</p>
          {imageSource !== null && <img src={imageSource} alt="配色卡" />}
        </section>
      )}
    </section>
  );
}

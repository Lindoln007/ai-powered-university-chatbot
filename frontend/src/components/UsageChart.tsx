import { useId, useState } from "react";

import type { UsagePoint } from "../api/client";
import { formatDay } from "../lib/format";

// Drawn at roughly its displayed size (the figure is capped at 56rem) so text stays ~12px.
const WIDTH = 880;
const HEIGHT = 260;
const PAD = { top: 16, right: 100, bottom: 28, left: 40 };

/**
 * Answered vs unanswered questions per day. Series differ by line style and
 * direct labels, not colour alone, and a data table is provided as a fallback.
 */
export function UsageChart({ points }: { points: UsagePoint[] }) {
  const titleId = useId();
  const [focusIndex, setFocusIndex] = useState<number | null>(null);

  if (points.length < 2) {
    return (
      <p className="chart-empty">
        {points.length === 1
          ? `${points[0].questions} question${points[0].questions === 1 ? "" : "s"} on ${formatDay(points[0].period)}. A trend appears after a second day of use.`
          : "No questions in this period yet."}
      </p>
    );
  }

  const max = Math.max(1, ...points.map((point) => point.questions));
  const niceMax = Math.max(2, Math.ceil(max / 4) * 4); // whole-number ticks at 0, half and max
  const innerW = WIDTH - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const x = (index: number) => PAD.left + (index / (points.length - 1)) * innerW;
  const y = (value: number) => PAD.top + innerH - (value / niceMax) * innerH;
  const line = (key: "answered" | "unanswered") =>
    points.map((point, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${y(point[key]).toFixed(1)}`).join(" ");
  const ticks = [0, niceMax / 2, niceMax];
  const labelEvery = Math.ceil(points.length / 6);
  const last = points[points.length - 1];
  // Direct labels sit to the right of each line's end, nudged apart if the values are close.
  let answeredY = y(last.answered) + 4;
  let unansweredY = y(last.unanswered) + 4;
  if (Math.abs(answeredY - unansweredY) < 16) {
    const middle = (answeredY + unansweredY) / 2;
    answeredY = middle - 8;
    unansweredY = middle + 8;
  }
  const focus = focusIndex === null ? null : points[focusIndex];

  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-labelledby={titleId}
        className="chart__svg"
        onMouseLeave={() => setFocusIndex(null)}
      >
        <title id={titleId}>
          Questions per day from {formatDay(points[0].period)} to {formatDay(last.period)}. Latest day: {last.answered} answered,{" "}
          {last.unanswered} unanswered.
        </title>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} className="chart__grid" />
            <text x={PAD.left - 8} y={y(tick) + 4} className="chart__axis" textAnchor="end">
              {tick}
            </text>
          </g>
        ))}
        {points.map((point, index) =>
          index % labelEvery === 0 || index === points.length - 1 ? (
            <text key={point.period} x={x(index)} y={HEIGHT - 8} className="chart__axis" textAnchor="middle">
              {formatDay(point.period)}
            </text>
          ) : null,
        )}
        <path d={line("answered")} className="chart__line chart__line--answered" />
        <path d={line("unanswered")} className="chart__line chart__line--unanswered" />
        <text x={x(points.length - 1) + 10} y={answeredY} className="chart__label">
          Answered
        </text>
        <text x={x(points.length - 1) + 10} y={unansweredY} className="chart__label chart__label--muted">
          Unanswered
        </text>
        {points.map((point, index) => (
          <rect
            key={point.period}
            x={x(index) - innerW / (points.length - 1) / 2}
            y={PAD.top}
            width={innerW / (points.length - 1)}
            height={innerH}
            fill="transparent"
            onMouseEnter={() => setFocusIndex(index)}
          />
        ))}
        {focus && focusIndex !== null && (
          <line x1={x(focusIndex)} x2={x(focusIndex)} y1={PAD.top} y2={PAD.top + innerH} className="chart__cursor" />
        )}
      </svg>
      <figcaption className="chart__caption" aria-live="polite">
        {focus
          ? `${formatDay(focus.period)}: ${focus.questions} questions, ${focus.answered} answered, ${focus.unanswered} unanswered`
          : "Hover over the chart for daily figures."}
      </figcaption>
      <details className="chart__table">
        <summary>Show as a table</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Questions</th>
              <th scope="col">Answered</th>
              <th scope="col">Unanswered</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.period}>
                <th scope="row">{formatDay(point.period)}</th>
                <td>{point.questions}</td>
                <td>{point.answered}</td>
                <td>{point.unanswered}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

import { jsPDF } from "jspdf";
import type { EvaluationRun } from "./types";

const BLUE = [0, 113, 227] as const;
const INK = [29, 29, 31] as const;
const MUTED = [134, 134, 139] as const;
const LINE = [232, 232, 237] as const;
const GREEN = [16, 185, 129] as const;
const RED = [239, 68, 68] as const;
const AMBER = [245, 158, 11] as const;
const SOFT_BLUE = [227, 240, 253] as const;
const SOFT_GREEN = [209, 250, 229] as const;
const SOFT_RED = [254, 226, 226] as const;
const BG = [245, 245, 247] as const;

type DimRollup = { id: string; score: number; passed: number; total: number };

function rgb(doc: jsPDF, c: readonly [number, number, number]) {
  doc.setTextColor(c[0], c[1], c[2]);
}

function fill(doc: jsPDF, c: readonly [number, number, number]) {
  doc.setFillColor(c[0], c[1], c[2]);
}

function stroke(doc: jsPDF, c: readonly [number, number, number]) {
  doc.setDrawColor(c[0], c[1], c[2]);
}

function scoreColor(score: number): readonly [number, number, number] {
  if (score >= 0.85) return GREEN;
  if (score >= 0.7) return BLUE;
  if (score >= 0.55) return AMBER;
  return RED;
}

function softScoreBg(score: number): readonly [number, number, number] {
  if (score >= 0.85) return SOFT_GREEN;
  if (score >= 0.55) return SOFT_BLUE;
  return SOFT_RED;
}

function ensureSpace(doc: jsPDF, y: number, need: number): number {
  const pageH = doc.internal.pageSize.getHeight();
  if (y + need > pageH - 18) {
    doc.addPage();
    drawFooter(doc);
    return 22;
  }
  return y;
}

function drawFooter(doc: jsPDF) {
  const w = doc.internal.pageSize.getWidth();
  const h = doc.internal.pageSize.getHeight();
  rgb(doc, MUTED);
  doc.setFontSize(8);
  doc.setFont("helvetica", "normal");
  doc.text("TCS AI Harness · Evaluation Lab", 14, h - 10);
  doc.text(`Page ${doc.getNumberOfPages()}`, w - 14, h - 10, { align: "right" });
}

function roundedRect(
  doc: jsPDF,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
  style: "F" | "FD" | "S" = "F",
) {
  doc.roundedRect(x, y, w, h, r, r, style);
}

function metricCard(
  doc: jsPDF,
  x: number,
  y: number,
  w: number,
  h: number,
  label: string,
  value: string,
  accent: readonly [number, number, number],
) {
  fill(doc, BG);
  stroke(doc, LINE);
  doc.setLineWidth(0.3);
  roundedRect(doc, x, y, w, h, 3, "FD");
  rgb(doc, MUTED);
  doc.setFontSize(7);
  doc.setFont("helvetica", "bold");
  doc.text(label.toUpperCase(), x + 4, y + 6);
  rgb(doc, accent);
  doc.setFontSize(16);
  doc.setFont("helvetica", "bold");
  doc.text(value, x + 4, y + 16);
}

function rollupDimensions(run: EvaluationRun): DimRollup[] {
  const map = new Map<string, { scoreSum: number; passed: number; total: number }>();
  for (const r of run.results) {
    const dims = (r.metrics?.dimensions ?? {}) as Record<
      string,
      { score?: number; passed?: boolean }
    >;
    for (const [id, payload] of Object.entries(dims)) {
      const cur = map.get(id) ?? { scoreSum: 0, passed: 0, total: 0 };
      cur.scoreSum += Number(payload.score ?? 0);
      cur.total += 1;
      if (payload.passed) cur.passed += 1;
      map.set(id, cur);
    }
  }
  return [...map.entries()].map(([id, v]) => ({
    id,
    score: v.total ? v.scoreSum / v.total : 0,
    passed: v.passed,
    total: v.total,
  }));
}

export function exportEvaluationPdf(run: EvaluationRun, agentName?: string) {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const margin = 14;
  const contentW = pageW - margin * 2;
  const rollup = rollupDimensions(run);
  const passedCases = run.results.filter((r) => r.passed).length;
  const agg = run.aggregate_score ?? 0;

  // —— Hero header ——
  fill(doc, BLUE);
  doc.rect(0, 0, pageW, 42, "F");
  // soft accent band
  fill(doc, [0, 88, 174]);
  doc.rect(0, 36, pageW, 6, "F");

  doc.setTextColor(255, 255, 255);
  doc.setFontSize(9);
  doc.setFont("helvetica", "bold");
  doc.text("TCS AI HARNESS  ·  EVALUATION LAB", margin, 12);
  doc.setFontSize(22);
  doc.setFont("helvetica", "bold");
  const title = run.name.length > 48 ? `${run.name.slice(0, 46)}…` : run.name;
  doc.text(title, margin, 24);
  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");
  doc.text(
    [
      agentName ? `Agent: ${agentName}` : null,
      `Status: ${run.status}`,
      `LLM judge: ${run.use_llm_judge ? "on" : "off"}`,
      new Date(run.created_at).toLocaleString(),
    ]
      .filter(Boolean)
      .join("   ·   "),
    margin,
    32,
  );

  let y = 52;

  // —— KPI strip ——
  const cardW = (contentW - 9) / 4;
  const cards: Array<{ label: string; value: string; color: readonly [number, number, number] }> = [
    { label: "Aggregate", value: agg.toFixed(2), color: scoreColor(agg) },
    {
      label: "Cases passed",
      value: `${passedCases}/${run.results.length}`,
      color: passedCases === run.results.length ? GREEN : AMBER,
    },
    { label: "Dimensions", value: String(rollup.length), color: BLUE },
    {
      label: "Pass rate",
      value:
        run.results.length > 0
          ? `${Math.round((passedCases / run.results.length) * 100)}%`
          : "—",
      color: BLUE,
    },
  ];
  cards.forEach((c, i) => {
    metricCard(doc, margin + i * (cardW + 3), y, cardW, 22, c.label, c.value, c.color);
  });
  y += 30;

  if (run.summary) {
    y = ensureSpace(doc, y, 18);
    fill(doc, SOFT_BLUE);
    roundedRect(doc, margin, y, contentW, 14, 2, "F");
    rgb(doc, INK);
    doc.setFontSize(9);
    doc.setFont("helvetica", "normal");
    const lines = doc.splitTextToSize(run.summary, contentW - 8);
    doc.text(lines.slice(0, 2), margin + 4, y + 6);
    y += 18;
  }

  // —— Dimension scores ——
  y = ensureSpace(doc, y, 28);
  rgb(doc, INK);
  doc.setFontSize(13);
  doc.setFont("helvetica", "bold");
  doc.text("Dimension scores", margin, y);
  y += 6;

  const barMax = contentW - 52;
  for (const d of rollup) {
    y = ensureSpace(doc, y, 10);
    const label = d.id.replaceAll("_", " ");
    rgb(doc, MUTED);
    doc.setFontSize(8);
    doc.setFont("helvetica", "normal");
    doc.text(label, margin, y + 3.2);

    fill(doc, LINE);
    roundedRect(doc, margin + 48, y, barMax, 4.5, 1.5, "F");
    const color = scoreColor(d.score);
    fill(doc, color);
    const w = Math.max(1.5, barMax * Math.min(1, Math.max(0, d.score)));
    roundedRect(doc, margin + 48, y, w, 4.5, 1.5, "F");

    rgb(doc, color);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(8);
    doc.text(`${Math.round(d.score * 100)}`, margin + 48 + barMax + 2, y + 3.5);
    y += 8;
  }

  // —— Color legend ——
  y = ensureSpace(doc, y, 12);
  y += 2;
  const legend = [
    { c: GREEN, t: "≥ 85%" },
    { c: BLUE, t: "70–84%" },
    { c: AMBER, t: "55–69%" },
    { c: RED, t: "< 55%" },
  ];
  let lx = margin;
  doc.setFontSize(7);
  doc.setFont("helvetica", "normal");
  for (const item of legend) {
    fill(doc, item.c);
    doc.circle(lx + 2, y, 1.6, "F");
    rgb(doc, MUTED);
    doc.text(item.t, lx + 5, y + 1);
    lx += 28;
  }
  y += 10;

  // —— Case breakdown ——
  y = ensureSpace(doc, y, 20);
  rgb(doc, INK);
  doc.setFontSize(13);
  doc.setFont("helvetica", "bold");
  doc.text("Case breakdown", margin, y);
  y += 8;

  for (const result of run.results) {
    const dims = (result.metrics?.dimensions ?? {}) as Record<
      string,
      { score?: number; passed?: boolean; threshold?: number; method?: string }
    >;
    const dimEntries = Object.entries(dims);
    const blockH = 18 + Math.ceil(dimEntries.length / 2) * 9 + (result.judge_notes ? 10 : 0);
    y = ensureSpace(doc, y, Math.min(blockH, 60));

    const headerBg = result.passed ? SOFT_GREEN : SOFT_RED;
    fill(doc, headerBg);
    stroke(doc, result.passed ? GREEN : RED);
    doc.setLineWidth(0.4);
    roundedRect(doc, margin, y, contentW, 12, 2, "FD");

    rgb(doc, INK);
    doc.setFontSize(10);
    doc.setFont("helvetica", "bold");
    doc.text(result.case_id, margin + 4, y + 5);
    const caseLabel =
      typeof result.metrics?.label === "string" ? result.metrics.label : "";
    if (caseLabel) {
      rgb(doc, MUTED);
      doc.setFontSize(8);
      doc.setFont("helvetica", "normal");
      doc.text(caseLabel, margin + 4, y + 9.5);
    }

    rgb(doc, result.passed ? GREEN : RED);
    doc.setFontSize(9);
    doc.setFont("helvetica", "bold");
    doc.text(
      `${result.passed ? "PASSED" : "FAILED"}  ·  ${result.score.toFixed(2)}`,
      margin + contentW - 4,
      y + 7,
      { align: "right" },
    );
    y += 15;

    const invokeError =
      typeof result.metrics?.invoke_error === "string" ? result.metrics.invoke_error : null;
    if (invokeError) {
      y = ensureSpace(doc, y, 12);
      fill(doc, SOFT_RED);
      roundedRect(doc, margin, y, contentW, 10, 2, "F");
      rgb(doc, RED);
      doc.setFontSize(7);
      doc.setFont("helvetica", "normal");
      const errLines = doc.splitTextToSize(`Invoke error: ${invokeError}`, contentW - 6);
      doc.text(errLines.slice(0, 2), margin + 3, y + 4);
      y += 12;
    }

    // Dimension chips 2-col
    const colW = (contentW - 4) / 2;
    let col = 0;
    let rowY = y;
    for (const [id, d] of dimEntries) {
      y = ensureSpace(doc, rowY, 10);
      if (y !== rowY) {
        rowY = y;
        col = 0;
      }
      const x = margin + col * (colW + 4);
      const sc = Number(d.score ?? 0);
      fill(doc, softScoreBg(sc));
      roundedRect(doc, x, rowY, colW, 8, 1.5, "F");
      rgb(doc, INK);
      doc.setFontSize(7);
      doc.setFont("helvetica", "bold");
      doc.text(id.replaceAll("_", " "), x + 2.5, rowY + 3.2);
      rgb(doc, scoreColor(sc));
      doc.text(`${sc.toFixed(2)}`, x + colW - 2.5, rowY + 3.2, { align: "right" });
      // mini bar
      fill(doc, LINE);
      roundedRect(doc, x + 2.5, rowY + 4.8, colW - 5, 1.6, 0.6, "F");
      fill(doc, scoreColor(sc));
      roundedRect(
        doc,
        x + 2.5,
        rowY + 4.8,
        Math.max(1, (colW - 5) * Math.min(1, sc)),
        1.6,
        0.6,
        "F",
      );

      col += 1;
      if (col >= 2) {
        col = 0;
        rowY += 9;
      }
    }
    if (col !== 0) rowY += 9;
    y = rowY + 2;

    if (result.judge_notes) {
      y = ensureSpace(doc, y, 12);
      rgb(doc, MUTED);
      doc.setFontSize(7);
      doc.setFont("helvetica", "italic");
      const notes = doc.splitTextToSize(result.judge_notes, contentW);
      doc.text(notes.slice(0, 3), margin, y);
      y += Math.min(notes.length, 3) * 3.5 + 4;
    }

    y += 4;
  }

  // —— Closing band ——
  y = ensureSpace(doc, y, 20);
  fill(doc, BG);
  roundedRect(doc, margin, y, contentW, 14, 2, "F");
  rgb(doc, INK);
  doc.setFontSize(8);
  doc.setFont("helvetica", "normal");
  doc.text(
    "Generated by TCS AI Harness Evaluation Lab · scores are measured (heuristics + optional LLM judge), not mocked.",
    margin + 4,
    y + 6,
  );
  rgb(doc, MUTED);
  doc.text(`Run id: ${run.id}`, margin + 4, y + 11);

  drawFooter(doc);
  // stamp footer on page 1 too if only one page was drawn at start without footer
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    drawFooter(doc);
  }

  const safe = run.name.replace(/[^\w\-]+/g, "_").slice(0, 48);
  doc.save(`harness-eval-${safe}-${run.id.slice(0, 8)}.pdf`);
}

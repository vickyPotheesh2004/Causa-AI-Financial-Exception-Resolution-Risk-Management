import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "file:///C:/Users/HP/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const navy = "#101C31", teal = "#147D78", ink = "#17253C", muted = "#64748B", canvas = "#F5F7FA";
const addText = (slide, text, left, top, width, height, size, color = ink, bold = false) => {
  const shape = slide.shapes.add({ geometry: "textbox", position: { left, top, width, height }, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = text; shape.text.style = { fontSize: size, color, bold, autoFit: "shrinkText" }; return shape;
};
const base = (title, subtitle) => { const s = deck.slides.add(); s.background.fill = canvas; addText(s, "CAUSA", 72, 42, 180, 30, 16, teal, true); addText(s, title, 72, 94, 1100, 54, 34, ink, true); addText(s, subtitle, 72, 156, 1050, 34, 17, muted); return s; };
const bullets = (s, items) => items.forEach((item, i) => { addText(s, "•", 88, 230 + i * 80, 22, 28, 22, teal, true); addText(s, item, 120, 226 + i * 80, 1040, 50, 19, ink); });

let s = base("Causa submission update", "AI Financial Exception Resolution and Risk Management System");
addText(s, "Evidence-driven financial exception workflow", 72, 258, 850, 45, 27, ink, true);
addText(s, "Synthetic demonstration data only. No real payment credentials or production financial records are used.", 72, 326, 920, 38, 18, muted);
addText(s, "Current status: SUBMISSION_READY_WITH_DOCUMENTED_LIMITATIONS", 72, 455, 850, 36, 18, teal, true);
addText(s, "Public demo: causa-ai-financial-exception.vercel.app", 72, 510, 850, 32, 16, muted);

s = base("Bounded AI investigation", "AI assists investigation; deterministic services retain financial authority");
bullets(s, ["Optional providers: local Ollama or intentionally configured Gemini free-tier model.", "Controlled context includes exception, evidence, risk, policy, timeline and deterministic decision.", "Strict schema validates findings, root-cause status, evidence IDs, unknowns, conflicts and route recommendation.", "Fallback is visibly labelled deterministic when an AI provider is unavailable or invalid."]);

s = base("Safety and decision boundary", "Evidence proves. Rules constrain. Humans govern consequential decisions.");
bullets(s, ["AI cannot approve payments, issue refunds, change financial records, override policy or modify audit history.", "Prompt injection text inside records remains untrusted data and cannot authorize an action.", "Cited evidence IDs are validated against the controlled case context before the finding is retained.", "The policy, risk, permission and decision engines determine approve, reject or escalation outcomes."]);

s = base("Verification and deployment", "Current implementation evidence");
bullets(s, ["76 automated tests passed, including AI prompt-injection and missing-evidence safety tests.", "Python compilation, JavaScript syntax validation and Vercel build completed successfully.", "Vercel public demo runs synthetic data with ephemeral SQLite state and deterministic fallback by default.", "Future company deployment requires durable PostgreSQL, persistent sessions, identity, object storage, monitoring and approvals."]);

await fs.mkdir("presentations", { recursive: true });
await (await PresentationFile.exportPptx(deck)).save("presentations/CAUSA_Submission_Update_v6.pptx");

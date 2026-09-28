import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "D:\\projects\\AI Financial Exception Resolution & Risk Management";
const SKILL_DIR = "C:\\Users\\HP\\.codex\\plugins\\cache\\openai-primary-runtime\\presentations\\26.921.10847\\skills\\presentations";
const RUNTIME_PYTHON = "C:\\Users\\HP\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe";
const TMP_DIR = path.join(workspaceDir, ".ppt-build");
const FINAL_PPTX = path.join(workspaceDir, "presentations", "CAUSA_Legal_and_Production_Readiness_Review.pptx");
const { resolvePresentationFont } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools", "artifact_tool_utils.mjs")).href);
const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools", "artifact_tool_utils.mjs")).href);
const font = resolvePresentationFont();
const P = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const navy = "#101C31", teal = "#147D78", ink = "#17253C", muted = "#66758B", pale = "#F5F7FA", red = "#A83C4A", amber = "#A86E15";

function textbox(slide, text, left, top, width, height, size, color=ink, bold=false) {
  const s = slide.shapes.add({ geometry: "textbox", position: { left, top, width, height }, fill: "none", line: { fill: "none", width: 0 } });
  s.text = text;
  s.text.style = { typeface: font, fontSize: size, color, bold, autoFit: "shrinkText" };
  return s;
}
function line(slide, left, top, width, color=teal) {
  return slide.shapes.add({ geometry: "rect", position: { left, top, width, height: 4 }, fill: color, line: { fill: color, width: 0 } });
}
function base(slide, number, title, subtitle="") {
  slide.background.fill = "#FFFFFF";
  textbox(slide, "CAUSE AI", 72, 35, 180, 25, 13, teal, true);
  textbox(slide, String(number).padStart(2, "0"), 1160, 35, 50, 25, 12, muted, true);
  textbox(slide, title, 72, 83, 1080, 52, 31, ink, true);
  if (subtitle) textbox(slide, subtitle, 72, 143, 1090, 36, 15, muted, false);
  line(slide, 72, 196, 1136, "#D9E3EA");
}
function bullets(slide, items, left=96, top=235, width=1040, size=18, color=ink) {
  let y=top;
  for (const item of items) {
    textbox(slide, "•", left, y, 22, 28, size, teal, true);
    textbox(slide, item, left+28, y, width, 55, size, color, false);
    y += 74;
  }
}

let s = P.slides.add();
s.background.fill = navy;
textbox(s, "Cause AI", 85, 128, 700, 74, 56, "#FFFFFF", true);
textbox(s, "Legal and production readiness review", 88, 219, 770, 38, 25, "#B7C8D8", false);
line(s, 88, 286, 210, "#53C7B7");
textbox(s, "Financial exception investigation and risk management", 88, 322, 760, 35, 20, "#D7E0ED", false);
textbox(s, "Prepared for legal, privacy, security and business review\n26 September 2026", 88, 560, 600, 52, 16, "#9FB0C3", false);
s.speakerNotes.textFrame.setText("Internal review deck. Current implementation evidence and release blockers.");

s = P.slides.add(); base(s, 2, "Application scope", "What Cause AI does today");
bullets(s, [
  "Detects payment-operation exceptions from normalized financial records and preserves evidence references.",
  "Creates tenant-scoped cases, investigation tickets and append-only audit events.",
  "Uses deterministic rules and explainable risk assessment. Human reviewers retain final authority.",
  "Runs as an approved synthetic-data demo on local loopback infrastructure."
]);

s = P.slides.add(); base(s, 3, "Financial data controls", "Controls added around imports and evidence");
bullets(s, [
  "Immutable financial-event records include tenant scope, source identity, SHA-256 content hash and ingestion time.",
  "Changed replay of a source record returns a conflict instead of silently replacing evidence.",
  "The Razorpay connector requires an explicit live-mode flag and tenant match before any read-only import.",
  "Normalized import data excludes raw email and card details from the connector output."
]);

s = P.slides.add(); base(s, 4, "Security controls", "Backend behavior verified by automated tests");
bullets(s, [
  "Tenant isolation, role checks, same-origin writes and immutable audit records protect core workflows.",
  "The HTTP layer applies CSP, no-store responses, MIME-sniffing protection and clickjacking protection.",
  "Request-size limits, malformed Content-Length handling, session expiry and login throttling reduce common abuse paths.",
  "Health checks verify database access and report the active schema version."
]);

s = P.slides.add(); base(s, 5, "Legal and privacy package", "Templates require legal completion before publication");
bullets(s, [
  "Terms cover authorised access, acceptable use, confidentiality, customer responsibility and service limits.",
  "Privacy notice covers processed data, purpose, sharing, retention, data rights and incident handling.",
  "India review includes DPDP, RBI payment-data restrictions, localisation requirements and applicable NPCI or UPI obligations.",
  "The template contains placeholders for the legal entity, privacy contact, processors, retention schedule and jurisdiction terms."
]);
s.speakerNotes.textFrame.setText("Sources: MeitY DPDP Act 2023 and DPDP Rules 2025; RBI card-on-file storage restriction RBI/2022-23/77; RBI payment-system storage FAQ.");

s = P.slides.add(); base(s, 6, "Production readiness score", "Evidence-based assessment as of 26 September 2026");
textbox(s, "43", 100, 255, 260, 140, 106, red, true);
textbox(s, "out of 100", 110, 400, 190, 32, 22, muted, false);
line(s, 420, 280, 700, "#E6EBF1");
textbox(s, "The score credits implemented application controls and 66 passing automated checks.", 420, 310, 700, 54, 20, ink, false);
textbox(s, "It excludes planned architecture, draft legal terms and controls that do not yet operate in production.", 420, 395, 700, 54, 20, ink, false);
textbox(s, "Production launch remains blocked by design.", 420, 490, 700, 32, 20, red, true);

s = P.slides.add(); base(s, 7, "Release blockers", "Controls the workspace cannot truthfully claim as complete");
bullets(s, [
  "Managed database, encrypted and tested backups, disaster recovery, TLS ingress, WAF, secrets manager and central observability.",
  "Company identity provider, MFA, SSO, lifecycle provisioning and privileged-access administration.",
  "Authorized Razorpay production credentials, webhook verification, settlement and refund sources, plus reconciliation approval.",
  "Independent VAPT, penetration testing, load testing, incident exercise, legal approval and signed customer agreements."
], 96, 230, 1040, 17, ink);

s = P.slides.add(); base(s, 8, "Submission decision", "Recommended next actions for legal and production owners");
bullets(s, [
  "Legal team completes the company-specific placeholders and approves the Terms, Privacy Notice and DPA.",
  "Security and platform teams implement the required production environment and produce operational evidence.",
  "Payments owners approve real Razorpay integration scope, credentials, webhook controls and reconciliation rules.",
  "Release authority reassesses the score after independent testing and documented control acceptance."
]);

await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });
const candidatePath = path.join(TMP_DIR, "causa-candidate.pptx");
await (await PresentationFile.exportPptx(P)).save(candidatePath);
await finalizePresentation({
  workspaceDir, candidatePath, finalPath: FINAL_PPTX, pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools", "inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools", "inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-heading-fit"],
  fontPolicy: { basis: "design", families: [font] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(TMP_DIR, "CAUSA_Legal_and_Production_Readiness_Review.validation.json"),
});
console.log(FINAL_PPTX);

import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";
const workspaceDir = process.cwd();
const SKILL_DIR = "C:/Users/HP/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations";
const RUNTIME_PYTHON = "C:/Users/HP/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe";
const sourcePath = path.join(workspaceDir, "presentations/CAUSA_Legal_and_Production_Readiness_Review.pptx");
const finalPath = path.join(workspaceDir, "presentations/CAUSA_Legal_and_Production_Readiness_Review_Updated_v5.pptx");
const stagingDir = path.join(workspaceDir, ".codex-finalizer");
await fs.mkdir(stagingDir, {recursive:true});
const presentation = await PresentationFile.importPptx(await FileBlob.load(sourcePath));
const replacements = [
 ["sh/87ipkzal", "Evidence-based assessment as of 26 September 2026", "Evidence-based assessment as of 27 September 2026"],
 ["sh/ml07i9sv", "43", "55"],
 ["sh/pc76hkr2", "The score credits implemented application controls and 66 passing automated checks.", "The score credits implemented controls, governance gates and 72 passing automated checks."],
 ["sh/h4bupgn6", "It excludes planned architecture, draft legal terms and controls that do not yet operate in production.", "Cross-document implementation is 56 out of 100 against the PDR and project description."],
 ["sh/w32twb6l", "Production launch remains blocked by design.", "Production launch remains blocked until company controls are evidenced."],
 ["sh/jadsz2xk", "Health checks verify database access and report the active schema version.", "Health checks verify database access and report schema version 4."],
];
for (const [id, oldText, replacement] of replacements) {
  const target = presentation.resolve(id);
  target.text.replace(oldText, replacement);
}
const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR,"container_tools/artifact_tool_utils.mjs")).href);
const candidatePath = path.join(stagingDir,"cause-ai-readiness-updated-candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
await finalizePresentation({
 workspaceDir, candidatePath, finalPath, pythonExecutable:RUNTIME_PYTHON,
 integrityValidatorPath:path.join(SKILL_DIR,"container_tools/inspect_presentation_package_integrity.py"),
 layoutValidatorPath:path.join(SKILL_DIR,"container_tools/inspect_presentation_layout_geometry.py"),
 layoutArgs:["--expected-slide-size-emu","12192000,6858000","--validate-bullet-geometry","--validate-heading-fit"],
 requiredNativeTableOwnerSlides:[],
 verifyArtifactToolImport:true,
 receiptPath:path.join(stagingDir,"cause-ai-readiness-updated-v5-validation.json"),
});







import { FileBlob, PresentationFile } from "file:///C:/Users/HP/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";
const p = await PresentationFile.importPptx(await FileBlob.load("presentations/CAUSA_Legal_and_Production_Readiness_Review_Updated_v5.pptx"));
const s = await p.inspect({kind:"slide,textbox,shape,notes",maxChars:12000});
console.log(s.ndjson);

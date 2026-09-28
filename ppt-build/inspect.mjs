import { FileBlob, PresentationFile } from "@oai/artifact-tool";
const source = process.argv[2];
const p = await PresentationFile.importPptx(await FileBlob.load(source));
const snap = await p.inspect({kind:"slide,textbox,shape,notes", maxChars:20000});
console.log(snap.ndjson);

import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";
const root = "D:\\projects\\AI Financial Exception Resolution & Risk Management";
const deck = await PresentationFile.importPptx(await FileBlob.load(path.join(root, "presentations", "CAUSA_Legal_and_Production_Readiness_Review.pptx")));
const dir = path.join(root, ".ppt-build", "rendered");
await fs.mkdir(dir, {recursive:true});
for (let i = 0; i < deck.slides.length; i++) {
  const image = await deck.export({slide: deck.slides.get(i), format:"png", scale:1});
  await fs.writeFile(path.join(dir, `slide-${i+1}.png`), new Uint8Array(await image.arrayBuffer()));
}
console.log(`rendered=${deck.slides.length}`);

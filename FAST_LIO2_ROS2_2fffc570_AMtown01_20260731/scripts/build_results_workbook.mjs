import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "D:/Desktop/carry_bot_2_ws/baseline_artifacts";
const runCsv = await fs.readFile(`${root}/analysis/csv/run_summary.csv`, "utf8");
const repeatCsv = await fs.readFile(`${root}/analysis/csv/repeatability_summary.csv`, "utf8");

const workbook = await Workbook.fromCSV(runCsv, { sheetName: "Run Summary" });
await workbook.fromCSV(repeatCsv, { sheetName: "Repeatability" });

function coerceScientificTypes(sheet) {
  const used = sheet.getUsedRange();
  const values = used.values;
  for (let row = 1; row < values.length; row += 1) {
    for (let col = 0; col < values[row].length; col += 1) {
      const value = values[row][col];
      if (value === "True" || value === "False") {
        values[row][col] = value === "True";
      } else if (typeof value === "string" && /^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$/.test(value)) {
        values[row][col] = Number(value);
      }
    }
  }
  used.values = values;
}

coerceScientificTypes(workbook.worksheets.getItem("Run Summary"));
coerceScientificTypes(workbook.worksheets.getItem("Repeatability"));

for (const name of ["Run Summary", "Repeatability"]) {
  const sheet = workbook.worksheets.getItem(name);
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const used = sheet.getUsedRange();
  used.format.font = { name: "Arial", size: 9, color: "#1F2937" };
  used.format.autofitColumns();
  used.format.autofitRows();
  used.getRow(0).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF", size: 9 },
    wrapText: true,
    rowHeight: 48,
    borders: { preset: "outside", style: "thin", color: "#17365D" },
  };
}

const runSheet = workbook.worksheets.getItem("Run Summary");
runSheet.getRange("B2:C4").format.numberFormat = "#,##0";
runSheet.getRange("D2:AZ4").format.numberFormat = "0.000";
const repeatSheet = workbook.worksheets.getItem("Repeatability");
repeatSheet.getRange("B2:E200").format.numberFormat = "0.000";
repeatSheet.getRange("F2:F200").format.numberFormat = "0";

const inspect = await workbook.inspect({
  kind: "table",
  range: "'Run Summary'!A1:K4",
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 12,
  maxChars: 6000,
});
await fs.writeFile(`${root}/analysis/results_workbook_inspect.ndjson`, inspect.ndjson, "utf8");

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
await fs.writeFile(`${root}/analysis/results_workbook_error_scan.ndjson`, errors.ndjson, "utf8");

const preview = await workbook.render({
  sheetName: "Run Summary",
  range: "A1:K4",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(`${root}/analysis/results_workbook_preview.png`, new Uint8Array(await preview.arrayBuffer()));

const repeatPreview = await workbook.render({
  sheetName: "Repeatability",
  range: "A1:F18",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(`${root}/analysis/results_workbook_repeatability_preview.png`, new Uint8Array(await repeatPreview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(`${root}/analysis/FAST_LIO2_baseline_results.xlsx`);
console.log(inspect.ndjson);
console.log(errors.ndjson);

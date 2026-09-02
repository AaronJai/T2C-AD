// Generator for docs/qual-comparison-tables-v3-claude-sonnet{,-ea}.docx
// Reads /tmp/qual_comparison_by_type.json (produced from results/qual_records_claude-sonnet_v3_localdb.json)
// and renders one color-coded table per ambiguity_type: Question | C2 output | C3 output,
// with cell shading standing in for the correct/incorrect column.
//
// METRIC env var selects which correctness flag drives the shading:
//   METRIC=ex (default) — is_correct (matches the benchmark's DEFAULT interpretation)
//   METRIC=ea            — matches_any_interpretation (matches ANY gold interpretation)
// The two are not interchangeable: EX has 0 regressions across all 80 ambiguous items;
// EA has exactly 1 (Q-104, temporal — see decisions-log 2026-07-28).
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, ShadingType, HeadingLevel, PageOrientation, BorderStyle,
  VerticalAlign, PageBreak,
} = require("docx");

const METRIC = (process.env.METRIC || "ex").toLowerCase();
if (!["ex", "ea"].includes(METRIC)) throw new Error(`METRIC must be 'ex' or 'ea', got '${METRIC}'`);
const C2_FIELD = `c2_correct_${METRIC}`;
const C3_FIELD = `c3_correct_${METRIC}`;
const OUT_PATH = `/tmp/qual-comparison-tables-v3-claude-sonnet${METRIC === "ea" ? "-ea" : ""}.docx`;

const DATA = JSON.parse(fs.readFileSync("/tmp/qual_comparison_by_type.json", "utf8"));

const GREEN = "DCF2DC";
const RED = "F8D7D9";
const HEADER_FILL = "E8E8E8";

const COL_WIDTHS = [2880, 5760, 5760]; // DXA, sums to 14400 (10in usable at landscape letter, 0.5in margins)

const TYPE_TITLES = {
  schema: "Schema ambiguity", entity: "Entity ambiguity",
  intent: "Intent ambiguity", temporal: "Temporal ambiguity",
};

function summarize(rows) {
  let bothCorrect = 0, bothWrong = 0, fixed = 0, regressed = 0;
  rows.forEach((r) => {
    const a = r[C2_FIELD], b = r[C3_FIELD];
    if (a && b) bothCorrect++;
    else if (!a && !b) bothWrong++;
    else if (!a && b) fixed++;
    else regressed++;
  });
  return `n=${rows.length} — ${fixed} fixed by C3, ${regressed} regressed, ${bothCorrect} both_correct, ${bothWrong} both_wrong`;
}

const cellBorders = {
  top: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
  bottom: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
  left: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
  right: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
};

function headerCell(text, width) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, color: "auto", fill: HEADER_FILL },
    borders: cellBorders,
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, size: 18 })] })],
  });
}

function questionCell(qid, question, width) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders: cellBorders,
    verticalAlign: VerticalAlign.TOP,
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    children: [
      new Paragraph({ children: [new TextRun({ text: qid, bold: true, size: 15, color: "666666" })] }),
      new Paragraph({ children: [new TextRun({ text: question, size: 17 })] }),
    ],
  });
}

function outputCell(cypher, correct, failureMode, width) {
  const paras = [
    new Paragraph({ children: [new TextRun({ text: cypher, font: "Courier New", size: 15 })] }),
  ];
  if (!correct) {
    paras.push(new Paragraph({
      children: [new TextRun({ text: `✗ ${failureMode || "wrong"}`, italics: true, size: 14, color: "8A1F26" })],
    }));
  } else {
    const label = METRIC === "ea" ? "✓ matches an interpretation" : "✓ matches default";
    paras.push(new Paragraph({
      children: [new TextRun({ text: label, italics: true, size: 14, color: "1F6B2C" })],
    }));
  }
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, color: "auto", fill: correct ? GREEN : RED },
    borders: cellBorders,
    verticalAlign: VerticalAlign.TOP,
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    children: paras,
  });
}

function buildTable(rows) {
  const header = new TableRow({
    tableHeader: true,
    children: [
      headerCell("Question", COL_WIDTHS[0]),
      headerCell("C2 — schema_grounded", COL_WIDTHS[1]),
      headerCell("C3 — disambiguation_enhanced", COL_WIDTHS[2]),
    ],
  });
  const body = rows.map((r) => new TableRow({
    children: [
      questionCell(r.qid, r.question, COL_WIDTHS[0]),
      outputCell(r.c2_cypher, r[C2_FIELD], r.c2_failure, COL_WIDTHS[1]),
      outputCell(r.c3_cypher, r[C3_FIELD], r.c3_failure, COL_WIDTHS[2]),
    ],
  }));
  return new Table({
    width: { size: 14400, type: WidthType.DXA },
    columnWidths: COL_WIDTHS,
    rows: [header, ...body],
  });
}

const children = [];

const metricLabel = METRIC === "ea"
  ? "EA (matches ANY gold interpretation)"
  : "EX (matches the DEFAULT gold interpretation)";

children.push(new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun({ text: `C2 vs C3 — Per-Question Comparison by Ambiguity Type (${METRIC.toUpperCase()})` })],
}));
children.push(new Paragraph({
  children: [new TextRun({
    text: "v3 substrate, Claude Sonnet 4.6 backend. Author: Aaron Tan. Run: local Neo4j Desktop " +
      "(policev3), 2026-07-27 — companion to the canonical Kaya run. Source: results/qual_records_" +
      "claude-sonnet_v3_localdb.json via experiments/analyze_qualitative.py.",
    italics: true, size: 18, color: "555555",
  })],
}));
children.push(new Paragraph({ text: "" }));
children.push(new Paragraph({
  children: [
    new TextRun({ text: "Legend: ", bold: true, size: 19 }),
    new TextRun({ text: "green ", bold: true, size: 19, color: "1F6B2C" }),
    new TextRun({ text: `= the generated query matches ${metricLabel}. `, size: 19 }),
    new TextRun({ text: "Red ", bold: true, size: 19, color: "8A1F26" }),
    new TextRun({ text: "= it does not; the small note under the query gives the failure_mode " +
      "(valid_non_default = a different valid reading than the default; wrong_result = matches no gold interpretation; " +
      "invalid_query = never executed).", size: 19 }),
  ],
}));
if (METRIC === "ea") {
  children.push(new Paragraph({ text: "" }));
  children.push(new Paragraph({
    children: [new TextRun({
      text: "Note: unlike EX (0 regressions across all 80 ambiguous items), EA has exactly one — " +
        "Q-104 “Who owns the Holden Commodore?” (temporal table). C2's unfiltered query happens to " +
        "satisfy the benchmark's non-default “including previous owner” reading; C3's retry loop " +
        "correctly flagged the temporal ambiguity but a downstream query-generation bug merged make+model " +
        "into a single malformed property ({model:'Holden Commodore'}), matching no interpretation at all. " +
        "The regression is a QG execution defect surfaced during retry, not a disambiguation-reasoning error.",
      italics: true, size: 17, color: "8A1F26",
    })],
  }));
}
children.push(new Paragraph({ text: "" }));

const order = ["schema", "entity", "intent", "temporal"];
order.forEach((type, i) => {
  if (i > 0) children.push(new Paragraph({ children: [new PageBreak()] }));
  children.push(new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text: TYPE_TITLES[type] })],
  }));
  children.push(new Paragraph({
    children: [new TextRun({ text: summarize(DATA[type]), italics: true, size: 18, color: "555555" })],
  }));
  children.push(new Paragraph({ text: "" }));
  children.push(buildTable(DATA[type]));
  children.push(new Paragraph({ text: "" }));
});

const doc = new Document({
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840, orientation: PageOrientation.LANDSCAPE },
        margin: { top: 720, bottom: 720, left: 720, right: 720 },
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT_PATH, buf);
  console.log(`wrote ${OUT_PATH}`);
});

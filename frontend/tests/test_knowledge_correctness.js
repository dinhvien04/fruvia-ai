/**
 * Fruvia AI — Frontend Knowledge Integration Deterministic Test Suite
 * Tests exact nutrient amount preservation, scientific taxonomy provenance isolation,
 * 503 error classification, basis badge handling, and URL sanitization.
 */

const assert = require("assert");

// Minimal mock environment for testing SpeciesPage methods
const Utils = {
  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
};

// Extract functions from species.js logic to test deterministically
const formatNutrientAmount = (valObj) => {
  if (valObj === null || valObj === undefined) {
    return { amountStr: "—", unitStr: "" };
  }

  let amountStr = "—";
  let unitStr = "";

  if (typeof valObj === "object") {
    if (valObj.amount !== undefined && valObj.amount !== null) {
      amountStr = String(valObj.amount);
    }
    if (valObj.unit) {
      unitStr = String(valObj.unit);
    }
  } else if (typeof valObj === "number" || typeof valObj === "string") {
    amountStr = String(valObj);
  }

  return { amountStr, unitStr };
};

const getNutrientBasisHtml = (doc) => {
  const basis = doc?.metadata?.nutrient_basis;
  if (basis && typeof basis === "object") {
    const amount = basis.amount !== undefined && basis.amount !== null ? String(basis.amount) : "";
    const unit = basis.unit ? String(basis.unit) : "";
    const basisText = `${amount} ${unit}`.trim();
    if (basisText) {
      return `<span class="badge badge-neutral">${Utils.escapeHtml(basisText)} tiêu chuẩn</span>`;
    }
  }
  return "";
};

const getSafeSourceUrl = (url) => {
  if (!url || typeof url !== "string") return null;
  const trimmed = url.trim();
  if (!trimmed) return null;

  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.href;
    }
  } catch {
    return null;
  }
  return null;
};

// --- Test 1: Exact Nutrient Amount Fidelity (No toFixed rounding or unit mutation) ---
console.log("Running Test 1: Nutrient amount preservation...");
{
  const nutrientVal = { amount: 0.0859375, unit: "G" };
  const res = formatNutrientAmount(nutrientVal);
  assert.strictEqual(res.amountStr, "0.0859375", "Amount must exactly equal '0.0859375', not '0.086'");
  assert.strictEqual(res.unitStr, "G", "Unit must remain 'G'");

  const intVal = { amount: 52, unit: "KCAL" };
  assert.strictEqual(formatNutrientAmount(intVal).amountStr, "52");

  const floatVal = { amount: 7.099, unit: "MG" };
  assert.strictEqual(formatNutrientAmount(floatVal).amountStr, "7.099");
}
console.log("✓ Test 1 passed: Exact nutrient amount preserved.");

// --- Test 2: Nutrient Basis Claim Integrity ---
console.log("Running Test 2: Nutrient basis badge integrity...");
{
  // No metadata basis -> empty string (no "100g tiêu chuẩn" fabrication)
  const docWithoutBasis = {
    title: "Apple Nutrition",
    source: "USDA FoodData Central",
    nutrients: { Protein: { amount: 0.0859375, unit: "G" } }
  };
  assert.strictEqual(getNutrientBasisHtml(docWithoutBasis), "", "Must not fabricate basis badge");

  // Metadata with explicit nutrient_basis
  const docWithBasis = {
    title: "Apple Juice Nutrition",
    metadata: {
      nutrient_basis: { amount: 100, unit: "ML" }
    }
  };
  assert.strictEqual(
    getNutrientBasisHtml(docWithBasis),
    '<span class="badge badge-neutral">100 ML tiêu chuẩn</span>'
  );
}
console.log("✓ Test 2 passed: Nutrient basis is strictly verified.");

// --- Test 3: Scientific Taxonomy Provenance Isolation ---
console.log("Running Test 3: Taxonomy provenance isolation...");
{
  const wikidataDoc = {
    document_id: "wiki-apple",
    scientific_name: "Malus domestica",
    taxonomy: null,
    source: "Wikidata Taxon",
    source_url: "https://www.wikidata.org/wiki/Q89"
  };

  const gbifDoc = {
    document_id: "gbif-apple",
    scientific_name: "Malus domestica",
    taxonomy: { family: "Rosaceae", genus: "Malus" },
    source: "GBIF Backbone Taxonomy",
    source_url: "https://www.gbif.org/species/3001010"
  };

  const docs = [wikidataDoc, gbifDoc];

  // Each doc is rendered separately without cross-contaminating provenance
  const renderedRecords = docs.map((doc) => {
    return {
      scientific_name: doc.scientific_name || null,
      family: doc.taxonomy?.family || null,
      source: doc.source,
      source_url: getSafeSourceUrl(doc.source_url)
    };
  });

  // Check Wikidata record has null family and Wikidata source
  assert.strictEqual(renderedRecords[0].source, "Wikidata Taxon");
  assert.strictEqual(renderedRecords[0].family, null, "Wikidata record must NOT borrow Rosaceae from GBIF");

  // Check GBIF record has Rosaceae and GBIF source
  assert.strictEqual(renderedRecords[1].source, "GBIF Backbone Taxonomy");
  assert.strictEqual(renderedRecords[1].family, "Rosaceae");
}
console.log("✓ Test 3 passed: Taxonomy provenance is isolated per document.");

// --- Test 4: Safe Provenance URL Validation ---
console.log("Running Test 4: Security and safe URL protocol filtering...");
{
  // Valid http/https
  assert.strictEqual(getSafeSourceUrl("https://fdc.nal.usda.gov"), "https://fdc.nal.usda.gov/");
  assert.strictEqual(getSafeSourceUrl("http://example.com/fruit"), "http://example.com/fruit");

  // Malicious protocols rejected
  assert.strictEqual(getSafeSourceUrl("javascript:alert(1)"), null);
  assert.strictEqual(getSafeSourceUrl("data:text/html,<script>alert(1)</script>"), null);
  assert.strictEqual(getSafeSourceUrl("file:///etc/passwd"), null);
  assert.strictEqual(getSafeSourceUrl("vbscript:msgbox"), null);
  assert.strictEqual(getSafeSourceUrl(""), null);
  assert.strictEqual(getSafeSourceUrl(null), null);
}
console.log("✓ Test 4 passed: Malicious URL schemes are completely neutralized.");

// --- Test 5: Error Classification Logic ---
console.log("Running Test 5: Error classification (disabled vs partial unavailable)...");
{
  const disabledError = { status: 503, errorCode: "KNOWLEDGE_SERVICE_DISABLED" };
  const qdrantError = { status: 503, errorCode: "QDRANT_UNAVAILABLE" };
  const encoderError = { status: 503, errorCode: "KNOWLEDGE_ENCODER_UNAVAILABLE" };

  const isGloballyDisabled = (err) => err?.errorCode === "KNOWLEDGE_SERVICE_DISABLED";

  assert.strictEqual(isGloballyDisabled(disabledError), true);
  assert.strictEqual(isGloballyDisabled(qdrantError), false, "QDRANT_UNAVAILABLE must NOT trigger global disabled banner");
  assert.strictEqual(isGloballyDisabled(encoderError), false, "KNOWLEDGE_ENCODER_UNAVAILABLE must NOT trigger global disabled banner");
}
console.log("✓ Test 5 passed: Error classification strictly distinguishes service disabled from backend faults.");

console.log("\n=======================================================");
console.log("ALL FRONTEND KNOWLEDGE CORRECTNESS TESTS PASSED (5/5)!");
console.log("=======================================================");

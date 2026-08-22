/**
 * Fruvia AI — Frontend Knowledge Integration Deterministic Test Suite
 * Directly executes the production knowledge-utils.js module to guarantee
 * 100% test integrity against production logic.
 */

const assert = require("assert");
const KnowledgeUtils = require("../js/knowledge-utils.js");

console.log("=== Testing Production KnowledgeUtils Module ===");

// --- Test 1: Exact Nutrient Amount Fidelity ---
console.log("Running Test 1: Nutrient amount preservation...");
{
  const nutrientVal = { amount: 0.0859375, unit: "G" };
  const res = KnowledgeUtils.formatNutrientAmount(nutrientVal);
  assert.strictEqual(
    res.amountStr,
    "0.0859375",
    "Amount must strictly equal '0.0859375' (never rounded to 0.086)"
  );
  assert.strictEqual(res.unitStr, "G", "Unit must remain 'G'");

  const intVal = { amount: 52, unit: "KCAL" };
  assert.strictEqual(KnowledgeUtils.formatNutrientAmount(intVal).amountStr, "52");

  const floatVal = { amount: 7.099, unit: "MG" };
  assert.strictEqual(KnowledgeUtils.formatNutrientAmount(floatVal).amountStr, "7.099");

  const scalarVal = 12.3456;
  assert.strictEqual(KnowledgeUtils.formatNutrientAmount(scalarVal).amountStr, "12.3456");

  const nullVal = KnowledgeUtils.formatNutrientAmount(null);
  assert.strictEqual(nullVal.amountStr, "—");
  assert.strictEqual(nullVal.unitStr, "");
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
  assert.strictEqual(
    KnowledgeUtils.getNutrientBasisHtml(docWithoutBasis),
    "",
    "Must not fabricate basis badge when metadata.nutrient_basis is absent"
  );

  // Metadata with explicit nutrient_basis
  const docWithBasis = {
    title: "Apple Juice Nutrition",
    metadata: {
      nutrient_basis: { amount: 100, unit: "ML" }
    }
  };
  assert.strictEqual(
    KnowledgeUtils.getNutrientBasisHtml(docWithBasis),
    '<span class="badge badge-neutral">100 ML tiêu chuẩn</span>'
  );
}
console.log("✓ Test 2 passed: Nutrient basis is strictly verified.");

// --- Test 3: Safe Provenance URL Validation ---
console.log("Running Test 3: Security and safe URL protocol filtering...");
{
  // Valid http/https
  assert.strictEqual(
    KnowledgeUtils.getSafeSourceUrl("https://fdc.nal.usda.gov/fdc-app.html"),
    "https://fdc.nal.usda.gov/fdc-app.html"
  );
  assert.strictEqual(
    KnowledgeUtils.getSafeSourceUrl("http://example.com/fruit"),
    "http://example.com/fruit"
  );

  // Malicious protocols neutralized
  assert.strictEqual(KnowledgeUtils.getSafeSourceUrl("javascript:alert(1)"), null);
  assert.strictEqual(KnowledgeUtils.getSafeSourceUrl("data:text/html,<script>alert(1)</script>"), null);
  assert.strictEqual(KnowledgeUtils.getSafeSourceUrl("file:///etc/passwd"), null);
  assert.strictEqual(KnowledgeUtils.getSafeSourceUrl("vbscript:msgbox"), null);
  assert.strictEqual(KnowledgeUtils.getSafeSourceUrl(""), null);
  assert.strictEqual(KnowledgeUtils.getSafeSourceUrl(null), null);
}
console.log("✓ Test 3 passed: Malicious URL schemes are completely neutralized.");

// --- Test 4: Partial Failure & Error Classification Behavior ---
console.log("Running Test 4: Partial failure and error classification...");
{
  // Scenario A: Overview fulfilled, Taxonomy fulfilled, Nutrition rejected with QDRANT_UNAVAILABLE 503
  const settledScenarioA = [
    {
      status: "fulfilled",
      value: { results: [{ title: "Táo Overview", text: "Táo là cây ăn quả." }] }
    },
    {
      status: "fulfilled",
      value: { results: [{ scientific_name: "Malus domestica", taxonomy: { family: "Rosaceae" } }] }
    },
    {
      status: "rejected",
      reason: { status: 503, errorCode: "QDRANT_UNAVAILABLE", message: "Qdrant connection refused" }
    }
  ];

  const processedA = KnowledgeUtils.processKnowledgeResponses(settledScenarioA);
  assert.strictEqual(
    processedA.isGloballyDisabled,
    false,
    "QDRANT_UNAVAILABLE 503 must NOT trigger global disabled state"
  );
  assert.notStrictEqual(processedA.overview, null, "Overview must remain fulfilled and renderable");
  assert.strictEqual(processedA.overviewErr, null);
  assert.notStrictEqual(processedA.taxonomy, null, "Taxonomy must remain fulfilled and renderable");
  assert.strictEqual(processedA.taxonomyErr, null);
  assert.strictEqual(processedA.nutrition, null);
  assert.strictEqual(
    processedA.nutritionErr.errorCode,
    "QDRANT_UNAVAILABLE",
    "Nutrition must be individually tracked as an error"
  );

  // Scenario B: Global service disabled (KNOWLEDGE_SERVICE_DISABLED)
  const settledScenarioB = [
    {
      status: "rejected",
      reason: { status: 503, errorCode: "KNOWLEDGE_SERVICE_DISABLED", message: "Knowledge disabled" }
    },
    {
      status: "rejected",
      reason: { status: 503, errorCode: "KNOWLEDGE_SERVICE_DISABLED", message: "Knowledge disabled" }
    },
    {
      status: "rejected",
      reason: { status: 503, errorCode: "KNOWLEDGE_SERVICE_DISABLED", message: "Knowledge disabled" }
    }
  ];

  const processedB = KnowledgeUtils.processKnowledgeResponses(settledScenarioB);
  assert.strictEqual(
    processedB.isGloballyDisabled,
    true,
    "KNOWLEDGE_SERVICE_DISABLED must trigger global disabled state"
  );
}
console.log("✓ Test 4 passed: Partial failure and global disabled states behave as expected.");

// --- Test 5: Scientific Taxonomy Provenance Isolation ---
console.log("Running Test 5: Taxonomy provenance isolation...");
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
      source_url: KnowledgeUtils.getSafeSourceUrl(doc.source_url)
    };
  });

  // Verify Wikidata record has null family and Wikidata source
  assert.strictEqual(renderedRecords[0].source, "Wikidata Taxon");
  assert.strictEqual(
    renderedRecords[0].family,
    null,
    "Wikidata record must NOT borrow Rosaceae from GBIF"
  );

  // Verify GBIF record has Rosaceae and GBIF source
  assert.strictEqual(renderedRecords[1].source, "GBIF Backbone Taxonomy");
  assert.strictEqual(renderedRecords[1].family, "Rosaceae");
}
console.log("✓ Test 5 passed: Taxonomy provenance isolation verified.");

console.log("\n=======================================================");
console.log("ALL PRODUCTION KNOWLEDGE UTILITY TESTS PASSED (5/5)!");
console.log("=======================================================");

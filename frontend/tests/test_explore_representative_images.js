/**
 * Fruvia AI — Explore Representative Images Deterministic Test Suite
 * Tests representative image rendering, safe URL sanitation, fallback placeholders,
 * and canonical species navigation routes.
 */

const assert = require("assert");
const KnowledgeUtils = require("../js/knowledge-utils.js");

console.log("=== Testing Explore Representative Images Logic ===");

// --- Test 1: Safe HTTP/HTTPS URL Sanitation ---
console.log("Running Test 1: Safe HTTP/HTTPS URL verification...");
{
  assert.strictEqual(
    KnowledgeUtils.getSafeHttpUrl("https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/thumbnails/apple.webp"),
    "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/thumbnails/apple.webp"
  );
  assert.strictEqual(
    KnowledgeUtils.getSafeHttpUrl("http://cdn.fruvia.ai/banana.jpg"),
    "http://cdn.fruvia.ai/banana.jpg"
  );

  // Unsafe schemes must return null
  assert.strictEqual(KnowledgeUtils.getSafeHttpUrl("javascript:alert(1)"), null);
  assert.strictEqual(KnowledgeUtils.getSafeHttpUrl("data:image/png;base64,123"), null);
  assert.strictEqual(KnowledgeUtils.getSafeHttpUrl("file:///etc/passwd"), null);
  assert.strictEqual(KnowledgeUtils.getSafeHttpUrl("vbscript:msgbox"), null);
  assert.strictEqual(KnowledgeUtils.getSafeHttpUrl(""), null);
  assert.strictEqual(KnowledgeUtils.getSafeHttpUrl(null), null);
  assert.strictEqual(KnowledgeUtils.getSafeHttpUrl(undefined), null);
}
console.log("✓ Test 1 passed: Safe HTTP/HTTPS URL verification.");

// --- Test 2: Card Media Rendering Simulation ---
console.log("Running Test 2: Card media markup simulation...");
{
  function renderMediaArea(item) {
    const safeUrl = KnowledgeUtils.getSafeHttpUrl(item.representative_image_url);
    const altText = KnowledgeUtils.escapeHtml(item.name_vi || item.name_en || item.canonical_class);

    if (safeUrl) {
      return `<img src="${KnowledgeUtils.escapeHtml(safeUrl)}" alt="${altText}" loading="lazy" decoding="async" class="species-card-image"><img src="assets/svg/brand-mark.svg" alt="" class="species-placeholder-icon" style="display: none;" aria-hidden="true">`;
    }
    return `<img src="assets/svg/brand-mark.svg" alt="" class="species-placeholder-icon" aria-hidden="true">`;
  }

  // Case A: Real image URL present
  const appleItem = {
    canonical_class: "apple",
    name_en: "Apple",
    name_vi: "Táo",
    representative_image_url: "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/thumbnails/apple.webp"
  };
  const appleHtml = renderMediaArea(appleItem);
  assert.ok(appleHtml.includes('class="species-card-image"'));
  assert.ok(appleHtml.includes('src="https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/thumbnails/apple.webp"'));
  assert.ok(appleHtml.includes('alt="Táo"'));
  assert.ok(appleHtml.includes('loading="lazy"'));

  // Case B: Image URL is null -> Placeholder rendered
  const nullItem = {
    canonical_class: "potato",
    name_en: "Potato",
    name_vi: "Khoai tây",
    representative_image_url: null
  };
  const nullHtml = renderMediaArea(nullItem);
  assert.ok(!nullHtml.includes('class="species-card-image"'));
  assert.ok(nullHtml.includes('class="species-placeholder-icon"'));

  // Case C: Unsafe XSS image URL -> Neutralized to placeholder
  const xssItem = {
    canonical_class: "xss",
    name_en: "Malicious",
    representative_image_url: "javascript:alert('xss')"
  };
  const xssHtml = renderMediaArea(xssItem);
  assert.ok(!xssHtml.includes('javascript:'));
  assert.ok(xssHtml.includes('class="species-placeholder-icon"'));
}
console.log("✓ Test 2 passed: Card media rendering simulation.");

// --- Test 3: Navigation Route Normalization ---
console.log("Running Test 3: Species navigation route verification...");
{
  function getSpeciesRoute(speciesId) {
    return `/species?id=${encodeURIComponent(speciesId.trim().toLowerCase())}`;
  }

  assert.strictEqual(getSpeciesRoute("apple"), "/species?id=apple");
  assert.strictEqual(getSpeciesRoute("Dragon Fruit"), "/species?id=dragon%20fruit");
  assert.strictEqual(getSpeciesRoute(" passion_fruit "), "/species?id=passion_fruit");
}
console.log("✓ Test 3 passed: Species navigation route verified.");

console.log("\n=======================================================");
console.log("ALL EXPLORE REPRESENTATIVE IMAGE TESTS PASSED (3/3)!");
console.log("=======================================================");

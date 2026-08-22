/**
 * Fruvia AI — Knowledge Utilities (knowledge-utils.js)
 * Pure, reusable helper functions for knowledge parsing, formatting,
 * error classification, and security sanitization.
 * Compatible with vanilla browser global and Node.js require() environments.
 */

(function (root, factory) {
  if (typeof module === "object" && typeof module.exports === "object") {
    // Node.js CommonJS environment
    module.exports = factory();
  } else {
    // Browser global environment
    root.KnowledgeUtils = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /**
   * Escape HTML special characters to prevent XSS.
   * @param {string} str - Raw untrusted text.
   * @returns {string} - Escaped HTML string.
   */
  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  /**
   * Safe URL protocol validator ensuring only http: and https: links are accepted.
   * Rejects javascript:, data:, file:, vbscript:, etc.
   * @param {string} url - Raw URL candidate.
   * @returns {string|null} - Normalized URL string or null if unsafe/invalid.
   */
  function getSafeSourceUrl(url) {
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
  }

  /**
   * Nutrient Amount Formatter:
   * STRICT FIDELITY: Returns exact raw amount without toFixed rounding or unit conversion.
   * e.g. 0.0859375 -> "0.0859375" (never 0.086)
   * @param {Object|number|string} valObj - Nutrient value object or scalar.
   * @returns {{ amountStr: string, unitStr: string }} - Formatted amount and unit.
   */
  function formatNutrientAmount(valObj) {
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
  }

  /**
   * Nutrient Basis Formatter:
   * STRICT INTEGRITY: Only renders a basis badge if metadata explicitly provides
   * structured nutrient_basis. Never fabricates "100g tiêu chuẩn" or infers from title/source.
   * @param {Object} doc - Knowledge document payload.
   * @returns {string} - Rendered badge HTML or empty string.
   */
  function getNutrientBasisHtml(doc) {
    const basis = doc?.metadata?.nutrient_basis;
    if (basis && typeof basis === "object") {
      const amount = basis.amount !== undefined && basis.amount !== null ? String(basis.amount) : "";
      const unit = basis.unit ? String(basis.unit) : "";
      const basisText = `${amount} ${unit}`.trim();
      if (basisText) {
        return `<span class="badge badge-neutral">${escapeHtml(basisText)} tiêu chuẩn</span>`;
      }
    }
    return "";
  }

  /**
   * Error Classifier:
   * Determines whether an error (or set of settled responses) represents a global
   * disabled knowledge service (HTTP 503 with errorCode "KNOWLEDGE_SERVICE_DISABLED").
   * @param {Object} error - Error object or rejected Promise reason.
   * @returns {boolean} - True if knowledge service is globally disabled.
   */
  function isKnowledgeServiceDisabled(error) {
    if (!error || typeof error !== "object") return false;
    return error.errorCode === "KNOWLEDGE_SERVICE_DISABLED";
  }

  /**
   * Aggregates settled knowledge query results into structured sections with partial
   * failure tracking and global disabled classification.
   * @param {Array<PromiseSettledResult>} settledResults - Array of settled query results: [overviewRes, taxonomyRes, nutritionRes]
   * @returns {{
   *   isGloballyDisabled: boolean,
   *   overview: Object|null,
   *   overviewErr: Object|null,
   *   taxonomy: Object|null,
   *   taxonomyErr: Object|null,
   *   nutrition: Object|null,
   *   nutritionErr: Object|null
   * }}
   */
  function processKnowledgeResponses([overviewRes, taxonomyRes, nutritionRes]) {
    const isGloballyDisabled =
      (overviewRes?.status === "rejected" && isKnowledgeServiceDisabled(overviewRes.reason)) ||
      (taxonomyRes?.status === "rejected" && isKnowledgeServiceDisabled(taxonomyRes.reason)) ||
      (nutritionRes?.status === "rejected" && isKnowledgeServiceDisabled(nutritionRes.reason));

    const overviewData = overviewRes?.status === "fulfilled" ? overviewRes.value : null;
    const overviewErr = overviewRes?.status === "rejected" ? overviewRes.reason : null;

    const taxonomyData = taxonomyRes?.status === "fulfilled" ? taxonomyRes.value : null;
    const taxonomyErr = taxonomyRes?.status === "rejected" ? taxonomyRes.reason : null;

    const nutritionData = nutritionRes?.status === "fulfilled" ? nutritionRes.value : null;
    const nutritionErr = nutritionRes?.status === "rejected" ? nutritionRes.reason : null;

    return {
      isGloballyDisabled,
      overview: overviewData,
      overviewErr,
      taxonomy: taxonomyData,
      taxonomyErr,
      nutrition: nutritionData,
      nutritionErr
    };
  }

  return {
    escapeHtml,
    getSafeSourceUrl,
    formatNutrientAmount,
    getNutrientBasisHtml,
    isKnowledgeServiceDisabled,
    processKnowledgeResponses
  };
});

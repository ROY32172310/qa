"""Browser-side probes.

The probes return facts. All thresholds and decisions stay in Python.
"""

from __future__ import annotations

COLLECT_JS = r"""
(cfg) => {
  const ignored = (el) => cfg.ignore.some(sel => {
    try { return el.closest(sel); } catch (_) { return false; }
  });
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width <= 2 || r.height <= 2) return false;
    if (st.display === "none" || st.visibility === "hidden") return false;
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const parentStyle = getComputedStyle(n);
      if (parentStyle.display === "none" || parentStyle.visibility === "hidden") return false;
      if (parseFloat(parentStyle.opacity || "1") < 0.05) return false;
    }
    return true;
  };
  const label = (el) => (
    el.getAttribute("aria-label") ||
    el.textContent ||
    el.value ||
    el.id ||
    el.tagName
  ).trim().replace(/\s+/g, " ").slice(0, 80);
  const controlSelector =
    "button,a[href],[role=button],input[type=submit],input[type=button],.btn,.cta";
  const controls = [...document.querySelectorAll(controlSelector)]
    .filter(el => visible(el) && !ignored(el) && !el.disabled &&
      el.getAttribute("aria-disabled") !== "true");
  const smallTargets = controls
    .map(el => {
      const r = el.getBoundingClientRect();
      return {label: label(el), width: Math.round(r.width), height: Math.round(r.height)};
    })
    .filter(x => x.width < cfg.minTap || x.height < cfg.minTap);
  const tinyFonts = [...document.querySelectorAll("*")]
    .filter(el => el.children.length === 0 && (el.textContent || "").trim() &&
      visible(el) && !ignored(el))
    .map(el => ({
      label: label(el).slice(0, 40),
      px: Number(parseFloat(getComputedStyle(el).fontSize).toFixed(2)),
    }))
    .filter(x => x.px > 0 && x.px < cfg.minFont);
  const hugeOverlays = [...document.querySelectorAll("body *")]
    .filter(el => {
      if (!visible(el) || ignored(el)) return false;
      const st = getComputedStyle(el);
      if (st.position !== "fixed") return false;
      if (el.matches("main,[role=main]")) return false;
      const r = el.getBoundingClientRect();
      return (r.width * r.height) / (innerWidth * innerHeight) > cfg.overlayRatio;
    })
    .map(el => ({label: String(el.className || el.id || el.tagName).slice(0, 60)}));
  const brokenImages = [...document.images]
    .filter(img => visible(img) && !ignored(img) && img.complete && img.naturalWidth === 0)
    .map(img => ({src: (img.currentSrc || img.src || "").slice(0, 180), alt: img.alt || ""}));
  const distortedMedia = [];
  for (const el of document.querySelectorAll("canvas,img,video")) {
    if (!visible(el) || ignored(el)) continue;
    const st = getComputedStyle(el);
    if (st.objectFit && st.objectFit !== "fill") continue;
    let nw = 0;
    let nh = 0;
    if (el.tagName === "CANVAS") {
      nw = el.width;
      nh = el.height;
    } else if (el.tagName === "IMG") {
      nw = el.naturalWidth;
      nh = el.naturalHeight;
    } else {
      nw = el.videoWidth || el.width;
      nh = el.videoHeight || el.height;
    }
    if (!nw || !nh) continue;
    const r = el.getBoundingClientRect();
    const natural = nw / nh;
    const shown = r.width / r.height;
    const deviation = Math.abs(shown - natural) / natural;
    if (deviation > cfg.aspectTolerance) {
      distortedMedia.push({
        label: label(el).slice(0, 40) || el.tagName.toLowerCase(),
        natural: [nw, nh],
        shown: [Math.round(r.width), Math.round(r.height)],
        deviation: Number(deviation.toFixed(3)),
      });
    }
  }
  return {
    title: document.title || "",
    url: location.href,
    viewport: {width: innerWidth, height: innerHeight},
    environment: {
      userAgent: navigator.userAgent,
      maxTouchPoints: navigator.maxTouchPoints || 0,
      coarsePointer: matchMedia("(pointer: coarse)").matches,
    },
    overflowX: Math.max(
      0,
      document.documentElement.scrollWidth - document.documentElement.clientWidth
    ),
    textLength: (document.body && document.body.innerText || "").trim().length,
    elementCount: document.querySelectorAll("body *").length,
    controlCount: controls.length,
    smallTargets,
    tinyFonts,
    hugeOverlays,
    brokenImages,
    distortedMedia,
  };
}
"""

ARM_LAYOUT_SHIFT_JS = r"""
(() => {
  const meter = {clip: 0, maxShift: 0, shifts: 0, supported: false};
  Object.defineProperty(window, "__webqa_layout_shift", {value: meter, configurable: true});
  try {
    const types = (window.PerformanceObserver && PerformanceObserver.supportedEntryTypes) || [];
    if (!types.includes("layout-shift")) return;
    meter.supported = true;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.hadRecentInput) continue;
        meter.clip += entry.value;
        meter.maxShift = Math.max(meter.maxShift, entry.value);
        meter.shifts += 1;
      }
    }).observe({type: "layout-shift", buffered: true});
  } catch (_) {}
})();
"""

READ_TIMING_JS = r"""
() => {
  const paints = performance.getEntriesByType("paint") || [];
  const fcp = paints.find(entry => entry.name === "first-contentful-paint");
  const shift = window.__webqa_layout_shift || null;
  return {
    firstContentfulPaintMs: fcp ? Math.round(fcp.startTime) : null,
    layoutShift: shift ? {
      supported: !!shift.supported,
      clip: Number(shift.clip || 0),
      maxShift: Number(shift.maxShift || 0),
      shifts: Number(shift.shifts || 0),
    } : null,
  };
}
"""

SMOKE_JS = r"""
async (cfg) => {
  const ignored = (el) => cfg.ignore.some(sel => {
    try { return el.closest(sel); } catch (_) { return false; }
  });
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.display !== "none" &&
      st.visibility !== "hidden" && parseFloat(st.opacity || "1") >= 0.05;
  };
  const state = () => ({
    htmlLength: document.body ? document.body.innerHTML.length : 0,
    elementCount: document.querySelectorAll("body *").length,
    textLength: document.body ? (document.body.innerText || "").trim().length : 0,
    fieldCount: document.querySelectorAll("input,select,textarea").length,
    dialogCount: document.querySelectorAll("[role=dialog],dialog[open]").length,
    url: location.href,
  });
  let target = null;
  let label = "";
  if (cfg.selector) {
    target = document.querySelector(cfg.selector);
    if (target && (!visible(target) || ignored(target))) target = null;
    label = target
      ? ((target.getAttribute("aria-label") || target.textContent || "").trim().slice(0, 60))
      : "";
  } else {
    const cta = new RegExp(cfg.ctaPattern, "i");
    const nav = new RegExp(cfg.navPattern, "i");
    const controls = [...document.querySelectorAll(
      "button,a[href],[role=button],input[type=submit],input[type=button],.btn,.cta"
    )].filter(el => visible(el) && !ignored(el) && !el.disabled);
    for (const el of controls) {
      const text = (
        el.getAttribute("aria-label") || el.textContent || el.value || ""
      ).trim().replace(/\s+/g, " ");
      if (text && cta.test(text) && !nav.test(text)) {
        target = el;
        label = text.slice(0, 60);
        break;
      }
    }
  }
  if (!target) return {found: false};
  const assertionResults = () => {
    const results = [];
    if (cfg.successSelector) {
      try {
        const successTarget = document.querySelector(cfg.successSelector);
        results.push({
          type: "selector",
          selector: cfg.successSelector,
          matched: !!(successTarget && visible(successTarget)),
        });
      } catch (err) {
        results.push({
          type: "selector",
          selector: cfg.successSelector,
          matched: false,
          error: String(err).slice(0, 160),
        });
      }
    }
    if (cfg.successUrlPattern) {
      try {
        const successUrl = new RegExp(cfg.successUrlPattern, "i");
        results.push({
          type: "url",
          pattern: cfg.successUrlPattern,
          matched: successUrl.test(location.href),
          url: location.href,
        });
      } catch (err) {
        results.push({
          type: "url",
          pattern: cfg.successUrlPattern,
          matched: false,
          error: String(err).slice(0, 160),
        });
      }
    }
    return results;
  };
  const assertionsBefore = assertionResults();
  const before = state();
  let clickError = "";
  try {
    target.click();
  } catch (err) {
    clickError = String(err).slice(0, 240);
  }
  await new Promise(resolve => setTimeout(resolve, cfg.settleMs));
  const after = state();
  const changed = (
    before.htmlLength !== after.htmlLength ||
    before.elementCount !== after.elementCount ||
    before.textLength !== after.textLength ||
    before.fieldCount !== after.fieldCount ||
    before.dialogCount !== after.dialogCount ||
    before.url !== after.url
  );
  const assertions = assertionResults().map((result, index) => ({
    ...result,
    matchedBefore: !!assertionsBefore[index].matched,
    matchedAfter: !!result.matched,
    matched: !!result.matched && !assertionsBefore[index].matched,
  }));
  const assertionConfigured = assertions.length > 0;
  const assertionMatched = assertionConfigured
    ? assertions.every(assertion => assertion.matched)
    : null;
  return {
    found: true,
    label,
    changed,
    assertions,
    assertionConfigured,
    assertionMatched,
    clickError,
    before,
    after,
  };
}
"""

SMOKE_ASSERTIONS_JS = r"""
(cfg) => {
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 2 && rect.height > 2 && style.display !== "none" &&
      style.visibility !== "hidden" && parseFloat(style.opacity || "1") >= 0.05;
  };
  const results = [];
  if (cfg.successSelector) {
    try {
      const target = document.querySelector(cfg.successSelector);
      results.push({
        type: "selector",
        selector: cfg.successSelector,
        matched: !!(target && visible(target)),
      });
    } catch (err) {
      results.push({
        type: "selector",
        selector: cfg.successSelector,
        matched: false,
        error: String(err).slice(0, 160),
      });
    }
  }
  if (cfg.successUrlPattern) {
    try {
      const pattern = new RegExp(cfg.successUrlPattern, "i");
      results.push({
        type: "url",
        pattern: cfg.successUrlPattern,
        matched: pattern.test(location.href),
        url: location.href,
      });
    } catch (err) {
      results.push({
        type: "url",
        pattern: cfg.successUrlPattern,
        matched: false,
        error: String(err).slice(0, 160),
      });
    }
  }
  return results;
}
"""

ACCESSIBILITY_JS = r"""
() => {
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (rect.width <= 2 || rect.height <= 2) return false;
    if (style.display === "none" || style.visibility === "hidden") return false;
    if (parseFloat(style.opacity || "1") < 0.05) return false;
    for (let node = el.parentElement; node && node !== document.documentElement;
      node = node.parentElement) {
      const parentStyle = getComputedStyle(node);
      if (parentStyle.display === "none" || parentStyle.visibility === "hidden") return false;
      if (parseFloat(parentStyle.opacity || "1") < 0.05) return false;
    }
    return true;
  };
  const accessibleText = (el) => {
    let text = "";
    for (const node of [...el.childNodes]) {
      if (node.nodeType === Node.TEXT_NODE) {
        text += node.nodeValue || "";
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const child = node;
        if (child.getAttribute("aria-hidden") === "true") continue;
        const style = getComputedStyle(child);
        if (style.display === "none" || style.visibility === "hidden") continue;
        if (child.tagName === "IMG" && child.alt) {
          text += ` ${child.alt} `;
          continue;
        }
        text += accessibleText(child);
      }
    }
    return text.replace(/\s+/g, " ").trim();
  };
  const idText = (ids) => ids
    .split(/\s+/)
    .map(id => document.getElementById(id))
    .filter(Boolean)
    .map(accessibleText)
    .filter(Boolean)
    .join(" ");
  const accessibleName = (el) => {
    const ariaLabel = (el.getAttribute("aria-label") || "").trim();
    if (ariaLabel) return ariaLabel;
    const labelledBy = (el.getAttribute("aria-labelledby") || "").trim();
    if (labelledBy && idText(labelledBy)) return idText(labelledBy);
    if (el.labels && el.labels.length) {
      const labelText = [...el.labels].map(accessibleText).filter(Boolean).join(" ");
      if (labelText) return labelText;
    }
    if (el.tagName === "IMG" && el.alt) return el.alt.trim();
    if (["submit", "button", "reset"].includes((el.type || "").toLowerCase()) && el.value) {
      return String(el.value).trim();
    }
    const text = accessibleText(el);
    if (text) return text;
    return (el.getAttribute("title") || "").trim();
  };
  const label = (el) => (
    accessibleName(el) || el.id || el.getAttribute("name") || el.tagName.toLowerCase()
  ).slice(0, 80);
  const focusableSelector =
    "a[href],button,input:not([type=hidden]),select,textarea,[tabindex],[contenteditable=true]";
  const controls = [...document.querySelectorAll(
    "a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=link]"
  )].filter(visible);
  const missingNames = controls
    .filter(el => !accessibleName(el))
    .map(el => ({tag: el.tagName.toLowerCase(), label: label(el)}));
  const imagesMissingAlt = [...document.images]
    .filter(img => visible(img) && !img.hasAttribute("alt"))
    .map(img => ({src: (img.currentSrc || img.src || "").slice(0, 180)}));
  const idCounts = new Map();
  for (const el of document.querySelectorAll("[id]")) {
    const id = el.id;
    if (!id) continue;
    idCounts.set(id, (idCounts.get(id) || 0) + 1);
  }
  const duplicateIds = [...idCounts.entries()]
    .filter(([, count]) => count > 1)
    .map(([id, count]) => ({id, count}));
  const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")]
    .filter(visible)
    .map(el => ({
      level: Number(el.tagName.slice(1)),
      label: accessibleText(el).slice(0, 80),
    }));
  const headingSkips = [];
  for (let index = 1; index < headings.length; index += 1) {
    if (headings[index].level > headings[index - 1].level + 1) {
      headingSkips.push({
        from: headings[index - 1].level,
        to: headings[index].level,
        label: headings[index].label,
      });
    }
  }
  const positiveTabindex = [...document.querySelectorAll("[tabindex]")]
    .filter(visible)
    .map(el => ({tabindex: Number(el.getAttribute("tabindex")), label: label(el)}))
    .filter(item => Number.isFinite(item.tabindex) && item.tabindex > 0);
  const hiddenFocusable = [...document.querySelectorAll(focusableSelector)]
    .filter(el => visible(el) && el.closest("[aria-hidden=true]"))
    .map(el => ({label: label(el)}));
  return {
    lang: (document.documentElement.lang || "").trim(),
    title: (document.title || "").trim(),
    missingNames,
    imagesMissingAlt,
    duplicateIds,
    headingSkips,
    positiveTabindex,
    hiddenFocusable,
  };
}
"""

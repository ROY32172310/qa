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
  return {found: true, label, changed, clickError, before, after};
}
"""

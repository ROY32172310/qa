"""Browser-side probes.

The probes return facts. All thresholds and decisions stay in Python.
"""

from __future__ import annotations

COLLECT_JS = r"""
(cfg) => {
  const documentRoot = document.documentElement;
  const documentBody = document.body;
  if (!documentRoot || !documentBody) return null;
  const layoutWidth = documentRoot.clientWidth || window.innerWidth;
  const composedParent = (el) => {
    if (!el) return null;
    if (el.parentElement) return el.parentElement;
    const root = el.getRootNode && el.getRootNode();
    return root && root.host ? root.host : null;
  };
  const allElements = (selector, root = document) => {
    const found = [];
    const visit = (scope) => {
      for (const el of scope.children) {
        try {
          if (el.matches(selector)) found.push(el);
        } catch (_) {}
        if (el.shadowRoot) visit(el.shadowRoot);
        visit(el);
      }
    };
    visit(root);
    return found;
  };
  const composedText = (root) => {
    let text = "";
    const addDirectText = (el) => {
      for (const node of el.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) text += node.nodeValue || "";
      }
    };
    addDirectText(root);
    const visit = (scope) => {
      for (const el of scope.children) {
        addDirectText(el);
        if (el.shadowRoot) visit(el.shadowRoot);
        visit(el);
      }
    };
    visit(root);
    return text;
  };
  const composedClosest = (el, selector) => {
    for (let node = el; node; node = composedParent(node)) {
      try {
        if (node.matches && node.matches(selector)) return node;
      } catch (_) {
        return null;
      }
    }
    return null;
  };
  const ignored = (el) => cfg.ignore.some(sel => composedClosest(el, sel));
  const cssEscape = (value) => (
    window.CSS && CSS.escape
      ? CSS.escape(String(value))
      : String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&")
  );
  const selectorFor = (el) => {
    if (!el || !el.tagName) return "";
    if (el.id) return "#" + cssEscape(el.id);
    const testId = el.getAttribute("data-testid");
    if (testId) return '[data-testid="' + String(testId).replace(/"/g, '\\"') + '"]';
    const parts = [];
    for (let node = el; node && node.nodeType === 1 && node !== documentRoot;
      node = composedParent(node)) {
      let part = node.tagName.toLowerCase();
      const treeParent = node.parentElement || (
        node.getRootNode && node.getRootNode().children ? node.getRootNode() : null
      );
      if (treeParent) {
        const same = [...treeParent.children].filter(child => child.tagName === node.tagName);
        if (same.length > 1) part += ":nth-of-type(" + (same.indexOf(node) + 1) + ")";
      }
      parts.unshift(part);
      if (node.id) {
        parts[0] = "#" + cssEscape(node.id);
        break;
      }
      if (parts.length >= 6) break;
    }
    return parts.join(" > ");
  };
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return {
      x: Math.round(r.x),
      y: Math.round(r.y),
      width: Math.round(r.width),
      height: Math.round(r.height),
    };
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width <= 2 || r.height <= 2) return false;
    if (st.display === "none" || st.visibility === "hidden") return false;
    for (let n = el; n && n !== documentRoot; n = composedParent(n)) {
      const parentStyle = getComputedStyle(n);
      if (parentStyle.display === "none" || parentStyle.visibility === "hidden") return false;
      if (parseFloat(parentStyle.opacity || "1") < 0.05) return false;
    }
    return true;
  };
  const declaresSafeAreaBottom = (el) => {
    const pattern = /env\s*\(\s*safe-area-inset-bottom/i;
    if (pattern.test(el.getAttribute("style") || "")) return true;
    for (const sheet of [...document.styleSheets]) {
      let rules;
      try {
        rules = sheet.cssRules;
      } catch (_) {
        continue;
      }
      const inspect = (items) => {
        for (const rule of items || []) {
          if (rule.cssRules && rule.cssRules.length) {
            if (inspect(rule.cssRules)) return true;
            continue;
          }
          if (!rule.selectorText || !pattern.test(rule.style.cssText || "")) continue;
          try {
            if (el.matches(rule.selectorText)) return true;
          } catch (_) {}
        }
        return false;
      };
      if (inspect(rules)) return true;
    }
    return false;
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
  const clippedByAncestor = (el) => {
    for (let node = composedParent(el); node && node !== documentBody;
      node = composedParent(node)) {
      const overflowX = getComputedStyle(node).overflowX;
      if (["hidden", "clip", "auto", "scroll"].includes(overflowX)) return true;
    }
    return false;
  };
  const overflowingElements = allElements("*")
    .filter(el => !el.matches("html,body") && visible(el) && !ignored(el) &&
      !clippedByAncestor(el))
    .map(el => {
      const r = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      let left = r.left;
      let right = r.right;
      let top = r.top;
      let bottom = r.bottom;
      for (const node of el.childNodes) {
        if (node.nodeType !== Node.TEXT_NODE || !(node.nodeValue || "").trim()) continue;
        try {
          const range = document.createRange();
          range.selectNodeContents(node);
          const textRect = range.getBoundingClientRect();
          left = Math.min(left, textRect.left);
          right = Math.max(right, textRect.right);
          top = Math.min(top, textRect.top);
          bottom = Math.max(bottom, textRect.bottom);
        } catch (_) {}
      }
      const rightOverflow = Math.max(0, right - layoutWidth);
      const leftOverflow = Math.max(0, -left);
      return {
        label: label(el).slice(0, 60),
        selector: selectorFor(el),
        box: {
          x: Math.round(left),
          y: Math.round(top),
          width: Math.round(right - left),
          height: Math.round(bottom - top),
        },
        right_overflow_px: Number(rightOverflow.toFixed(1)),
        left_overflow_px: Number(leftOverflow.toFixed(1)),
        overflow_px: Number(Math.max(leftOverflow, rightOverflow).toFixed(1)),
        position: style.position,
      };
    })
    .filter(row => row.overflow_px > cfg.overflowTolerance &&
      row.position !== "fixed")
    .sort((a, b) => b.overflow_px - a.overflow_px ||
      b.selector.length - a.selector.length)
    .slice(0, 5);
  const controls = allElements(controlSelector)
    .filter(el => visible(el) && !ignored(el) && !el.disabled &&
      el.getAttribute("aria-disabled") !== "true");
  const smallTargets = controls
    .map(el => {
      const r = el.getBoundingClientRect();
      return {
        label: label(el),
        selector: selectorFor(el),
        width: Math.round(r.width),
        height: Math.round(r.height),
        box: box(el),
      };
    })
    .filter(x => x.width < cfg.minTap || x.height < cfg.minTap);
  const tinyFonts = allElements("*")
    .filter(el => el.children.length === 0 && (el.textContent || "").trim() &&
      visible(el) && !ignored(el))
    .map(el => ({
      label: label(el).slice(0, 40),
      selector: selectorFor(el),
      px: Number(parseFloat(getComputedStyle(el).fontSize).toFixed(2)),
    }))
    .filter(x => x.px > 0 && x.px < cfg.minFont);
  const hugeOverlays = [];
  for (const el of allElements("*")) {
    if (!visible(el) || ignored(el)) continue;
    const st = getComputedStyle(el);
    if (st.position !== "fixed") continue;
    if (el.matches("main,[role=main]")) continue;
    const r = el.getBoundingClientRect();
    const coveredWidth = Math.max(0, Math.min(innerWidth, r.right) - Math.max(0, r.left));
    const coveredHeight = Math.max(0, Math.min(innerHeight, r.bottom) - Math.max(0, r.top));
    const coverage = (coveredWidth * coveredHeight) / (innerWidth * innerHeight);
    if (coverage > cfg.overlayRatio) {
      hugeOverlays.push({
        label: String(el.className || el.id || el.tagName).slice(0, 60),
        selector: selectorFor(el),
        box: box(el),
        coverage: Number(coverage.toFixed(3)),
      });
    }
  }
  const safeAreaPenetrations = [];
  if (cfg.safeBottom > 0) {
    for (const el of allElements("*")) {
      if (!visible(el) || ignored(el)) continue;
      if (el.matches("html,body,main,[role=main]")) continue;
      const style = getComputedStyle(el);
      if (style.position !== "fixed" && style.position !== "sticky") continue;
      const r = el.getBoundingClientRect();
      if (r.width < innerWidth * 0.45 || r.height < 24) continue;
      if (r.bottom <= 0 || r.top >= innerHeight) continue;
      const gap = Math.max(0, innerHeight - r.bottom);
      if (gap >= cfg.safeBottom) continue;
      if (parseFloat(style.paddingBottom || "0") >= cfg.safeBottom) continue;
      let nestedInBottomLayer = false;
      for (let node = composedParent(el); node; node = composedParent(node)) {
        const parentStyle = getComputedStyle(node);
        if (parentStyle.position === "fixed" || parentStyle.position === "sticky") {
          const parentRect = node.getBoundingClientRect();
          if (parentRect.height >= 24 && parentRect.bottom > innerHeight - cfg.safeBottom) {
            nestedInBottomLayer = true;
            break;
          }
        }
      }
      if (nestedInBottomLayer || declaresSafeAreaBottom(el)) continue;
      safeAreaPenetrations.push({
        label: label(el).slice(0, 60),
        selector: selectorFor(el),
        box: box(el),
        bottom_gap_px: Math.round(gap),
        required_gap_px: cfg.safeBottom,
        position: style.position,
      });
    }
  }
  const clippedText = [];
  for (const el of allElements("*")) {
    if (!visible(el) || ignored(el) || composedClosest(el, "[aria-hidden=true]")) continue;
    const textNodes = [...el.childNodes].filter(node =>
      node.nodeType === Node.TEXT_NODE && (node.nodeValue || "").trim().length >= 2
    );
    if (!textNodes.length) continue;
    const elementRect = el.getBoundingClientRect();
    if (
      elementRect.width <= 2 ||
      elementRect.height <= 2 ||
      elementRect.right <= 0 ||
      elementRect.left >= innerWidth ||
      elementRect.bottom <= 0 ||
      elementRect.top >= innerHeight
    ) continue;
    for (const textNode of textNodes) {
      let textRect;
      try {
        const range = document.createRange();
        range.selectNodeContents(textNode);
        textRect = range.getBoundingClientRect();
      } catch (_) {
        continue;
      }
      if (
        textRect.width <= 0 ||
        textRect.height <= 0 ||
        textRect.right <= 0 ||
        textRect.left >= innerWidth ||
        textRect.bottom <= 0 ||
        textRect.top >= innerHeight
      ) continue;
      for (
        let clipper = el;
        clipper && clipper !== documentRoot;
        clipper = composedParent(clipper)
      ) {
        const clipStyle = getComputedStyle(clipper);
        const overflowX = clipStyle.overflowX;
        const overflowY = clipStyle.overflowY;
        const scrollsX = ["auto", "scroll"].includes(overflowX) &&
          clipper.scrollWidth > clipper.clientWidth + 1;
        const scrollsY = ["auto", "scroll"].includes(overflowY) &&
          clipper.scrollHeight > clipper.clientHeight + 1;
        if (scrollsX || scrollsY) break;
        const clipsX = ["hidden", "clip"].includes(overflowX);
        const clipsY = ["hidden", "clip"].includes(overflowY);
        if (!clipsX && !clipsY) continue;
        const lineClamp = (
          clipStyle.getPropertyValue("-webkit-line-clamp") ||
          clipStyle.getPropertyValue("line-clamp") ||
          "none"
        ).trim();
        if (clipsX && clipStyle.textOverflow === "ellipsis") break;
        if (lineClamp !== "none" && lineClamp !== "0") break;
        const clipperRect = clipper.getBoundingClientRect();
        const left = clipperRect.left + (parseFloat(clipStyle.borderLeftWidth) || 0);
        const right = clipperRect.right - (parseFloat(clipStyle.borderRightWidth) || 0);
        const top = clipperRect.top + (parseFloat(clipStyle.borderTopWidth) || 0);
        const bottom = clipperRect.bottom - (parseFloat(clipStyle.borderBottomWidth) || 0);
        const horizontalClip = clipsX
          ? Math.max(0, left - textRect.left, textRect.right - right)
          : 0;
        const verticalClip = clipsY
          ? Math.max(0, top - textRect.top, textRect.bottom - bottom)
          : 0;
        if (horizontalClip <= 0.1 && verticalClip <= 0.1) continue;
        clippedText.push({
          label: (textNode.nodeValue || "").trim().replace(/\s+/g, " ").slice(0, 48),
          selector: selectorFor(el),
          clipped_by: selectorFor(clipper),
          box: box(el),
          text_box: {
            x: Math.round(textRect.x),
            y: Math.round(textRect.y),
            width: Math.round(textRect.width),
            height: Math.round(textRect.height),
          },
          horizontal_clip_px: Number(horizontalClip.toFixed(1)),
          vertical_clip_px: Number(verticalClip.toFixed(1)),
          clip_px: Number(Math.max(horizontalClip, verticalClip).toFixed(1)),
        });
        break;
      }
    }
  }
  const brokenImages = allElements("img")
    .filter(img => visible(img) && !ignored(img) && img.complete && img.naturalWidth === 0)
    .map(img => ({
      src: (img.currentSrc || img.src || "").slice(0, 180),
      alt: img.alt || "",
      selector: selectorFor(img),
      box: box(img),
    }));
  const distortedMedia = [];
  for (const el of allElements("canvas,img,video")) {
    if (!visible(el) || ignored(el)) continue;
    const r = el.getBoundingClientRect();
    if (Math.min(r.width, r.height) < cfg.aspectMinPx) continue;
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
    const natural = nw / nh;
    const shown = r.width / r.height;
    const deviation = Math.abs(shown - natural) / natural;
    if (deviation > cfg.aspectTolerance) {
      distortedMedia.push({
        label: label(el).slice(0, 40) || el.tagName.toLowerCase(),
        selector: selectorFor(el),
        natural: [nw, nh],
        shown: [Math.round(r.width), Math.round(r.height)],
        box: box(el),
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
      documentRoot.scrollWidth - documentRoot.clientWidth
    ),
    textLength: composedText(documentBody).trim().length,
    elementCount: allElements("*", documentBody).length,
    controlCount: controls.length,
    smallTargets,
    tinyFonts,
    hugeOverlays,
    overflowingElements,
    safeAreaPenetrations: safeAreaPenetrations.slice(0, 10),
    clippedText: clippedText.slice(0, 20),
    brokenImages,
    distortedMedia,
  };
}
"""

TEXT_SCALE_JS = r"""
(scale) => {
  const requested = Number(scale);
  if (!Number.isFinite(requested) || requested <= 1) {
    return {applied: false, textScale: 1, scaledElements: 0};
  }
  if (window.__ego_webqa_text_scale === requested) {
    return {applied: true, textScale: requested, scaledElements: 0, reused: true};
  }
  const documentRoot = document.documentElement;
  if (!documentRoot) {
    return {applied: false, textScale: 1, scaledElements: 0};
  }
  const elements = [...document.querySelectorAll("*")];
  const originals = new Map();
  for (const el of elements) {
    if (["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(el.tagName)) continue;
    const size = Number.parseFloat(getComputedStyle(el).fontSize);
    if (Number.isFinite(size) && size > 0) originals.set(el, size);
  }
  let scaledElements = 0;
  for (const [el, size] of originals) {
    el.style.setProperty("font-size", `${size * requested}px`, "important");
    scaledElements += 1;
  }
  window.__ego_webqa_text_scale = requested;
  documentRoot.dataset.egoWebqaTextScale = String(requested);
  return {applied: true, textScale: requested, scaledElements};
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
  const composedParent = (el) => {
    if (!el) return null;
    if (el.parentElement) return el.parentElement;
    const root = el.getRootNode && el.getRootNode();
    return root && root.host ? root.host : null;
  };
  const allElements = (selector, root = document) => {
    const found = [];
    const visit = (scope) => {
      for (const el of scope.children) {
        try {
          if (el.matches(selector)) found.push(el);
        } catch (_) {}
        if (el.shadowRoot) visit(el.shadowRoot);
        visit(el);
      }
    };
    visit(root);
    return found;
  };
  const composedClosest = (el, selector) => {
    for (let node = el; node; node = composedParent(node)) {
      try {
        if (node.matches && node.matches(selector)) return node;
      } catch (_) {
        return null;
      }
    }
    return null;
  };
  const ignored = (el) => cfg.ignore.some(sel => composedClosest(el, sel));
  const composedText = (root) => {
    let text = "";
    const addDirectText = (el) => {
      for (const node of el.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) text += node.nodeValue || "";
      }
    };
    addDirectText(root);
    const visit = (scope) => {
      for (const el of scope.children) {
        addDirectText(el);
        if (el.shadowRoot) visit(el.shadowRoot);
        visit(el);
      }
    };
    visit(root);
    return text;
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.display !== "none" &&
      st.visibility !== "hidden" && parseFloat(st.opacity || "1") >= 0.05;
  };
  const state = () => ({
    htmlLength: document.body ? document.body.innerHTML.length : 0,
    elementCount: document.body ? allElements("*", document.body).length : 0,
    textLength: document.body ? composedText(document.body).trim().length : 0,
    fieldCount: allElements("input,select,textarea").length,
    dialogCount: allElements("[role=dialog],dialog[open]").length,
    url: location.href,
  });
  let target = null;
  let label = "";
  if (cfg.selector) {
    target = allElements(cfg.selector).find(el => visible(el) && !ignored(el)) || null;
    if (target && (!visible(target) || ignored(target))) target = null;
    label = target
      ? ((target.getAttribute("aria-label") || target.textContent || "").trim().slice(0, 60))
      : "";
  } else {
    const cta = new RegExp(cfg.ctaPattern, "i");
    const nav = new RegExp(cfg.navPattern, "i");
    const controls = allElements(
      "button,a[href],[role=button],input[type=submit],input[type=button],.btn,.cta"
    ).filter(el => visible(el) && !ignored(el) && !el.disabled);
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
        const successTarget = allElements(cfg.successSelector).find(visible) || null;
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
  const allElements = (selector, root = document) => {
    const found = [];
    const visit = (scope) => {
      for (const el of scope.children) {
        try {
          if (el.matches(selector)) found.push(el);
        } catch (_) {}
        if (el.shadowRoot) visit(el.shadowRoot);
        visit(el);
      }
    };
    visit(root);
    return found;
  };
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 2 && rect.height > 2 && style.display !== "none" &&
      style.visibility !== "hidden" && parseFloat(style.opacity || "1") >= 0.05;
  };
  const results = [];
  if (cfg.successSelector) {
    try {
      const target = allElements(cfg.successSelector).find(visible) || null;
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
  const composedParent = (el) => {
    if (!el) return null;
    if (el.parentElement) return el.parentElement;
    const root = el.getRootNode && el.getRootNode();
    return root && root.host ? root.host : null;
  };
  const allElements = (selector, root = document) => {
    const found = [];
    const visit = (scope) => {
      for (const el of scope.children) {
        try {
          if (el.matches(selector)) found.push(el);
        } catch (_) {}
        if (el.shadowRoot) visit(el.shadowRoot);
        visit(el);
      }
    };
    visit(root);
    return found;
  };
  const composedClosest = (el, selector) => {
    for (let node = el; node; node = composedParent(node)) {
      try {
        if (node.matches && node.matches(selector)) return node;
      } catch (_) {
        return null;
      }
    }
    return null;
  };
  const cssEscape = (value) => (
    window.CSS && CSS.escape
      ? CSS.escape(String(value))
      : String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&")
  );
  const selectorFor = (el) => {
    if (!el || !el.tagName) return "";
    if (el.id) return "#" + cssEscape(el.id);
    const testId = el.getAttribute("data-testid");
    if (testId) return '[data-testid="' + String(testId).replace(/"/g, '\\"') + '"]';
    const parts = [];
    for (let node = el; node && node.nodeType === 1 && node !== document.documentElement;
      node = composedParent(node)) {
      let part = node.tagName.toLowerCase();
      const treeParent = node.parentElement || (
        node.getRootNode && node.getRootNode().children ? node.getRootNode() : null
      );
      if (treeParent) {
        const same = [...treeParent.children].filter(child => child.tagName === node.tagName);
        if (same.length > 1) part += ":nth-of-type(" + (same.indexOf(node) + 1) + ")";
      }
      parts.unshift(part);
      if (node.id) {
        parts[0] = "#" + cssEscape(node.id);
        break;
      }
      if (parts.length >= 6) break;
    }
    return parts.join(" > ");
  };
  const rootLabels = new WeakMap();
  let rootSequence = 0;
  const rootLabel = (root) => {
    if (root === document) return "document";
    if (!rootLabels.has(root)) {
      rootSequence += 1;
      rootLabels.set(root, "shadow-" + rootSequence);
    }
    return rootLabels.get(root);
  };
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (rect.width <= 2 || rect.height <= 2) return false;
    if (style.display === "none" || style.visibility === "hidden") return false;
    if (parseFloat(style.opacity || "1") < 0.05) return false;
    for (let node = composedParent(el); node && node !== document.documentElement;
      node = composedParent(node)) {
      const parentStyle = getComputedStyle(node);
      if (parentStyle.display === "none" || parentStyle.visibility === "hidden") return false;
      if (parseFloat(parentStyle.opacity || "1") < 0.05) return false;
    }
    return true;
  };
  const accessibleText = (el, seen = new Set()) => {
    if (!el || seen.has(el)) return "";
    seen.add(el);
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
        text += accessibleText(child, seen);
      }
    }
    if (el.shadowRoot) text += accessibleText(el.shadowRoot, seen);
    return text.replace(/\s+/g, " ").trim();
  };
  const byId = (origin, id) => {
    const root = origin.getRootNode ? origin.getRootNode() : document;
    if (root.getElementById) return root.getElementById(id);
    return allElements("#" + cssEscape(id), root)[0] || null;
  };
  const idText = (origin, ids) => ids
    .split(/\s+/)
    .map(id => byId(origin, id))
    .filter(Boolean)
    .map(accessibleText)
    .filter(Boolean)
    .join(" ");
  const accessibleName = (el) => {
    const ariaLabel = (el.getAttribute("aria-label") || "").trim();
    if (ariaLabel) return ariaLabel;
    const labelledBy = (el.getAttribute("aria-labelledby") || "").trim();
    if (labelledBy && idText(el, labelledBy)) return idText(el, labelledBy);
    if (el.labels && el.labels.length) {
      const labelText = [...el.labels]
        .map(labelElement => accessibleText(labelElement))
        .filter(Boolean)
        .join(" ");
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
  const controls = allElements(
    "a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=link]"
  ).filter(visible);
  const missingNames = controls
    .filter(el => !accessibleName(el))
    .map(el => ({
      tag: el.tagName.toLowerCase(),
      label: label(el),
      selector: selectorFor(el),
    }));
  const imagesMissingAlt = allElements("img")
    .filter(img => visible(img) && !img.hasAttribute("alt"))
    .map(img => ({
      src: (img.currentSrc || img.src || "").slice(0, 180),
      selector: selectorFor(img),
    }));
  const idCounts = new Map();
  for (const el of allElements("[id]")) {
    const id = el.id;
    if (!id) continue;
    const scope = rootLabel(el.getRootNode());
    const key = scope + "\u0000" + id;
    const current = idCounts.get(key) || {id, scope, count: 0};
    current.count += 1;
    idCounts.set(key, current);
  }
  const duplicateIds = [...idCounts.values()]
    .filter(item => item.count > 1);
  const headings = allElements("h1,h2,h3,h4,h5,h6")
    .filter(visible)
    .map(el => ({
      level: Number(el.tagName.slice(1)),
      label: accessibleText(el).slice(0, 80),
      selector: selectorFor(el),
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
  const positiveTabindex = allElements("[tabindex]")
    .filter(visible)
    .map(el => ({
      tabindex: Number(el.getAttribute("tabindex")),
      label: label(el),
      selector: selectorFor(el),
    }))
    .filter(item => Number.isFinite(item.tabindex) && item.tabindex > 0);
  const hiddenFocusable = allElements(focusableSelector)
    .filter(el => visible(el) && composedClosest(el, "[aria-hidden=true]"))
    .map(el => ({label: label(el), selector: selectorFor(el)}));
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

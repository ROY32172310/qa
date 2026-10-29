(() => {
  "use strict";

  const variants = {
    "mobile-360-100-safe0": {
      label: "360 × 800 · 1.0× text · 0px safe area",
      before:
        "The page fits this viewport, but the missing service worker still logs a blocking console error.",
      after:
        "The console is clean and the page fits. Only the 710KB transfer warning remains.",
    },
    "mobile-360-100-safe34": {
      label: "360 × 800 · 1.0× text · 34px safe area",
      before:
        "The page fits this viewport, but the missing service worker still logs a blocking console error.",
      after:
        "The console is clean and the bottom controls respect the simulated safe area.",
    },
    "mobile-360-150-safe0": {
      label: "360 × 800 · 1.5× text · 0px safe area",
      before:
        "At 1.5× text, the page is 5px wider than the viewport. The service worker also fails.",
      after:
        "The bottom controls wrap inside 360px, and the service worker error is gone.",
    },
    "mobile-360-150-safe34": {
      label: "360 × 800 · 1.5× text · 34px safe area",
      before:
        "1.5× text makes the page 5px wider than a 360px viewport. The service worker fails in all eight variants.",
      after:
        "The bottom controls wrap inside the viewport. The service worker error is gone. Only the 710KB transfer warning remains.",
    },
    "mobile-390-100-safe0": {
      label: "390 × 844 · 1.0× text · 0px safe area",
      before:
        "The page fits this viewport, but the missing service worker still logs a blocking console error.",
      after:
        "The console is clean and the page fits. Only the 710KB transfer warning remains.",
    },
    "mobile-390-100-safe34": {
      label: "390 × 844 · 1.0× text · 34px safe area",
      before:
        "The page fits this viewport, but the missing service worker still logs a blocking console error.",
      after:
        "The console is clean and the bottom controls respect the simulated safe area.",
    },
    "mobile-390-150-safe0": {
      label: "390 × 844 · 1.5× text · 0px safe area",
      before:
        "Text enlarges without horizontal overflow here, but the missing service worker remains a blocking console error.",
      after:
        "The console is clean, the enlarged text fits, and only the transfer warning remains.",
    },
    "mobile-390-150-safe34": {
      label: "390 × 844 · 1.5× text · 34px safe area",
      before:
        "Text enlarges without horizontal overflow here, but the missing service worker remains a blocking console error.",
      after:
        "The console is clean, enlarged text fits, and the bottom controls respect the simulated safe area.",
    },
  };

  const controls = Array.from(
    document.querySelectorAll("[data-variant]"),
  );
  const beforeImage = document.querySelector("#before-image");
  const afterImage = document.querySelector("#after-image");
  const beforeDetail = document.querySelector("#before-detail");
  const afterDetail = document.querySelector("#after-detail");
  const selectedVariant = document.querySelector("#selected-variant");
  const showFailure = document.querySelector("#show-failure");
  const evidence = document.querySelector("#evidence");

  function selectVariant(name) {
    const variant = variants[name];
    if (!variant) {
      return;
    }

    for (const control of controls) {
      const active = control.dataset.variant === name;
      control.classList.toggle("is-active", active);
      control.setAttribute("aria-pressed", String(active));
    }

    beforeImage.src = `assets/before/${name}.png`;
    afterImage.src = `assets/after/${name}.png`;
    beforeImage.alt = `Before repair: generated vocabulary page at ${variant.label}.`;
    afterImage.alt = `After repair: vocabulary page at ${variant.label}, with controls kept inside the viewport.`;
    beforeDetail.textContent = variant.before;
    afterDetail.textContent = variant.after;
    selectedVariant.textContent = variant.label;
  }

  for (const control of controls) {
    control.addEventListener("click", () => {
      selectVariant(control.dataset.variant);
    });
  }

  showFailure.addEventListener("click", () => {
    selectVariant("mobile-360-150-safe34");
    showFailure.textContent = "已显示失败组合 / Showing failing variant";
    evidence.scrollIntoView({ behavior: "smooth", block: "start" });
    document
      .querySelector('[data-variant="mobile-360-150-safe34"]')
      .focus({ preventScroll: true });
  });
})();

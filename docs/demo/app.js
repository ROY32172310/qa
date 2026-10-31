(() => {
  "use strict";

  const controls = Array.from(document.querySelectorAll("[data-case]"));
  const caseLink = document.querySelector("#case-link");
  const caseTitle = document.querySelector("#case-title");
  const beforeVerdict = document.querySelector("#before-verdict");
  const afterVerdict = document.querySelector("#after-verdict");
  const heroBeforeStatus = document.querySelector("#hero-before-status");
  const heroAfterStatus = document.querySelector("#hero-after-status");
  const findingDimension = document.querySelector("#finding-dimension");
  const findingMeasure = document.querySelector("#finding-measure");
  const findingSelector = document.querySelector("#finding-selector");
  const findingTrigger = document.querySelector("#finding-trigger");
  const beforeCaption = document.querySelector("#before-caption");
  const afterCaption = document.querySelector("#after-caption");
  const reproduceCommand = document.querySelector("#reproduce-command");

  const images = {
    heroBefore: document.querySelector("#hero-before-image"),
    heroAfter: document.querySelector("#hero-after-image"),
    caseBefore: document.querySelector("#case-before-image"),
    caseAfter: document.querySelector("#case-after-image"),
  };

  function displayCase(item) {
    const scenario = `${item.finding.trigger.replaceAll(" · ", ", ")}`;
    const beforeSummary =
      `${item.before.blocks} blocking · ${item.before.warnings} warnings`;
    const afterSummary =
      `${item.after.blocks} blocking · ${item.after.warnings} warnings`;
    const imageStem = item.id;

    caseTitle.textContent = item.title;
    caseLink.href = item.url;
    caseLink.textContent = `Open ${item.title}`;
    beforeVerdict.textContent = `${item.before.status} · ${beforeSummary}`;
    afterVerdict.textContent = `${item.after.status} · ${afterSummary}`;
    heroBeforeStatus.textContent = item.before.status;
    heroAfterStatus.textContent = item.after.status;
    findingDimension.textContent = item.finding.dimension;
    findingMeasure.textContent = `${item.finding.measured_px}px`;
    findingSelector.textContent = item.finding.selector;
    findingTrigger.textContent = item.finding.trigger;
    beforeCaption.textContent =
      `${item.before.status} · ${item.finding.measured_px}px over`;
    afterCaption.textContent =
      `${item.after.status} · ${item.after.issue_occurrences} findings`;
    reproduceCommand.textContent =
      `ego-webqa ${item.url} --profile baseline --browser-channel chrome --no-smoke`;

    images.heroBefore.src = `assets/production/before/${imageStem}.png`;
    images.heroAfter.src = `assets/production/after/${imageStem}.png`;
    images.caseBefore.src = `assets/production/before/${imageStem}.png`;
    images.caseAfter.src = `assets/production/after/${imageStem}.png`;

    images.heroBefore.alt =
      `${item.title} before repair at ${scenario}: the page extends beyond the viewport.`;
    images.heroAfter.alt =
      `${item.title} after repair at ${scenario}: the footer remains inside the viewport.`;
    images.caseBefore.alt =
      `${item.title} before repair at ${scenario}.`;
    images.caseAfter.alt =
      `${item.title} after repair at ${scenario}, with no delivery findings.`;
  }

  async function loadLedger() {
    const response = await fetch("data/repair-ledger.json", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Evidence ledger returned ${response.status}`);
    }

    const ledger = await response.json();
    const cases = new Map(ledger.cases.map((item) => [item.id, item]));

    for (const control of controls) {
      const item = cases.get(control.dataset.case);
      if (!item) {
        control.disabled = true;
        continue;
      }

      control.addEventListener("click", () => {
        for (const candidate of controls) {
          const active = candidate === control;
          candidate.classList.toggle("is-active", active);
          candidate.setAttribute("aria-pressed", String(active));
        }
        displayCase(item);
      });
    }
  }

  loadLedger().catch((error) => {
    document.documentElement.dataset.ledgerStatus = "unavailable";
    console.error(error);
    for (const control of controls) {
      control.disabled = true;
    }
  });
})();

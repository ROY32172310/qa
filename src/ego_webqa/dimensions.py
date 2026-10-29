"""Closed registry of deterministic delivery-check dimensions."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class Dimension:
    """Versioned metadata for one stable issue code."""

    id: str
    version: str
    description: str
    detector: str
    default_severity: str
    introduced_in: str
    profile: str = "baseline"
    parameters: tuple[str, ...] = ()
    deprecated_in: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "version": self.version,
            "description": self.description,
            "detector": self.detector,
            "default_severity": self.default_severity,
            "introduced_in": self.introduced_in,
            "profile": self.profile,
            "parameters": list(self.parameters),
            "deprecated_in": self.deprecated_in,
        }


def _dimension(
    code: str,
    description: str,
    detector: str,
    *,
    severity: str,
    version: str = "1.0.0",
    introduced: str = "0.1.0",
    profile: str = "baseline",
    parameters: tuple[str, ...] = (),
) -> Dimension:
    return Dimension(
        id=code,
        version=version,
        description=description,
        detector=detector,
        default_severity=severity,
        introduced_in=introduced,
        profile=profile,
        parameters=parameters,
    )


_DIMENSIONS = {
    "http_error": _dimension(
        "http_error",
        "The main document returned an HTTP error.",
        "navigation",
        severity="block",
    ),
    "load_error": _dimension(
        "load_error",
        "The page could not reach DOM content readiness.",
        "navigation",
        severity="block",
    ),
    "slow_load_event": _dimension(
        "slow_load_event",
        "The page rendered but its load event exceeded the bounded deadline.",
        "navigation",
        severity="warn",
        introduced="0.2.2",
    ),
    "ready_selector_not_found": _dimension(
        "ready_selector_not_found",
        "The configured SPA readiness selector did not become visible.",
        "navigation",
        severity="block",
        parameters=("ready_selector",),
    ),
    "page_error": _dimension(
        "page_error",
        "The page raised an uncaught JavaScript exception.",
        "runtime",
        severity="block",
    ),
    "console_error": _dimension(
        "console_error",
        "The page emitted console.error.",
        "runtime",
        severity="block",
        parameters=("ignore_console_patterns",),
    ),
    "resource_failure": _dimension(
        "resource_failure",
        "A request failed or returned an HTTP error.",
        "network",
        severity="block",
        parameters=("ignore_request_patterns",),
    ),
    "horizontal_overflow": _dimension(
        "horizontal_overflow",
        "Content extends beyond the viewport width.",
        "geometry",
        severity="block",
        parameters=("overflow_tolerance_px",),
    ),
    "blank_page": _dimension(
        "blank_page",
        "The page contains almost no visible content.",
        "content",
        severity="block",
        parameters=("blank_text_chars", "blank_element_count"),
    ),
    "unreadable_font": _dimension(
        "unreadable_font",
        "Visible text is below the hard readability floor.",
        "readability",
        severity="block",
        parameters=("hard_font_px",),
    ),
    "tiny_fonts": _dimension(
        "tiny_fonts",
        "Multiple visible text nodes are below the preferred size.",
        "readability",
        severity="warn",
        parameters=("min_font_px", "small_issue_report_min"),
    ),
    "small_tap_targets": _dimension(
        "small_tap_targets",
        "Multiple interactive targets are below the touch target threshold.",
        "geometry",
        severity="warn",
        parameters=("min_tap_target_px", "small_issue_report_min"),
    ),
    "huge_overlay": _dimension(
        "huge_overlay",
        "A fixed overlay covers too much of the viewport.",
        "geometry",
        severity="warn",
        version="1.1.0",
        parameters=("overlay_ratio",),
    ),
    "broken_image": _dimension(
        "broken_image",
        "A visible image failed to decode.",
        "media",
        severity="block",
    ),
    "media_distortion": _dimension(
        "media_distortion",
        "A media element has a distorted aspect ratio.",
        "media",
        severity="block",
        version="1.1.0",
        parameters=("aspect_tolerance", "aspect_min_rendered_px"),
    ),
    "slow_first_paint": _dimension(
        "slow_first_paint",
        "First contentful paint exceeded the advisory budget.",
        "timing",
        severity="warn",
        parameters=("fcp_warn_ms",),
    ),
    "layout_shift": _dimension(
        "layout_shift",
        "The page shifted significantly after initial render.",
        "timing",
        severity="block",
        parameters=("cls_warn", "cls_error"),
    ),
    "network_idle_timeout": _dimension(
        "network_idle_timeout",
        "The page did not reach network idle within the bounded deadline.",
        "network",
        severity="warn",
        parameters=("wait_for_network_idle", "timeout_ms"),
    ),
    "transfer_budget": _dimension(
        "transfer_budget",
        "Initial requests exceed the configured request or transfer budget.",
        "network",
        severity="block",
        parameters=(
            "request_warn_count",
            "request_error_count",
            "transfer_warn_bytes",
            "transfer_error_bytes",
        ),
    ),
    "primary_cta_not_found": _dimension(
        "primary_cta_not_found",
        "No primary call-to-action could be identified.",
        "smoke",
        severity="warn",
        parameters=("cta_pattern", "smoke_selector"),
    ),
    "cta_page_error": _dimension(
        "cta_page_error",
        "Clicking the primary action raised a page error.",
        "smoke",
        severity="block",
    ),
    "cta_assertion_failed": _dimension(
        "cta_assertion_failed",
        "The primary action did not satisfy its configured success assertion.",
        "smoke",
        severity="block",
        parameters=("smoke_success_selector", "smoke_success_url_pattern"),
    ),
    "dead_primary_cta": _dimension(
        "dead_primary_cta",
        "The primary action produced no observable state change.",
        "smoke",
        severity="block",
    ),
    "smoke_flow_step_failed": _dimension(
        "smoke_flow_step_failed",
        "A configured smoke-flow action could not be executed.",
        "smoke",
        severity="block",
        introduced="0.3.0",
        parameters=("smoke_flow",),
    ),
    "smoke_flow_assertion_failed": _dimension(
        "smoke_flow_assertion_failed",
        "A configured smoke-flow expectation was not met.",
        "smoke",
        severity="block",
        introduced="0.3.0",
        parameters=("smoke_flow",),
    ),
    "smoke_flow_page_error": _dimension(
        "smoke_flow_page_error",
        "The configured smoke flow raised a page-level JavaScript error.",
        "smoke",
        severity="block",
        introduced="0.3.0",
        parameters=("smoke_flow",),
    ),
    "missing_html_lang": _dimension(
        "missing_html_lang",
        "The document does not declare a language.",
        "accessibility",
        severity="warn",
        introduced="0.2.0",
        profile="accessibility",
    ),
    "missing_page_title": _dimension(
        "missing_page_title",
        "The document has no descriptive title.",
        "accessibility",
        severity="warn",
        introduced="0.2.0",
        profile="accessibility",
    ),
    "control_missing_name": _dimension(
        "control_missing_name",
        "An interactive control has no accessible name.",
        "accessibility",
        severity="block",
        introduced="0.2.0",
        profile="accessibility",
    ),
    "image_missing_alt": _dimension(
        "image_missing_alt",
        "A visible image has no alt attribute.",
        "accessibility",
        severity="block",
        introduced="0.2.0",
        profile="accessibility",
    ),
    "duplicate_id": _dimension(
        "duplicate_id",
        "The document contains duplicate id values.",
        "accessibility",
        severity="warn",
        introduced="0.2.0",
        profile="accessibility",
    ),
    "heading_level_skip": _dimension(
        "heading_level_skip",
        "Heading levels skip in document order.",
        "accessibility",
        severity="warn",
        introduced="0.2.0",
        profile="accessibility",
    ),
    "positive_tabindex": _dimension(
        "positive_tabindex",
        "Positive tabindex values override natural focus order.",
        "accessibility",
        severity="warn",
        introduced="0.2.0",
        profile="accessibility",
    ),
    "aria_hidden_focusable": _dimension(
        "aria_hidden_focusable",
        "Focusable content is inside an aria-hidden subtree.",
        "accessibility",
        severity="block",
        introduced="0.2.0",
        profile="accessibility",
    ),
}

DIMENSIONS = MappingProxyType(_DIMENSIONS)


def dimension_for(code: str) -> Dimension:
    """Return the registered dimension or reject an unknown issue code."""

    try:
        return DIMENSIONS[code]
    except KeyError as exc:
        raise ValueError(f"unregistered ego-webqa dimension: {code}") from exc


def registry_payload() -> dict[str, object]:
    """Return a stable machine-readable registry for docs and integrations."""

    return {
        "schema_version": "1.0",
        "dimensions": [DIMENSIONS[code].to_dict() for code in sorted(DIMENSIONS)],
    }

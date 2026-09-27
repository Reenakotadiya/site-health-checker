"""Automated accessibility checks that can be made from a page's HTML.

These catch many of the most common WCAG problems. They can't replace a full audit:
color contrast, keyboard navigation and screen reader flows need a real browser or a person.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str  # critical, serious or moderate
    wcag: str
    why: str
    fix: str


RULES = {rule.id: rule for rule in [
    Rule("image-alt", "Image has no alt text", "critical", "1.1.1 Non-text Content",
         "Screen reader users hear nothing, or just the file name, instead of what the image shows.",
         'Add alt="short description of the image". If the image is only decoration, use alt="".'),
    Rule("form-label", "Form field has no label", "critical", "1.3.1 Info and Relationships / 4.1.2 Name, Role, Value",
         "People using screen readers can't tell what they are supposed to type into the field.",
         'Add a <label for="field-id">Your name</label> linked to the field, or an aria-label attribute.'),
    Rule("button-name", "Button has no text", "critical", "4.1.2 Name, Role, Value",
         "Screen readers announce just \"button\", so users don't know what it does.",
         "Put visible text inside the button. For icon-only buttons, add aria-label=\"what it does\"."),
    Rule("link-name", "Link has no text", "serious", "2.4.4 Link Purpose",
         "Screen readers announce just \"link\", so users can't tell where it goes.",
         "Put text inside the link. For icon links, give the icon image an alt, or add aria-label to the link."),
    Rule("html-lang", "Page language is not set", "serious", "3.1.1 Language of Page",
         "Screen readers may read the page with the wrong language and pronunciation.",
         'Add the language to the opening html tag, for example <html lang="en">.'),
    Rule("zoom-disabled", "Zooming is disabled", "serious", "1.4.4 Resize Text",
         "People with low vision can't pinch to zoom and enlarge the text on phones.",
         "Remove user-scalable=no and any maximum-scale below 2 from the viewport meta tag."),
    Rule("page-has-h1", "Page has no main heading (h1)", "moderate", "1.3.1 Info and Relationships (best practice)",
         "Screen reader users often jump to the h1 to find the main content. Without one, the page is harder to navigate.",
         "Add one <h1> that describes the main purpose of the page."),
    Rule("heading-order", "Heading levels are skipped", "moderate", "1.3.1 Info and Relationships (best practice)",
         "Jumping from, say, h2 straight to h4 makes the page outline confusing for screen reader users.",
         "Use heading levels in order (h1, then h2, then h3). Style them with CSS if you need a different look."),
]}

SEVERITY_PENALTY = {"critical": 10, "serious": 5, "moderate": 2}
SEVERITY_ORDER = ["critical", "serious", "moderate"]

_UNLABELLED_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}
_LABEL_ATTRS = ("aria-label", "aria-labelledby", "title")


@dataclass
class Issue:
    rule: str
    element: str = ""  # short HTML snippet showing where the problem is


def _snippet(tag: str, attrs: dict) -> str:
    keep = ("type", "name", "id", "src", "href", "class")
    shown = " ".join(f'{k}="{attrs[k]}"' for k in keep if attrs.get(k))
    text = f"<{tag}{' ' + shown if shown else ''}>"
    return text if len(text) <= 100 else text[:97] + "...>"


def _has_label_attr(attrs: dict) -> bool:
    return any((attrs.get(name) or "").strip() for name in _LABEL_ATTRS)


class _A11yParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.issues: list[Issue] = []
        self.html_lang: str | None = None
        self.headings: list[int] = []
        self.label_targets: set[str] = set()
        self.fields: list[tuple[str, str]] = []  # (id, snippet) of fields not labelled on their own
        self._label_depth = 0
        self._named: list[dict] = []  # open links/buttons still waiting for accessible text

    def handle_starttag(self, tag, attr_list):
        attrs = {k: (v or "") for k, v in attr_list}
        hidden = attrs.get("aria-hidden") == "true" or attrs.get("role") in ("presentation", "none")

        if tag == "html":
            self.html_lang = attrs.get("lang", "").strip()
        elif tag == "meta" and attrs.get("name", "").lower() == "viewport":
            self._check_viewport(attrs.get("content", ""))
        elif tag == "img":
            if "alt" not in attrs and not hidden:
                self.issues.append(Issue("image-alt", _snippet(tag, attrs)))
            elif attrs.get("alt", "").strip():
                self._text_found()
        elif re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        elif tag == "label":
            self._label_depth += 1
            if attrs.get("for"):
                self.label_targets.add(attrs["for"])
        elif tag in ("input", "select", "textarea"):
            if tag == "input" and attrs.get("type", "text").lower() in _UNLABELLED_INPUT_TYPES:
                return
            if not (self._label_depth or _has_label_attr(attrs)):
                self.fields.append((attrs.get("id", ""), _snippet(tag, attrs)))
        elif (tag == "a" and "href" in attrs or tag == "button") and not hidden:
            rule = "link-name" if tag == "a" else "button-name"
            self._named.append({"rule": rule, "snippet": _snippet(tag, attrs), "named": _has_label_attr(attrs)})

    def handle_endtag(self, tag):
        if tag == "label":
            self._label_depth = max(0, self._label_depth - 1)
        elif tag in ("a", "button"):
            rule = "link-name" if tag == "a" else "button-name"
            for i in range(len(self._named) - 1, -1, -1):
                if self._named[i]["rule"] == rule:
                    item = self._named.pop(i)
                    if not item["named"]:
                        self.issues.append(Issue(rule, item["snippet"]))
                    break

    def handle_data(self, data):
        if data.strip():
            self._text_found()

    def _text_found(self):
        for item in self._named:
            item["named"] = True

    def _check_viewport(self, content: str):
        settings = {}
        for part in re.split(r"[,;]", content.lower()):
            key, _, value = part.partition("=")
            settings[key.strip()] = value.strip()
        no_scaling = settings.get("user-scalable") in ("no", "0")
        try:
            low_max = float(settings.get("maximum-scale", "10")) < 2
        except ValueError:
            low_max = False
        if no_scaling or low_max:
            self.issues.append(Issue("zoom-disabled", f'<meta name="viewport" content="{content}">'))

    def finish(self) -> list[Issue]:
        if not self.html_lang:
            self.issues.append(Issue("html-lang", "<html>"))
        for field_id, snippet in self.fields:
            if not field_id or field_id not in self.label_targets:
                self.issues.append(Issue("form-label", snippet))
        if 1 not in self.headings:
            self.issues.append(Issue("page-has-h1"))
        for previous, current in zip(self.headings, self.headings[1:]):
            if current > previous + 1:
                self.issues.append(Issue("heading-order", f"<h{previous}> followed by <h{current}>"))
        return self.issues


def audit_html(html: str) -> list[Issue]:
    parser = _A11yParser()
    parser.feed(html)
    parser.close()
    return parser.finish()


def page_score(issues: list[Issue]) -> int:
    """100 minus a penalty per issue (critical 10, serious 5, moderate 2), never below 0."""
    return max(0, 100 - sum(SEVERITY_PENALTY[RULES[issue.rule].severity] for issue in issues))

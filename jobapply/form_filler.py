"""DOM-aware autofill engine.

Given a Playwright container (typically the Easy Apply modal), it discovers form
controls, works out the associated question/label for each, asks
:func:`jobapply.field_matcher.resolve_answer` what to put there, and fills it.

It never clicks a final submit button; the caller decides submission. Fields it
can't confidently answer are collected in :class:`FillResult.unmapped` so the
caller can pause for human review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Locator

from .field_matcher import Answer, choose_option, resolve_answer
from .profile import Profile
from .rate_limiter import RateLimiter


@dataclass
class FillResult:
    filled: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    low_confidence: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.unmapped or self.low_confidence)

    def merge(self, other: "FillResult") -> None:
        self.filled += other.filled
        self.unmapped += other.unmapped
        self.low_confidence += other.low_confidence


class FormFiller:
    def __init__(self, profile: Profile, rate_limiter: RateLimiter | None = None) -> None:
        self.profile = profile
        self.rl = rate_limiter

    def _pause(self) -> None:
        if self.rl:
            self.rl.action_pause()

    def fill_container(self, container: Locator) -> FillResult:
        """Fill every recognised control inside ``container``."""
        result = FillResult()
        self._fill_file_inputs(container, result)
        self._fill_text_inputs(container, result)
        self._fill_textareas(container, result)
        self._fill_selects(container, result)
        self._fill_radio_groups(container, result)
        self._fill_checkboxes(container, result)
        return result

    # ------------------------------------------------------------------
    # Label discovery
    # ------------------------------------------------------------------
    def _label_for(self, element: Locator) -> str:
        """Best-effort label text for a control."""
        for attr in ("aria-label", "name", "placeholder", "id"):
            try:
                val = element.get_attribute(attr)
            except Exception:
                val = None
            if val and not val.startswith("urn:") and len(val) > 1:
                if attr == "id":
                    label = self._label_by_for(element, val)
                    if label:
                        return label
                    continue
                return val
        # <label> wrapping ancestor
        try:
            handle = element.evaluate(
                """el => {
                    const wrap = el.closest('label');
                    if (wrap) return wrap.innerText;
                    const grp = el.closest('[data-test-form-element], .fb-dash-form-element, fieldset');
                    if (grp) {
                        const lab = grp.querySelector('label, legend, span');
                        if (lab) return lab.innerText;
                    }
                    return '';
                }"""
            )
            if handle:
                return handle
        except Exception:
            pass
        return ""

    def _label_by_for(self, element: Locator, elem_id: str) -> str:
        try:
            return element.evaluate(
                """(el, id) => {
                    const lab = document.querySelector(`label[for="${id}"]`);
                    return lab ? lab.innerText : '';
                }""",
                elem_id,
            ) or ""
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Field type handlers
    # ------------------------------------------------------------------
    def _fill_text_inputs(self, container: Locator, result: FillResult) -> None:
        selector = (
            "input[type='text'], input[type='email'], input[type='tel'], "
            "input[type='number'], input[type='url'], input:not([type])"
        )
        inputs = container.locator(selector)
        for i in range(inputs.count()):
            el = inputs.nth(i)
            if not self._is_actionable(el):
                continue
            label = self._label_for(el)
            answer = resolve_answer(label, self.profile)
            if answer is None:
                result.unmapped.append(label or "<unlabelled text field>")
                continue
            if not answer.value:
                result.low_confidence.append(label)
                continue
            self._type_value(el, answer)
            self._handle_typeahead(container, el, answer)
            (result.filled if answer.confident else result.low_confidence).append(label)
            self._pause()

    def _fill_textareas(self, container: Locator, result: FillResult) -> None:
        areas = container.locator("textarea")
        for i in range(areas.count()):
            el = areas.nth(i)
            if not self._is_actionable(el):
                continue
            label = self._label_for(el)
            answer = resolve_answer(label, self.profile)
            if answer is None or not answer.value:
                result.unmapped.append(label or "<unlabelled textarea>")
                continue
            try:
                el.fill(answer.value)
                result.filled.append(label)
            except Exception:
                result.unmapped.append(label)
            self._pause()

    def _fill_selects(self, container: Locator, result: FillResult) -> None:
        selects = container.locator("select")
        for i in range(selects.count()):
            el = selects.nth(i)
            if not self._is_actionable(el):
                continue
            label = self._label_for(el)
            answer = resolve_answer(label, self.profile)
            options = self._option_labels(el)
            if answer is None:
                result.unmapped.append(label or "<unlabelled dropdown>")
                continue
            choice = choose_option(answer, options)
            if choice is None:
                result.low_confidence.append(label)
                continue
            try:
                el.select_option(label=choice)
                (result.filled if answer.confident else result.low_confidence).append(label)
            except Exception:
                result.low_confidence.append(label)
            self._pause()

    def _fill_radio_groups(self, container: Locator, result: FillResult) -> None:
        """Handle fieldset-style radio groups (common for yes/no questions)."""
        groups = container.locator("fieldset")
        for i in range(groups.count()):
            group = groups.nth(i)
            radios = group.locator("input[type='radio']")
            if radios.count() == 0:
                continue
            label = self._label_for(group)
            answer = resolve_answer(label, self.profile)
            if answer is None:
                result.unmapped.append(label or "<unlabelled choice group>")
                continue
            options = self._radio_option_labels(group)
            choice = choose_option(answer, list(options.keys()))
            if choice is None:
                result.low_confidence.append(label)
                continue
            try:
                options[choice].check()
                (result.filled if answer.confident else result.low_confidence).append(label)
            except Exception:
                result.low_confidence.append(label)
            self._pause()

    def _fill_checkboxes(self, container: Locator, result: FillResult) -> None:
        boxes = container.locator("input[type='checkbox']")
        for i in range(boxes.count()):
            el = boxes.nth(i)
            if not self._is_actionable(el):
                continue
            label = self._label_for(el)
            answer = resolve_answer(label, self.profile)
            if answer is None:
                # Never auto-tick unknown checkboxes (could be marketing/consent).
                continue
            should_check = answer.kind == "boolean" and answer.value.lower() == "yes"
            try:
                if should_check and not el.is_checked():
                    el.check()
                    result.filled.append(label)
            except Exception:
                result.low_confidence.append(label)
            self._pause()

    def _fill_file_inputs(self, container: Locator, result: FillResult) -> None:
        files = container.locator("input[type='file']")
        for i in range(files.count()):
            el = files.nth(i)
            label = (self._label_for(el) or "").lower()
            path = None
            if "cover" in label and self.profile.cover_letter_path:
                path = self.profile.cover_letter_path
            elif self.profile.resume_path:
                path = self.profile.resume_path
            if not path or not Path(path).exists():
                continue
            try:
                el.set_input_files(path)
                result.filled.append(f"file:{Path(path).name}")
            except Exception:
                result.unmapped.append("file upload")
            self._pause()

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------
    def _type_value(self, el: Locator, answer: Answer) -> None:
        try:
            el.fill("")
            el.type(answer.value, delay=25)
        except Exception:
            el.fill(answer.value)

    def _handle_typeahead(self, container: Locator, el: Locator, answer: Answer) -> None:
        """LinkedIn city/location fields are autocomplete widgets; select first."""
        label = (self._label_for(el) or "").lower()
        if not any(k in label for k in ("city", "location")):
            return
        try:
            el.press("ArrowDown")
            self._pause()
            listbox = container.locator("[role='option'], .basic-typeahead__selectable")
            if listbox.count() > 0:
                listbox.first.click()
        except Exception:
            pass

    def _option_labels(self, select_el: Locator) -> list[str]:
        try:
            return [
                (o or "").strip()
                for o in select_el.locator("option").all_inner_texts()
                if (o or "").strip()
            ]
        except Exception:
            return []

    def _radio_option_labels(self, group: Locator) -> dict[str, Locator]:
        mapping: dict[str, Locator] = {}
        radios = group.locator("input[type='radio']")
        for i in range(radios.count()):
            radio = radios.nth(i)
            text = self._label_for(radio) or (radio.get_attribute("value") or "")
            if text:
                mapping[text.strip()] = radio
        return mapping

    def _is_actionable(self, el: Locator) -> bool:
        try:
            return el.is_visible() and el.is_enabled()
        except Exception:
            return False

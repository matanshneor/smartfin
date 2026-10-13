"""כפתור שמירה דולק רק כשמשהו השתנה — בכל מקום (מתן, 13.10).

"בכל המקומות שיש אפשרות לשמור שינויים — שהאפשרות לא תהיה דלוקה אם לא שונה
כלום, ותידלק כשמשנים. שלא יהיה רשום 'אין שינויים' — אותו כיתוב, כבוי או פעיל.\""""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
_ROOT = Path(__file__).resolve().parent.parent


def _js(name):
    return (_ROOT / "frontend/static/js" / name).read_text(encoding="utf-8")


def test_one_helper_compares_against_the_saved_values():
    core = _js("core.js")
    body = core[core.index("window.sfSaveWhenChanged = function"):]
    body = body[:body.index("\n};\n")]
    assert "el.value.trim() !== el.defaultValue.trim()" in body
    assert "el.checked !== el.defaultChecked" in body
    assert "button.disabled = !changed();" in body


def test_every_settings_form_uses_it():
    js = _js("settings.js")
    for form, btn in (("familyNameEdit", "saveFamilyNameBtn"), ("profileEdit", "saveProfileBtn"),
                      ("emailForm", "saveEmailBtn"), ("phoneForm", "savePhoneBtn"),
                      ("passwordForm", "changePasswordBtn")):
        assert f"['{form}', '{btn}']" in js, form
    assert "window.sfSaveWhenChanged(row.querySelector('.cat-edit-form'), row.querySelector('.cat-edit-save'))" in js


def test_budgets_project_and_transaction_windows_too():
    assert "window.sfSaveWhenChanged(card, actions.querySelector('[data-save]'))" in _js("month.js")
    assert "function syncSave() { saveBtn.disabled = !isDirty(); }" in _js("project-edit.js")
    tx = _js("transactions.js")
    assert "'אין שינויים'" not in tx


def test_a_disabled_save_looks_off_but_keeps_its_words():
    css = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")
    assert ".btn-primary:disabled, .project-save-btn:disabled {" in css

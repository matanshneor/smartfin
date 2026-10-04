"""צירוף קבלה להוצאה קיימת (מתן, 3.10 — רעיון 34): רק התמונה, בלי קריאה
אוטומטית; קבלה קודמת נמחקת אם אף עסקה אחרת לא מצביעה עליה."""
import io

import pytest

from backend import app as app_module
from backend.app import app, limiter

pytestmark = pytest.mark.unit

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture
def env(monkeypatch):
    limiter.reset()
    app.config["TESTING"] = True
    st = {"type": "expense", "old": None, "uploaded": [], "updated": [], "deleted": [], "unused": [],
          "upload_ok": True, "update_ok": True}
    db = app_module.db
    monkeypatch.setattr(db, "personal_project_owner", lambda *a: None, raising=False)
    monkeypatch.setattr(db, "transaction_type", lambda tx, fid: st["type"])
    monkeypatch.setattr(db, "get_transaction_receipt_path", lambda tx, fid: st["old"])
    monkeypatch.setattr(db, "upload_receipt", lambda tok, fid, b, ct: st["uploaded"].append(ct) or
                        (("fam/new.png", None) if st["upload_ok"] else (None, "boom")))
    monkeypatch.setattr(db, "update_transaction", lambda tx, fid, data: st["updated"].append(data) or
                        (({"id": tx}, None) if st["update_ok"] else (None, "boom")))
    monkeypatch.setattr(db, "delete_receipt", lambda tok, path: st["deleted"].append(path))
    monkeypatch.setattr(app_module, "_delete_unused_receipts", lambda fid, paths: st["unused"].extend(paths))
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = "u"
        sess["family_id"] = "fam"
    return c, st


def _post(c, data=_PNG, ctype="image/png", name="r.png"):
    files = {"image": (io.BytesIO(data), name, ctype)} if data is not None else {}
    return c.post("/api/transactions/t1/receipt", data=files, content_type="multipart/form-data")


def test_attaching_to_an_expense_sets_only_the_receipt(env):
    c, st = env
    res = _post(c)
    assert res.status_code == 200 and res.get_json() == {"status": "ok", "replaced": False}
    assert st["updated"] == [{"receipt_path": "fam/new.png"}], "רק הקבלה — לא סכום, תיאור או תאריך"


def test_replacing_cleans_up_the_old_one(env):
    c, st = env
    st["old"] = "fam/old.png"
    assert _post(c).get_json()["replaced"] is True
    assert st["unused"] == ["fam/old.png"]


def test_not_for_income(env):
    c, st = env
    st["type"] = "income"
    assert _post(c).status_code == 422 and st["uploaded"] == []


def test_a_missing_transaction(env):
    c, st = env
    st["type"] = None
    assert _post(c).status_code == 404


@pytest.mark.parametrize("data,ctype,status", [(None, None, 422), (b"x", "application/pdf", 422),
                                               (b"", "image/png", 422)], ids=["no-file", "pdf", "empty"])
def test_bad_files_are_refused(env, data, ctype, status):
    c, st = env
    assert _post(c, data, ctype).status_code == status and st["uploaded"] == []


def test_a_failed_save_does_not_leave_the_file_behind(env):
    c, st = env
    st["update_ok"] = False
    assert _post(c).status_code == 500
    assert st["deleted"] == ["fam/new.png"]


def test_the_edit_window_offers_it_for_expenses_only():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "frontend/static/js/transactions.js").read_text(encoding="utf-8")
    assert "attachFor = tx && tx.type === 'expense' ? tx.id : null;" in js
    assert "attachLabel.textContent = hasReceipt ? 'החלפת קבלה' : 'צירוף קבלה';" in js
    assert js.count("setupAttach(null);") == 2, "הוספה ושכפול מסתירים את הכפתור"

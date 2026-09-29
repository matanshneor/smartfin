"""עוזר במסד לבדיקת הדפדפן של ב9 — רץ ב-.venv. פקודות: setup / read / cleanup."""
import os, sys, json
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(".env")
from backend import supabase_config as db
cmd = sys.argv[1]
r, _ = db.sign_in(os.environ.get("RLS_TEST_EMAIL_A", "rls-test-family-a@smartfin.test"), os.environ["RLS_TEST_PASSWORD_A"])
db.set_auth_token(r.session.access_token)
fid = db.get_profile(r.user.id)["family_id"]
t = db.get_client().table
B = "f3b3dd61-7d45-496a-b561-c075cdd08b03"      # משתמש הבדיקה ב' — במשפחה אחרת
state_file = "/tmp/edit_keep_state.json"
if cmd == "setup":
    settings = (db.get_family(fid) or {}).get("settings") or {}
    json.dump({"attribution": settings.get("owner_attribution")}, open(state_file, "w"))
    db.update_family_settings(fid, {"owner_attribution": {"expense": True, "income": False, "savings": False}})
    t("transactions").insert({"family_id": fid, "amount": 90, "type": "expense", "date": sys.argv[2],
                              "description": "KEEP-GONE", "user_id": B}).execute()
    print("ok")
elif cmd == "read":
    rows = t("transactions").select("description, amount, category_id, user_id, project_id") \
        .eq("family_id", fid).like("description", "KEEP-%").execute().data
    print(json.dumps({r["description"]: {**r, "user_is_B": r["user_id"] == B} for r in rows}))
elif cmd == "cleanup":
    state = json.load(open(state_file)) if os.path.exists(state_file) else {}
    db.update_family_settings(fid, {"owner_attribution": state.get("attribution") or
                                    {"expense": False, "income": False, "savings": False}})
    t("transactions").delete().eq("family_id", fid).like("description", "KEEP-%").execute()
    t("projects").delete().eq("family_id", fid).eq("name", "KEEP-PROJ").execute()
    print("cleaned-keep")

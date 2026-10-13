/* כניסה עם Face ID (מתן, 12.10).
 *
 * Passkeys של Supabase. המפתח נשמר במכשיר (במחזיק המפתחות של iCloud או של
 * Google) ונפתח בפנים או באצבע. השרת שלנו רק מעביר: ‎/api/passkey/*‎.
 *
 * כאן: המרה בין ה-JSON של השרת (base64url) לאובייקטים של הדפדפן — בשיטה
 * המובנית כשיש (‎parse…FromJSON‎, ‎toJSON‎), וידנית בדפדפנים ישנים. אותה
 * המרה כמו ב-‎@supabase/auth-js‎ (‎lib/webauthn.ts‎).
 *
 * שני מקומות:
 *   התחברות — כפתור "כניסה עם Face ID", רק במכשיר שכבר הופעל בו (‎sf_passkey‎).
 *   הגדרות → החשבון שלי — הפעלה, ורשימת המכשירים עם "הסרה".
 */
(function () {
    'use strict';

    const supported = !!(window.PublicKeyCredential && navigator.credentials);
    const FLAG = 'sf_passkey';
    // אייפון / אייפד / מק — Face ID או Touch ID; בשאר — טביעת אצבע
    const apple = /iPhone|iPad|Macintosh/.test(navigator.userAgent);
    const NAME = apple ? 'Face ID' : 'טביעת אצבע';

    function setFlag(on) {
        try { on ? localStorage.setItem(FLAG, '1') : localStorage.removeItem(FLAG); } catch (e) { /* אין אחסון */ }
    }
    function hasFlag() {
        try { return localStorage.getItem(FLAG) === '1'; } catch (e) { return false; }
    }

    function b64urlToBuf(s) {
        const pad = '='.repeat((4 - s.length % 4) % 4);
        const bin = atob((s + pad).replace(/-/g, '+').replace(/_/g, '/'));
        const out = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
        return out.buffer;
    }
    function bufToB64url(buf) {
        const bytes = new Uint8Array(buf);
        let bin = '';
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }
    function credList(list) {
        return (list || []).map(function (c) {
            return Object.assign({}, c, { id: b64urlToBuf(c.id), type: c.type || 'public-key' });
        });
    }

    function creationOptions(o) {
        if (typeof PublicKeyCredential.parseCreationOptionsFromJSON === 'function') {
            return PublicKeyCredential.parseCreationOptionsFromJSON(o);
        }
        const out = Object.assign({}, o, {
            challenge: b64urlToBuf(o.challenge),
            user: Object.assign({}, o.user, { id: b64urlToBuf(o.user.id) }),
        });
        if (o.excludeCredentials && o.excludeCredentials.length) out.excludeCredentials = credList(o.excludeCredentials);
        else delete out.excludeCredentials;
        return out;
    }
    function requestOptions(o) {
        if (typeof PublicKeyCredential.parseRequestOptionsFromJSON === 'function') {
            return PublicKeyCredential.parseRequestOptionsFromJSON(o);
        }
        const out = Object.assign({}, o, { challenge: b64urlToBuf(o.challenge) });
        if (o.allowCredentials && o.allowCredentials.length) out.allowCredentials = credList(o.allowCredentials);
        else delete out.allowCredentials;
        return out;
    }
    function credentialJSON(c) {
        if (typeof c.toJSON === 'function') return c.toJSON();
        const r = c.response, json = {
            id: c.id, rawId: c.id, type: 'public-key',
            clientExtensionResults: c.getClientExtensionResults(),
            authenticatorAttachment: c.authenticatorAttachment || undefined,
            response: { clientDataJSON: bufToB64url(r.clientDataJSON) },
        };
        if (r.attestationObject) json.response.attestationObject = bufToB64url(r.attestationObject);
        if (r.authenticatorData) {
            json.response.authenticatorData = bufToB64url(r.authenticatorData);
            json.response.signature = bufToB64url(r.signature);
            if (r.userHandle) json.response.userHandle = bufToB64url(r.userHandle);
        }
        return json;
    }

    function post(url, body) {
        return fetch(url, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(body || {}),
        }).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (d) {
                if (!r.ok) { const e = new Error(d.error || ''); e.code = d.code; throw e; }
                return d;
            });
        });
    }

    // ביטול בחלון של המערכת אינו שגיאה — פשוט לא קורה כלום
    function cancelled(e) { return e && (e.name === 'NotAllowedError' || e.name === 'AbortError'); }
    const FAILED = NAME + ' לא הצליח — נסו שוב';

    // ── התחברות ──────────────────────────────────────────────────────────
    const loginBtn = document.getElementById('passkeyLogin');
    if (loginBtn && supported && hasFlag()) {
        const err = document.getElementById('passkeyError');
        loginBtn.querySelector('[data-passkey-name]').textContent = NAME;
        loginBtn.hidden = false;
        loginBtn.addEventListener('click', function () {
            if (loginBtn.disabled) return;
            loginBtn.disabled = true;
            err.textContent = '';
            post('/api/passkey/login/options')
                .then(function (o) {
                    return navigator.credentials.get({ publicKey: requestOptions(o.options) })
                        .then(function (c) {
                            return post('/api/passkey/login/verify',
                                        { challenge_id: o.challenge_id, credential: credentialJSON(c) });
                        });
                })
                .then(function (d) { window.location.replace(d.redirect || '/'); })
                .catch(function (e) {
                    loginBtn.disabled = false;
                    if (cancelled(e)) return;
                    // אין במכשיר הזה כניסה כזאת (נמחקה, או מכשיר אחר) — הכפתור
                    // לא יעזור בפעם הבאה, אז הוא יורד עד שיופעל שוב בהגדרות
                    if (e.code === 'webauthn_credential_not_found') { setFlag(false); loginBtn.hidden = true; }
                    err.textContent = e.message || FAILED;
                });
        });
        // נפתח לבד (מתן, 12.10): בטלפון שהופעל בו — חלון ה-Face ID קופץ מיד, בלי
        // לחיצה. לא אחרי "התנתקות" יזומה באותה לשונית (מי שהתנתק אולי רוצה
        // חשבון אחר), ולא אחרי ניסיון כושל בסיסמה (יש שגיאה במסך). ספארי עלול
        // לסרב בלי לחיצה — אז נשאר הכפתור, בלי הודעה (‎cancelled‎).
        let justOut = false;
        try { justOut = sessionStorage.getItem('sf_logged_out') === '1'; sessionStorage.removeItem('sf_logged_out'); } catch (e) { /* אין אחסון */ }
        const failedLogin = !!document.querySelector('.alert-error');
        const panel = document.getElementById('loginPanel');
        const onLogin = !panel || panel.style.display !== 'none';      // לא בלשונית ההרשמה
        if (!justOut && !failedLogin && onLogin) setTimeout(function () { loginBtn.click(); }, 350);
    }

    // ── מסך הנעילה (‎/unlock‎, מתן 13.10) ─────────────────────────────────
    const unlockBtn = document.getElementById('unlockBtn');
    if (unlockBtn) {
        const screen = document.getElementById('unlockScreen');
        const uerr = document.getElementById('unlockError');
        unlockBtn.querySelector('[data-passkey-name]').textContent = NAME;
        // "כניסה עם סיסמה" — בטופס ההתחברות לא להקפיץ שוב את ה-Face ID
        document.getElementById('unlockPassword').addEventListener('submit', function () {
            try { sessionStorage.setItem('sf_logged_out', '1'); } catch (e) { /* אין אחסון */ }
        });
        if (!supported) {
            unlockBtn.hidden = true;
            uerr.textContent = 'הטלפון הזה לא תומך ב-' + NAME + ' — היכנסו עם סיסמה';
        } else {
            unlockBtn.addEventListener('click', function () {
                if (unlockBtn.disabled) return;
                unlockBtn.disabled = true;
                uerr.textContent = '';
                post('/api/passkey/login/options')
                    .then(function (o) {
                        return navigator.credentials.get({ publicKey: requestOptions(o.options) })
                            .then(function (c) {
                                return post('/api/unlock/verify',
                                            { challenge_id: o.challenge_id, credential: credentialJSON(c) });
                            });
                    })
                    .then(function () { window.location.replace(screen.dataset.next || '/'); })
                    .catch(function (e) {
                        unlockBtn.disabled = false;
                        unlockBtn.querySelector('span').firstChild.textContent = 'נסו שוב עם ';
                        uerr.textContent = cancelled(e) ? '' : (e.message || FAILED);
                    });
            });
            setTimeout(function () { unlockBtn.click(); }, 350);
        }
        return;
    }

    // ── הגדרות → החשבון שלי: מתג (מתן, 13.10) ──────────────────────────
    // דולק = יש מפתח בחשבון. הדלקה — יצירת מפתח בטלפון הזה; כיבוי — אישור,
    // והסרת המפתחות (כמו "כיבוי" שהיה ליד כל מפתח). בלי רשימת מכשירים:
    // המפתח עובר לבד בין מכשירי האפל דרך iCloud.
    const box = document.getElementById('passkeySettings');
    if (!box || !supported) return;
    const toggle = document.getElementById('passkeyToggle');
    const hint = document.getElementById('passkeyHint');
    const err = document.getElementById('passkeySettingsError');
    box.querySelectorAll('[data-passkey-name]').forEach(function (el) { el.textContent = NAME; });
    let ids = [];

    function render(items) {
        ids = items.map(function (p) { return p.id; });
        toggle.checked = ids.length > 0;
        hint.textContent = ids.length ? 'נעילת האפליקציה מופעלת' : 'נעילת האפליקציה באמצעות ' + NAME;
        // יש כניסה כזאת בחשבון — הכפתור במסך ההתחברות יופיע בטלפון הזה
        if (ids.length) setFlag(true);
    }
    function load() {
        return fetch('/api/passkeys', { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
            .then(function (items) { render(items); box.hidden = false; })
            .catch(function () { /* לא הופעל באתר או לא זמין — השורה לא מופיעה */ });
    }

    function turnOn() {
        return post('/api/passkey/register/options')
            .then(function (o) {
                return navigator.credentials.create({ publicKey: creationOptions(o.options) })
                    .then(function (c) {
                        return post('/api/passkey/register/verify',
                                    { challenge_id: o.challenge_id, credential: credentialJSON(c) });
                    });
            })
            .then(function () {
                setFlag(true);
                if (window.showToast) window.showToast('נעילת האפליקציה באמצעות ' + NAME + ' הופעלה', 'success');
            })
            .catch(function (e) { if (!cancelled(e)) err.textContent = e.message || FAILED; });
    }
    function turnOff() {
        const ask = window.appConfirm ? window.appConfirm({
            title: 'לכבות את נעילת האפליקציה?',
            message: 'האפליקציה תיפתח בלי ' + NAME + '.',
            confirmText: 'כיבוי', cancelText: 'ביטול', danger: false,
        }) : Promise.resolve(true);
        return ask.then(function (yes) {
            if (!yes) return;
            return Promise.all(ids.map(function (id) {
                return fetch('/api/passkeys/' + encodeURIComponent(id), {
                    method: 'DELETE', credentials: 'same-origin', headers: { 'Accept': 'application/json' },
                }).then(function (r) { if (!r.ok) throw new Error(); });
            })).then(function () { setFlag(false); })
              .catch(function () { err.textContent = 'הכיבוי נכשל — נסו שוב'; });
        });
    }

    toggle.addEventListener('change', function () {
        const wantOn = toggle.checked;
        toggle.checked = !wantOn;          // המצב מתעדכן רק אחרי שזה באמת קרה
        toggle.disabled = true;
        err.textContent = '';
        (wantOn ? turnOn() : turnOff())
            .then(load)
            .then(function () { toggle.disabled = false; });
    });

    load();
})();

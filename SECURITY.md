# Security policy

## Reporting a vulnerability

**Do not open a public Issue.** Use GitHub's private reporting:
**Security → Report a vulnerability** (*Private vulnerability reporting*) in this repository.
Include the version, the operating system, the steps to reproduce and the impact. I reply as soon as possible
(the project is maintained in spare time: normally within 7 days for a first answer). I thank those who report
responsibly publicly, if they wish.

## Supported versions

Only the latest published version receives security fixes.

## Threat model

NeoTracker is a **local** app that holds **health data** and photos. It defends against:

1. **Other computers on the network** → the server listens only on `127.0.0.1`.
2. **Web pages open in your browser** (CSRF, *DNS rebinding*, requests to `localhost`) → checks of `Host` and
   `Origin`, mandatory `X-NeoTracker` header on state-changing operations, a random **session key** (256 bit)
   handed to the app window and kept in an `HttpOnly; SameSite=Strict` cookie, compared in constant time. Without
   the key every request (except `/api/ping`) is rejected.
3. **Other programs and users of the PC** → the key changes at every start; the `sessione.token` file has `0600`
   permissions (Linux/Mac) and is deleted on exit; `impostazioni.json` (with any OpenWeather key) has `0600`
   permissions and is written atomically.
4. **Malicious content** (trap images, disguised files, texts with HTML) → format detection from the bytes rather
   than the extension, megapixel (150 MP) and size limits, re-encoding of the personal picture, no HTML
   interpretation in texts (the page builds elements, not HTML strings), strict CSP (`script-src 'self'`,
   `connect-src 'self'`, no external resources), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, CSP
   `sandbox` on the images served.
5. **Paths and SQL** → files are resolved only inside the data folder; queries are always parameterised.
6. **Responses from external services** → `https` only, no `file:`/`ftp:` (not even via redirects), maximum size,
   XML with `ENTITY` declarations rejected.
7. **Resource exhaustion** → connection timeouts, a cap on "presence" connections, size limits.

The automated tests are in `tests/test_sicurezza.py`; static analysis (bandit) and CodeQL run in CI.

## Known limits (what is NOT protected)

- **Malware or other programs running under your own account** can read the data folder and the key file: this is
  not a boundary the program can defend. Use disk encryption (BitLocker) and an account with a password. The data
  is **not encrypted** by the program.
- The session key appears in the command line used to open the window (visible to other processes of the same user
  for a few moments) and, if Edge/Chrome are not found, in the history of the default browser (valid only until
  NeoTracker is closed).
- The **analysis projects** (TensorFlow, PyTorch, etc.) are third-party code and models, run in local virtual
  environments: install them only from the sources indicated. PyTorch weights are loaded with `weights_only=True`
  (numbers only, no code); the Keras models are third-party files.
- **SkinSense** (optional, off) sends the photo to a service we do not control.
- The program uses the **Pillow** library to open images: keep it up to date (≥ 10.3.0; the app warns in Settings
  if it is old).

## Good practice for users

Keep Windows, Python and Pillow up to date; do not expose port 8750 with port forwarding or tunnels; do not run
NeoTracker on a shared computer without encryption; never publish the data folder (it contains health data). If
you publish a fork of your own, do not include real data, photos or settings: `.gitignore` excludes them.

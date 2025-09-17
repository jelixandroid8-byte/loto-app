# android-app (PWA/TWA scaffold)

This folder contains a minimal PWA scaffold to make the existing site installable
and ready to be wrapped as a Trusted Web Activity (TWA) for the Play Store.

What I added:
- `manifest.json` — PWA manifest (uses existing `/static/img1.jpg` as icons)
- `service-worker.js` — minimal service worker (cache-first)

Next steps to test locally:
1. Serve the site over HTTPS (required for service workers and TWA). For local testing you can use `mkcert` + a simple HTTPS server or host in a staging HTTPS environment.
2. Add the manifest link and service worker registration to your base template (`templates/layout.html`).

Example HTML to include in `<head>` of `layout.html`:

```html
<link rel="manifest" href="/android-app/manifest.json">
<meta name="theme-color" content="#2d6a4f">
```

And register the service worker in a small script, e.g., at the bottom of the layout (before `</body>`):

```html
<script>
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/android-app/service-worker.js')
    .then(() => console.log('Service worker registered'))
    .catch(err => console.error('SW registration failed', err));
}
</script>
```

TWA packaging (optional):
- Use Bubblewrap (https://github.com/GoogleChromeLabs/bubblewrap) to create an Android project that wraps your HTTPS-hosted site and generate an APK / AAB for Play store.

Security note:
- PWAs and TWA require HTTPS. For production use an SSL certificate and configure the server accordingly.

---

Detailed Bubblewrap packaging checklist

1) Prepare assets
  - Replace the JPG icons in `manifest.json` with PNGs at 192x192 and 512x512 (square, transparent background preferred).
  - Place icons under `static/icons/` and update manifest paths.

2) Validate PWA
  - Open your site in Chrome and run Lighthouse (Application > PWA). Fix any critical failures (manifest, icons, service worker scope).

3) Install Bubblewrap

  npm install -g @bubblewrap/cli

4) Initialize a TWA project

  bubblewrap init --manifest=https://yourdomain/manifest.json

  - Provide a unique applicationId (e.g. com.yourcompany.lotoweb)
  - Generate or import a signing keystore when prompted.

5) Build and test

  bubblewrap build
  # The output will be an Android Studio project or an .aab ready to upload

6) Upload to Play Console
  - Use the Play Console to upload the generated AAB.
  - Configure store listing, content rating, privacy policy, and screenshots.

If you want I can generate the icon PNGs and a sample `bubblewrap` config file to speed up the packaging. Tell me which package name you'd like (reverse-domain, e.g. com.example.lotoweb) and whether you prefer to use Play App Signing or a local keystore.

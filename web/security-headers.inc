# Included in every location of nginx.conf (see the note there).
add_header X-Content-Type-Options nosniff always;
add_header X-Frame-Options DENY always;
add_header Referrer-Policy no-referrer always;
# Stripe.js (card entry on /apply) loads from js.stripe.com, frames its card field, and talks to
# api.stripe.com; nothing else is allowed off-site.
add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://js.stripe.com; frame-src blob: https://js.stripe.com https://hooks.stripe.com; connect-src 'self' https://api.stripe.com; img-src 'self' blob: data: https://*.stripe.com; style-src 'self' 'unsafe-inline'" always;

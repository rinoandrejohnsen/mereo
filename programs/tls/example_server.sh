#!/usr/bin/env bash
# Minimal TLS 1.3 server — the secure endpoint the mereo HTTPS client talks to.
# It terminates TLS (handshake, cert, record layer) so the client has a real
# peer to connect to. Any cert works; the dev client skips validation.
set -e
cd "$(dirname "$0")"

# one-time: a self-signed EC (P-256) certificate + key
if [ ! -f cert.pem ]; then
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
    -keyout key.pem -out cert.pem -days 30 -nodes -subj "/CN=localhost" 2>/dev/null
fi

# TLS 1.3 only, pinned to exactly what the mereo client offers
# (AES-128-GCM-SHA256 + X25519). -www serves a small HTML status page to any
# GET. -num_tickets 0 keeps the client's plain kTLS read path simple.
exec openssl s_server -accept 4443 -cert cert.pem -key key.pem \
  -tls1_3 -ciphersuites TLS_AES_128_GCM_SHA256 -groups X25519 \
  -www -num_tickets 0 -quiet

#!/bin/sh
set -e

if [ "$ENABLE_SSL" = "true" ]; then
    # If Let's Encrypt certs exist, link them into /etc/nginx/ssl
    if [ -d /etc/letsencrypt/live ] && [ -z "$(ls -A /etc/nginx/ssl/ 2>/dev/null)" ]; then
        DOMAIN_DIR=$(ls -d /etc/letsencrypt/live/*/ 2>/dev/null | head -1)
        if [ -n "$DOMAIN_DIR" ]; then
            mkdir -p /etc/nginx/ssl
            ln -sf "$DOMAIN_DIR/fullchain.pem" /etc/nginx/ssl/fullchain.pem
            ln -sf "$DOMAIN_DIR/privkey.pem" /etc/nginx/ssl/privkey.pem
        fi
    fi
    cp /etc/nginx/custom/nginx-ssl.conf /etc/nginx/nginx.conf
else
    cp /etc/nginx/custom/nginx.conf /etc/nginx/nginx.conf
fi

UPLOAD_REQUEST_MAX_BYTES=${UPLOAD_REQUEST_MAX_BYTES:-105906176}
case "$UPLOAD_REQUEST_MAX_BYTES" in ''|*[!0-9]*) exit 1;; esac
export UPLOAD_REQUEST_MAX_BYTES
envsubst '${UPLOAD_REQUEST_MAX_BYTES}' < /etc/nginx/nginx.conf > /etc/nginx/nginx.conf.tmp
mv /etc/nginx/nginx.conf.tmp /etc/nginx/nginx.conf
exec nginx -g 'daemon off;'

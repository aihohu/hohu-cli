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

exec nginx -g 'daemon off;'

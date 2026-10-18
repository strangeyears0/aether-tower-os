FROM nginxinc/nginx-unprivileged:1.27-alpine

# Adres backendu podstawiany do szablonu nginx przy starcie (envsubst).
ENV API_UPSTREAM=http://reservation-service:8000

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY index.html styles.css app.js favicon.svg /usr/share/nginx/html/

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1

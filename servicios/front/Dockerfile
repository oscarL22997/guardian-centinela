# Imagen base: nginx oficial alpine (~20 MB). Solo sirve archivos estáticos.
FROM nginx:1.28-alpine
COPY nginx-front.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
EXPOSE 80

# Cenkor Admin · 全栈前端镜像（内置 Nginx：托管 dist + 反代 /api 到后端）
#   用法：--build-arg FRONTEND=admin-web|portal-web|developer-web
FROM node:20-alpine AS build
ARG FRONTEND
WORKDIR /app
COPY frontend/$FRONTEND/package.json frontend/$FRONTEND/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/$FRONTEND/ ./
ARG VITE_API_BASE_URL=
ARG VITE_WS_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_WS_URL=$VITE_WS_URL
RUN npm run build

FROM nginx:alpine
COPY docker/fullstack/nginx-app.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1/healthz || exit 1
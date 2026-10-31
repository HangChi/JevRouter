# Web 仪表盘镜像。它只跟 API 讲话，自己不含任何提供方凭证。
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# 构建期需要知道 API 在哪；运行时也可以用同名环境变量覆盖。
ARG API_UPSTREAM_URL=http://127.0.0.1:8000
ENV API_UPSTREAM_URL=$API_UPSTREAM_URL
RUN npm run build

FROM node:22-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/next.config.ts ./next.config.ts
EXPOSE 3000
CMD ["npm", "run", "start"]

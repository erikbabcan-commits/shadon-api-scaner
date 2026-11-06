FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM alpine:3.24.4
WORKDIR /dist
COPY --from=build /app/dist ./built
CMD ["sh", "-ec", "rm -rf /out/*; cp -a /dist/built/. /out/; echo web assets copied; exec sleep infinity"]

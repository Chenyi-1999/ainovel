FROM node:22-alpine AS frontend
WORKDIR /src/frontend
ENV NODE_OPTIONS=--max-old-space-size=384 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY docs/ /src/docs/
RUN npm run build

FROM golang:1.25 AS builder
WORKDIR /src
ENV CGO_ENABLED=0 GOMAXPROCS=1 GOGC=50 GOMEMLIMIT=384MiB GOFLAGS=-p=1
COPY . .
COPY --from=frontend /src/frontend/dist ./frontend/dist
RUN go build -trimpath -ldflags="-s -w -X main.version=f790187-lab" -o /out/story .

FROM alpine:3.22
RUN apk add --no-cache ca-certificates tzdata \
    && adduser -D -u 10001 writer && mkdir /data && chown writer:writer /data
COPY --from=builder /out/story /usr/local/bin/show-me-the-story
COPY LICENSE /usr/share/doc/show-me-the-story/LICENSE
LABEL org.opencontainers.image.source="https://github.com/Nigh/show-me-the-story" \
    org.opencontainers.image.revision="f790187373f23dbaaffa0838197e972a394960d3"
USER writer
WORKDIR /data
EXPOSE 48090
ENTRYPOINT ["show-me-the-story", "/data"]

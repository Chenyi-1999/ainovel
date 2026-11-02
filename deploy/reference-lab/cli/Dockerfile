FROM golang:1.25 AS builder
WORKDIR /src
ENV CGO_ENABLED=0 GOWORK=off GOMAXPROCS=1 GOGC=50 GOMEMLIMIT=384MiB GOFLAGS=-p=1
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -trimpath -ldflags="-s -w -X main.commit=1c4fd8b3f9f2ade663b238cb2bf1ea7ac7d43bcf -X main.version=lab" -o /out/ainovel-cli ./cmd/ainovel-cli

FROM alpine:3.22
RUN apk add --no-cache ca-certificates tzdata ttyd \
    && adduser -D -u 10001 writer \
    && mkdir -p /workspace /home/writer/.ainovel \
    && chown -R writer:writer /workspace /home/writer
COPY --from=builder /out/ainovel-cli /usr/local/bin/ainovel-cli
COPY LICENSE /usr/share/doc/ainovel-cli/LICENSE
LABEL org.opencontainers.image.source="https://github.com/voocel/ainovel-cli" \
    org.opencontainers.image.revision="1c4fd8b3f9f2ade663b238cb2bf1ea7ac7d43bcf"
ENV HOME=/home/writer TERM=xterm-256color COLORTERM=truecolor
USER writer
WORKDIR /workspace
EXPOSE 7681
ENTRYPOINT ["ttyd", "-i", "0.0.0.0", "-p", "7681", "-b", "/terminal", "-W", "-m", "1", "-t", "titleFixed=ainovel-cli", "/usr/local/bin/ainovel-cli"]

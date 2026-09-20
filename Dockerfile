# Hugo extended は CGO を使うため、実行側と同じ libc でビルドする必要がある。
# 実行側が Alpine (musl) なので、ビルドも Alpine で行う。さらに静的リンクして、
# ビルド側と実行側で Alpine のバージョンがずれても動くようにする。
FROM golang:alpine AS hugo-builder

RUN apk add --no-cache build-base

RUN CGO_ENABLED=1 go install -tags extended \
    -ldflags "-linkmode external -extldflags '-static'" \
    github.com/gohugoio/hugo@v0.166.0

FROM asciidoctor/docker-asciidoctor:latest

RUN apk add --no-cache \
    curl git make jq \
    ruby-dev alpine-sdk graphviz
RUN gem install bundler json asciidoctor-html5s asciidoctor-diagram

COPY --from=hugo-builder /go/bin/hugo /usr/bin/hugo

WORKDIR /src
RUN git config --global --add safe.directory /src

CMD /usr/bin/hugo server --bind=0.0.0.0

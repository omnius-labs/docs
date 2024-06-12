FROM golang as hugo-builder

RUN CGO_ENABLED=1 go install -tags extended github.com/gohugoio/hugo@v0.127.0

FROM asciidoctor/docker-asciidoctor

# libc6-compat is required for Hugo
RUN apk add --no-cache \
    libc6-compat \
    curl git make jq \
    ruby-dev alpine-sdk graphviz
RUN gem install bundler json asciidoctor-html5s asciidoctor-diagram

COPY --from=hugo-builder /go/bin/hugo /usr/bin/hugo

WORKDIR /src
RUN git config --global --add safe.directory /src

CMD /usr/bin/hugo server --bind=0.0.0.0

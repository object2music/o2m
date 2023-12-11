FROM alpine:3 as downloader

RUN wget https://github.com/pocketbase/pocketbase/releases/download/v0.16.5/pocketbase_0.16.5_linux_amd64.zip \
    && unzip pocketbase_0.16.5_linux_amd64.zip \
    && chmod +x /pocketbase

FROM alpine:3
RUN apk update && apk add ca-certificates && rm -rf /var/cache/apk/*

EXPOSE 8090

COPY --from=downloader /pocketbase /usr/local/bin/pocketbase

RUN mkdir /pb_data
COPY ./pb_migrations /pb_migrations

RUN pocketbase migrate --migrationsDir=/pb_migration --dir=/pb_data/

RUN ls -la /pb_data

ENTRYPOINT ["/usr/local/bin/pocketbase", "serve", "--http=0.0.0.0:8090", "--dir=/pb_data", "--migrationsDir=/pb_migrations"]
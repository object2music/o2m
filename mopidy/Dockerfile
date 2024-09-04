FROM ubuntu:22.04 as builder

# interactive mode
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install Env Rust gstreamer
RUN apt update
#RUN apt install -y curl
#RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
#ENV PATH="/root/.cargo/bin:${PATH}"
#RUN rustup toolchain install nightly
#RUN rustup default nightly
RUN apt install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gcc pkg-config git wget
RUN apt install -y libasound2 libasound2-dev 
#RUN git clone --depth 1 https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs
#WORKDIR /app/gst-plugins-rs
#RUN cargo build --package gst-plugin-spotify -Z sparse-registry --release 
#RUN cp ./gst-plugin-spotify_0.13.0-1_amd64.deb /app/gst-plugin-spotify_0.13.0-1_amd64.deb && dpkg --install gst-plugin-spotify_0.13.0-1_amd64.deb

FROM ubuntu:22.04

# interactive mode
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt update 

# Install dependencies
RUN apt install -y wget 

# Install Python
RUN apt install -y python3 python3-pip git

# Mopidy
RUN mkdir -p /etc/apt/keyrings
RUN wget -q -O /etc/apt/keyrings/mopidy-archive-keyring.gpg \
    https://apt.mopidy.com/mopidy.gpg
RUN  wget -q -O /etc/apt/sources.list.d/mopidy.list https://apt.mopidy.com/bullseye.list
RUN apt-get update
RUN apt-get -y install mopidy
#RUN  apt-get install -y swig python-spotify libpcsclite-dev libcairo2-dev

# Install libspotify
#RUN apt install -y libspotify-dev

WORKDIR /app

COPY ./start_mopidy.sh /app/start_mopidy.sh
COPY ./requirements.txt /app/requirements.txt
COPY ./entrypoint.sh ./entrypoint.sh
COPY ./create_conf_files.sh ./create_conf_files.sh
RUN chmod +x ./entrypoint.sh
RUN chmod +x ./create_conf_files.sh

# copies from local (to solve with a backoffice later)
#COPY ./samples/m3u /root/.local/share/mopidy/m3u
#COPY ./samples/podcasts/Podcasts.opml /etc/mopidy/podcasts.opml

# put in iris folder
COPY  ./o2m.css /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.css
COPY  ./o2m.js /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/o2m.js
COPY  ./app.js /app/app.js
COPY ./index.html /app/index.html
#See https://github.com/mopidy/mopidy-spotify/issues/394 for how to get credentials.json
COPY ./credentials.json /app/credentials.json
#COPY ./samples/index.html /usr/local/lib/python3.10/dist-packages/mopidy_iris/static/index.html

# Install Python dependencies with caching
RUN --mount=type=cache,target=/root/.cache \
python3 -m pip install -r requirements.txt

# Install Rust gstreamer
ARG URL=https://github.com/kingosticks/gst-plugins-rs-build/releases/download/gst-plugin-spotify_0.13.1-1
ARG FILE=gst-plugin-spotify_0.13.1-1_amd64.deb
ARG FILE2=libgstspotify.so
RUN wget $URL/$FILE && dpkg --install $FILE && rm $FILE
#COPY --from=builder /app/gst-plugins-rs/target/release/libgstspotify.so /app/libgstspotify.so
#RUN cp /app/libgstspotify.so /usr/lib/x86_64-linux-gnu/gstreamer-1.0/

# install mopidy-spotify
#RUN python3 -m pip install https://github.com/mopidy/mopidy-spotify/archive/master.zip
RUN python3 -m pip install Mopidy-Spotify==5.0.0a2

ENTRYPOINT ["./entrypoint.sh"]
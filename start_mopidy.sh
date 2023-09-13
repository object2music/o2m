#!/bin/bash
pkill mopidy
pkill python3

#docker/entrypoint.sh
docker-compose down 
docker-compose up -d
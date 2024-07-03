#!/usr/bin/env bash

xhost +local:docker
docker run --rm --name=measure --env-file=../.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -e DISPLAY=192.168.178.195:0 -v /tmp/.X11-unix:/tmp/.X11-unix -it measure_ocr python3 ocr/main.py -t /usr/bin/tesseract -s rtp://@127.0.0.1:9988
xhost -local:docker

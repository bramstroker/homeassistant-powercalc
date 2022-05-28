# syntax=docker/dockerfile:1

FROM python:3.8-slim-buster

WORKDIR /app

COPY requirements.txt requirements.txt

RUN apt-get update
RUN apt-get install ffmpeg libsm6 libxext6 -y
RUN apt-get install tesseract-ocr -y
RUN pip3 install -r requirements.txt

COPY . .

CMD [ "python3", "measure.py"]

# syntax=docker/dockerfile:1

FROM python:3.8-slim-buster

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt
RUN mkdir -p /root
RUN touch /root/.python_hue

COPY . .

CMD [ "python3", "measure.py"]
# syntax=docker/dockerfile:1

FROM python:3.8-slim-buster

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

# Not copying local dir, export local dir to container.
#COPY . .

CMD [ "python3", "measure.py"]

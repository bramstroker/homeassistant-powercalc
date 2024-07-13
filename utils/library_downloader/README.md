# Docker build and push

```commandline
docker build --platform=linux/amd64 -t downloader .
docker image tag downloader bramgerritsen/powercalc-download-proxy:latest
docker push bramgerritsen/powercalc-download-proxy:latest
```

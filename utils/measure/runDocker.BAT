@echo off
REM Build & Launch on windows
if not exist DOCKER_IMAGE_BUILT (
  docker build -t measure_local .
  echo Done > DOCKER_IMAGE_BUILT
)
REM CYGWIN COMMAND : 
REM docker run --rm --name=measure_local -env-file=.env -v "$(cygpath -w $(pwd)):/app" -it  measure_local


SET SCRIPTPATH=%~dp0
docker run --rm --name=measure_local -env-file=.env -v "%SCRIPTPATH%:/app" -it  measure_local


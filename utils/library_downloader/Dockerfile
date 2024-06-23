# Dockerfile

FROM node:20.10.0-alpine3.17
RUN mkdir -p /opt/app
WORKDIR /opt/app
COPY package.json package-lock.json ./
RUN npm install
COPY . .
RUN npm run build
COPY dist/ .
EXPOSE 3000
CMD [ "npm", "start"]

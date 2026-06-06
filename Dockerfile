FROM node:20-alpine

WORKDIR /app

COPY frontend/package*.json ./frontend/
WORKDIR /app/frontend
RUN npm ci --legacy-peer-deps

COPY frontend/ ./

RUN chmod -R 755 node_modules/.bin
RUN npx react-scripts build

EXPOSE $PORT
CMD npx serve -s build -l $PORT
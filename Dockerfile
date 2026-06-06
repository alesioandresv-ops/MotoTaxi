FROM node:20-alpine

WORKDIR /app

COPY frontend/package*.json ./frontend/
WORKDIR /app/frontend
RUN npm ci --legacy-peer-deps
RUN chmod -R 755 node_modules/.bin

COPY frontend/ ./

RUN npx react-scripts build

EXPOSE $PORT
CMD ["npm", "run", "preview", "--host", "0.0.0.0", "--port", "$PORT"]
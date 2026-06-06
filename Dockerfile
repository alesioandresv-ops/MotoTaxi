FROM node:20-alpine AS builder

WORKDIR /app

COPY frontend/package*.json ./

RUN npm ci --legacy-peer-deps

COPY frontend/ ./

RUN npm run build

FROM node:20-alpine

WORKDIR /app

RUN npm install -g serve

COPY --from=builder /app/build ./build

EXPOSE 5173

CMD ["serve", "-s", "build", "-l", "5173"]

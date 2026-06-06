# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy lockfile and manifest first for layer caching
COPY frontend/package.json frontend/package-lock.json ./

RUN npm ci --legacy-peer-deps

# Copy the rest of the frontend source
COPY frontend/ ./

RUN npm run build

# Stage 2: Runtime — serve the static build with `serve`
FROM node:20-alpine AS runtime

WORKDIR /app

# Install serve globally to host the static build
RUN npm install -g serve

# Copy only the compiled build output
COPY --from=builder /app/build ./build

EXPOSE 5173

CMD ["serve", "-s", "build", "-l", "5173"]

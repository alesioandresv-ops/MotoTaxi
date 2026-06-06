FROM node:20-alpine

WORKDIR /app

# Copiar solo package.json primero para cachear las dependencias
COPY frontend/package*.json ./frontend/

WORKDIR /app/frontend

# Instalar dependencias con npm ci
RUN npm ci --legacy-peer-deps

# Copiar el resto del código
WORKDIR /app
COPY frontend ./frontend

WORKDIR /app/frontend

# Build
RUN npm run build

EXPOSE 5173

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]


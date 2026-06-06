FROM node:20-alpine

WORKDIR /app

# Copiar archivos del proyecto
COPY . .

# Build
WORKDIR /app/frontend
RUN npm ci --legacy-peer-deps && npm run build

# Start
EXPOSE 5173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]


# 🏍️ MotoTaxi - Aplicación de Mototaxi tipo Uber

Una aplicación web completa de mototaxi que permite a usuarios solicitar viajes y a conductores gestionar sus servicios.

## 📋 Características Principales

### Para Pasajeros
- ✅ Registro e inicio de sesión
- ✅ Solicitar viajes con ubicación de origen y destino
- ✅ Ver estado del viaje en tiempo real
- ✅ Información del conductor y vehículo
- ✅ Tarifa estimada antes de solicitar
- ✅ Historial de viajes
- ✅ Sistema de calificaciones
- ✅ Perfil con calificación promedio

### Para Conductores
- ✅ Registro e inicio de sesión
- ✅ Estado en línea/fuera de línea
- ✅ Ver viajes disponibles
- ✅ Aceptar viajes
- ✅ Gestionar estado del viaje (solicitado → en progreso → completado)
- ✅ Historial de viajes completados
- ✅ Seguimiento de ganancias del día
- ✅ Estadísticas de viajes
- ✅ Sistema de calificaciones
- ✅ Consejos para mejorar el servicio

## 🚀 Cómo Usar

### Opción Rápida (Sin Instalación)

1. **Abre el archivo `index.html`** en tu navegador web:
   ```
   c:\Users\Andrés N\Desktop\MotoTaxi\index.html
   ```

2. **Haz clic en "Demo Pasajero"** o **"Demo Conductor"** para acceder inmediatamente

3. ¡Comienza a usar la aplicación!

### Usuarios de Demo

**Pasajero Demo:**
- 👤 Nombre: Juan Pasajero
- ⭐ Calificación: 4.8

**Conductor Demo:**
- 👤 Nombre: Carlos Conductor
- ⭐ Calificación: 4.9

## 💻 Tecnología Utilizada

- **Frontend**: HTML5, CSS3, JavaScript Vanilla
- **Almacenamiento**: Estado en memoria (datos se resetean al recargar)
- **Diseño**: Responsive (compatible con dispositivos móviles)
- **Iconos**: Emojis integrados

## 📁 Estructura del Proyecto

```
MotoTaxi/
├── index.html          # Aplicación principal (HTML + CSS + JavaScript)
├── README.md           # Este archivo
├── backend/            # Archivos del servidor Node.js (opcional)
│   ├── package.json
│   └── server.js
└── frontend/           # Archivos React (para desarrollo futuro)
    ├── package.json
    ├── public/
    │   └── index.html
    └── src/
        ├── App.js
        ├── index.js
        ├── pages/
        │   ├── Login.js
        │   ├── Dashboard.js
        │   └── DriverDashboard.js
        └── components/
```

## 🎨 Interfaz de Usuario

### Pantalla de Login
- Campos de correo y contraseña
- Botones de demo rápido para pruebas
- Diseño moderno con gradiente de colores

### Dashboard del Pasajero
- Mapa interactivo (placeholder)
- Formulario para solicitar viajes
- Estado del viaje con actualizaciones
- Información del conductor
- Historial de viajes
- Calificación promedio

### Dashboard del Conductor
- Estado en línea/fuera de línea
- Lista de viajes disponibles
- Detalles del viaje activo
- Control de acciones (iniciar, completar)
- Estadísticas del día
- Historial de viajes completados
- Ganancias del día

## 🔧 Funcionalidades Simuladas

La aplicación incluye simulaciones para demostración:

1. **Aceptación de Viaje**: El conductor acepta el viaje con un clic
2. **Cambio de Estado**: El viaje pasa automáticamente por estados (requested → accepted → ongoing)
3. **Calificación Dinámica**: Se actualiza con las nuevas calificaciones
4. **Ganancias**: Se calculan basadas en viajes completados

## 📊 Estados del Viaje

```
requested   → El pasajero solicita un viaje
    ↓
accepted    → El conductor acepta el viaje
    ↓
ongoing     → El viaje está en progreso
    ↓
completed   → El viaje se completó exitosamente
```

## 🌐 Colores y Tema

- **Primario**: #667eea (Azul Violeta)
- **Secundario**: #764ba2 (Púrpura)
- **Conductor**: #1e3c72 (Azul Oscuro)
- **Éxito**: #4caf50 (Verde)
- **Advertencia**: #ff9800 (Naranja)
- **Error**: #ff6b6b (Rojo)

## 📱 Responsividad

La aplicación es completamente responsive y funciona en:
- ✅ Computadoras de escritorio
- ✅ Tablets
- ✅ Teléfonos móviles

## 🚀 Próximas Características (Futuro)

- Integración con mapas reales (Google Maps API)
- Geolocalización en tiempo real
- Chat en vivo entre pasajero y conductor
- Métodos de pago integrados
- Reseñas detalladas
- Sistema de notificaciones push
- Backend con base de datos persistente

## 📝 Notas

- Los datos se almacenan en memoria del navegador
- Al recargar la página, todos los datos se resetean
- Para persistencia, considera implementar un backend con base de datos

## 🤝 Contribuciones

Este proyecto es un prototipo de demostración. Siéntete libre de modificar y mejorar.

## 📄 Licencia

Proyecto educativo - Uso libre

---

**Creado**: 28 de Mayo de 2026
**Versión**: 1.0.0

¡Disfruta usando MotoTaxi! 🏍️

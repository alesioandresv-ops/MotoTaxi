# 📦 Instalación - MotoTaxi

## ⚡ Inicio Rápido (Recomendado)

### Paso 1: Abrir la Aplicación
1. Navega a: `c:\Users\Andrés N\Desktop\MotoTaxi\`
2. **Haz doble clic en `index.html`** para abrir en tu navegador
3. ¡La aplicación se abrirá automáticamente!

### Paso 2: Acceder como Pasajero o Conductor
En la pantalla de inicio, tienes dos opciones:

**Opción A: Demo Pasajero**
- Haz clic en el botón "👤 Demo Pasajero"
- Acceso instantáneo como: Juan Pasajero
- Puedes solicitar viajes inmediatamente

**Opción B: Demo Conductor**
- Haz clic en el botón "🏍️ Demo Conductor"
- Acceso instantáneo como: Carlos Conductor
- Puedes ver viajes disponibles e ir en línea

## 🌐 Navegadores Soportados

✅ **Funcionan correctamente:**
- Chrome/Chromium (recomendado)
- Firefox
- Edge
- Safari
- Opera

## 📂 Archivos del Proyecto

```
c:\Users\Andrés N\Desktop\MotoTaxi\
│
├── 📄 index.html          ← Abre esto para ejecutar la app
├── 📄 README.md           ← Documentación completa
├── 📄 INSTALL.md          ← Este archivo
│
├── 📁 backend/            ← Código del servidor (opcional)
│   ├── package.json
│   └── server.js
│
└── 📁 frontend/           ← Código React (para desarrollo)
    ├── package.json
    ├── public/
    └── src/
```

## ✨ Características que Puedes Probar

### Como Pasajero:
1. ✅ Completa los campos de origen y destino
2. ✅ Solicita un viaje
3. ✅ Observa cómo el estado cambia a "aceptado"
4. ✅ El viaje cambia automáticamente a "en progreso"
5. ✅ Cancela viajes si lo deseas
6. ✅ Visualiza tu historial de viajes

### Como Conductor:
1. ✅ Activa el modo "En Línea" (botón verde)
2. ✅ Verás viajes disponibles
3. ✅ Haz clic en "Aceptar" para tomar un viaje
4. ✅ Inicia el viaje con el botón "🚀 Iniciar Viaje"
5. ✅ Completa el viaje con "✅ Completar Viaje"
6. ✅ Observa cómo se actualiza: ganancias, estadísticas y historial

## 🔍 Solución de Problemas

### El archivo no abre
**Solución:** 
- Intenta hacer clic derecho en `index.html`
- Selecciona "Abrir con"
- Elige tu navegador preferido (Chrome, Firefox, etc.)

### Los botones no funcionan
**Solución:**
- Recarga la página (F5 o Ctrl+R)
- Limpia el caché del navegador (Ctrl+Shift+Delete)
- Intenta en modo incógnito

### Los datos desaparecen al recargar
**Comportamiento normal:** Los datos se almacenan en memoria, por lo que se resetean al recargar la página. Esto es solo una demostración.

### El navegador muestra errores en la consola
**No te preocupes:** La aplicación funciona correctamente a pesar de los errores menores en la consola. Estos se corregirán en versiones futuras.

## 📋 Requisitos del Sistema

- Cualquier navegador web moderno (instalado en tu computadora)
- Internet Explorer NO es compatible (es muy antiguo)
- No requiere instalación de software adicional
- No requiere Node.js ni npm para usar la versión HTML

## 🚀 Para Desarrolladores (Opcional)

Si deseas trabajar con la versión Node.js + React:

### Requisitos Previos:
- Node.js 14+ instalado
- npm o yarn

### Backend (Express):
```bash
cd "c:\Users\Andrés N\Desktop\MotoTaxi\backend"
npm install
npm start
```
El servidor estará disponible en: `http://localhost:3001`

### Frontend (React):
```bash
cd "c:\Users\Andrés N\Desktop\MotoTaxi\frontend"
npm install
npm start
```
La aplicación se abrirá en: `http://localhost:3000`

## 💡 Consejos

1. **Prueba ambas vistas**: Abre dos pestañas del navegador, una como pasajero y otra como conductor
2. **Usa el Historial**: Para ver todos los viajes que has completado
3. **Observa las Estadísticas**: Verás cómo se actualizan las ganancias del conductor
4. **Experimenta con Cancelaciones**: Prueba cancelar un viaje como pasajero

## 🎨 Personalización

Para cambiar colores, estilos o textos:
1. Abre `index.html` en un editor de texto (Notepad++, VS Code, etc.)
2. Busca la sección `<style>` 
3. Realiza cambios
4. Guarda y recarga la página en el navegador

## 📞 Soporte

Si tienes problemas:
1. Asegúrate de estar en un navegador moderno
2. Recarga completamente la página (Ctrl+F5)
3. Intenta en otro navegador
4. Revisa la consola del navegador para mensajes de error (F12)

## 🎯 Próximos Pasos

Después de explorar la aplicación:
1. Personaliza los colores y estilos
2. Agrega más funcionalidades
3. Integra un backend real
4. Conecta con una base de datos
5. ¡Lanza tu aplicación!

---

**¡Disfruta explorando MotoTaxi! 🏍️**

Última actualización: 28 de Mayo de 2026

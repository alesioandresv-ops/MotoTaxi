Exponer MotoTaxi al público (rápido) — ngrok

Requisitos rápidos:
- Tener el backend corriendo localmente: `npm start` en `backend/`.
- Instalar ngrok: https://ngrok.com/ (registro y `ngrok authtoken <token>`)

1) Ejecuta el backend:

```powershell
cd /d "C:\Users\Andrés N\Desktop\MotoTaxi\backend"
npm start
```

2) Abre ngrok para el puerto del backend (por defecto 3001):

```powershell
ngrok http 3001
```

3) Ngrok mostrará una URL pública (ej. `https://abcd-1234.ngrok.io`). Copia esa URL.

4) Configura el frontend para usar esa URL como API. En `frontend/.env` añade o actualiza:

```env
REACT_APP_API_URL=https://abcd-1234.ngrok.io
```

5) Reinicia el frontend:

```powershell
cd /d "C:\Users\Andrés N\Desktop\MotoTaxi\frontend"
npm start
```

6) Abre en el celular la URL que ngrok provee para la app frontend si la expones también, o usa la IP pública del PC + puerto 3000; si solo expusiste backend con ngrok, abre el frontend en la IP del PC y las llamadas al backend irán por ngrok si `REACT_APP_API_URL` apunta a ngrok.

Notas:
- Ngrok free rota las URLs — si necesitas una URL estable, adquiere un plan o despliega en la nube.
- Asegúrate de usar `https://` cuando ngrok genere HTTPS para evitar bloqueos de mixed-content en navegadores.

Despliegue recomendado (permanente)
- Opción simple: Render, Railway, Heroku, Fly.io. Crea un repo, conecta el servicio y despliega `backend` como app Node.js y `frontend` como app estática (o construir en `backend` y servir desde Express). Estos servicios ofrecen una URL pública estable.
- En producción asegúrate de:
  - Usar variables de entorno `PORT` y `NODE_ENV=production`.
  - Configurar CORS restringiendo orígenes si es necesario (actualmente `app.use(cors())` permite todos).
  - Proteger credenciales (no subir `.env` a git).

Firewall y red
- Si alojas desde tu PC, debes abrir puertos en tu router (NAT) y en el firewall de Windows (no recomendado para producción).
- Comando PowerShell (admin) para permitir el puerto 3001:

```powershell
New-NetFirewallRule -DisplayName "MotoTaxi API" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3001
```

Resumen rápido — solución inmediata:
- Usa ngrok para exponer backend públicamente y configura `REACT_APP_API_URL` en `frontend/.env` con la URL de ngrok, reinicia el frontend y prueba desde el celular.

Si quieres, puedo:
- Generar el `.env` con la URL pública si me das la URL de ngrok.
- Preparar pasos para desplegar en Render/Heroku con comandos concretos.

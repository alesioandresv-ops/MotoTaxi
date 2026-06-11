const getApiUrl = () => {
  // Si hay una variable de entorno, usarla
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }

  // En desarrollo local con react-scripts, usar el backend de localhost:3001
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'http://localhost:3001';
  }

  // En producción o en una URL pública, asumir el mismo host al servir build desde backend.
  return window.location.origin;
};

export const API_URL = getApiUrl();

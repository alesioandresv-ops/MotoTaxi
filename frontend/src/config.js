const getApiUrl = () => {
  // Si hay una variable de entorno, usarla
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }

  // En desarrollo, detectar la URL basado en el hostname actual
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'http://localhost:3001';
  }

  // Si está en otra IP (celular/red local), usar esa misma IP con puerto 3001
  return `http://${window.location.hostname}:3001`;
};

export const API_URL = getApiUrl();

const getApiUrl = () => {
	const envUrl = process.env.REACT_APP_API_URL;
	if (envUrl) {
		try {
			const u = new URL(envUrl);
			// If page is HTTPS and envUrl is http://localhost, ignore envUrl to avoid mixed-content
			if (window.location.protocol === 'https:' && u.protocol === 'http:' && (u.hostname === 'localhost' || u.hostname === '127.0.0.1')) {
				// fall through
			} else {
				return envUrl;
			}
		} catch (e) {
			return envUrl;
		}
	}

	if (window && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
		return 'http://localhost:3001';
	}

	// In production, assume the API is served from the same origin
	return window.location.origin;
};

export const API_URL = getApiUrl();

export default API_URL;

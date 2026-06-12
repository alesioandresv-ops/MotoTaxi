const getApiUrl = () => {
	const envUrl = (process.env.REACT_APP_API_URL || '').trim();
	if (envUrl) {
		try {
			const u = new URL(envUrl);
			if (window.location.protocol === 'https:' && u.protocol === 'http:') {
				if (u.hostname === window.location.hostname || u.hostname === 'localhost' || u.hostname === '127.0.0.1') {
					return window.location.origin;
				}
				return envUrl.replace(/^http:/, 'https:');
			}
			return envUrl;
		} catch (e) {
			return envUrl;
		}
	}

	if (window && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
		return 'http://localhost:3001';
	}

	// In production, use the same origin to avoid mixed-content issues.
	return window.location.origin;
};

export const API_URL = getApiUrl();

export default API_URL;

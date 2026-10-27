const API_BASE_URL = window.location.protocol === "file:"
    ? "http://127.0.0.1:8000"
    : window.location.origin;

async function apiRequest(path, options) {
    const response = await fetch(API_BASE_URL + path, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options && options.headers)
        }
    });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.detail || "The server could not complete the request.");
    }

    return data;
}

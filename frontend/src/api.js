const API_BASE_URL = window.location.origin;

async function apiRequest(path, options) {
    if (window.location.protocol === "file:") {
        throw new Error("Open SkillTrack through the backend URL to use account features.");
    }

    const response = await fetch(API_BASE_URL + path, {
        ...options,
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            ...(options && options.headers)
        }
    });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        const error = new Error(data.detail || "The server could not complete the request.");
        error.status = response.status;
        throw error;
    }

    return data;
}

async function apiLogout() {
    await apiRequest("/auth/logout", { method: "POST" });
    localStorage.removeItem("currentUser");
    localStorage.removeItem("currentUserId");
}

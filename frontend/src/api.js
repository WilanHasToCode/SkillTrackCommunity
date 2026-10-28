const API_BASE_URL = window.location.origin;

function formatApiError(data) {
    const fallback = "The server could not complete the request.";
    const detail = data && data.detail;

    if (typeof detail === "string") {
        const safeMessages = [
            "Username and email are required.",
            "That username or email is already registered.",
            "Invalid username or password.",
            "Authentication required.",
            "Invalid or expired session.",
            "Administrator access required.",
            "Password recovery email is not configured.",
            "Reset link is invalid or expired.",
            "You can only view your own profile.",
            "Account not found.",
            "You can only update your own profile.",
            "Current password is incorrect.",
            "Provide a new username or a new password.",
            "Username cannot be empty.",
            "That username is already registered.",
            "Skill not found.",
            "Post not found.",
            "Post content cannot be empty.",
            "You can only edit your own posts.",
            "Skill or module not found.",
            "Module not found.",
            "Skill not found.",
            "This module is already completed.",
            "The module assessment is not fully configured.",
            "The active attempt has no next question.",
            "No question is ready for this attempt step.",
            "The question is not the expected attempt question.",
            "This question has already been answered.",
            "This assessment attempt is already completed.",
            "Assessment attempt not found.",
            "You cannot access another user's attempt.",
            "You cannot answer another user's attempt."
        ];
        return safeMessages.includes(detail) ? detail : fallback;
    }

    if (Array.isArray(detail)) {
        const fieldNames = {
            username: "Username",
            email: "Email",
            password: "Password",
            new_password: "Password",
            content: "Post content",
            token: "Reset link",
            question_id: "Question",
            selected_option: "Answer"
        };
        const messages = detail.map(function (item) {
            if (!item || !Array.isArray(item.loc) || typeof item.type !== "string") {
                return "Please check the information you entered.";
            }

            const field = fieldNames[item.loc[item.loc.length - 1]];
            if (!field) {
                return "Please check the information you entered.";
            }
            if (item.type === "missing") {
                return field + " is required.";
            }

            const limits = {
                username: [1, 50],
                email: [3, 100],
                password: [12, 128],
                new_password: [12, 128],
                content: [1, 5000],
                token: [1, 128]
            };
            const name = item.loc[item.loc.length - 1];
            const range = limits[name];
            if (item.type === "string_too_short" && range) {
                return field + " must be at least " + range[0] + " characters.";
            }
            if (item.type === "string_too_long" && range) {
                return field + " must be " + range[1] + " characters or fewer.";
            }
            return field + " is invalid.";
        });

        return Array.from(new Set(messages)).join(" ") || fallback;
    }

    return fallback;
}

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
        const error = new Error(formatApiError(data));
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

var username = localStorage.getItem("currentUser") || "Member";
var userId = Number(localStorage.getItem("currentUserId"));

function renderProfile(profile) {
    username = profile.username;
    var letter = username.charAt(0).toUpperCase();
    localStorage.setItem("currentUser", username);
    document.getElementById("profileName").textContent = username;
    document.getElementById("profileEmail").textContent = profile.email;
    document.getElementById("avatar").textContent = letter;
    document.getElementById("bigAvatar").textContent = letter;
}

// Shows a message. type is "ok" (green) or "err" (red)
function showMessage(text, type) {
    var box = document.getElementById("msg");
    box.className = "msg " + type;
    box.textContent = text;
}

// Edit Profile button: opens the edit box
function showEditBox() {
    document.getElementById("msg").className = "msg";
    document.getElementById("editBox").className = "edit-card card";
}

// Cancel button: closes the edit box
function hideEditBox() {
    document.getElementById("editBox").className = "edit-card card hidden";
}

async function loadProfile() {
    if (!Number.isInteger(userId) || userId < 1) {
        showMessage("Please log in again to view your profile.", "err");
        return;
    }

    try {
        var profile = await apiRequest("/users/" + userId + "/profile");
        renderProfile(profile);
    } catch (error) {
        showMessage("Could not load profile: " + error.message, "err");
    }
}

async function saveProfile() {
    var newName = document.getElementById("newUser").value.trim();
    var currentPassword = document.getElementById("currentPass").value;
    var newPassword = document.getElementById("newPass").value;

    if (newName === "" && newPassword === "") {
        showMessage("Type a new username or a new password.", "err");
        return;
    }

    if (!currentPassword) {
        showMessage("Enter your current password to confirm the change.", "err");
        return;
    }

    if (newPassword !== "" && newPassword.length < 3) {
        showMessage("Password must be at least 3 characters.", "err");
        return;
    }

    if (!Number.isInteger(userId) || userId < 1) {
        showMessage("Please log in again before updating your profile.", "err");
        return;
    }

    var payload = { current_password: currentPassword };
    if (newName !== "") {
        payload.username = newName;
    }
    if (newPassword !== "") {
        payload.new_password = newPassword;
    }

    var saveButton = document.getElementById("saveProfileBtn");
    saveButton.disabled = true;
    try {
        var profile = await apiRequest("/users/" + userId + "/profile", {
            method: "PATCH",
            body: JSON.stringify(payload)
        });
        renderProfile(profile);
        document.getElementById("newUser").value = "";
        document.getElementById("currentPass").value = "";
        document.getElementById("newPass").value = "";
        hideEditBox();
        showMessage("Profile updated.", "ok");
    } catch (error) {
        showMessage(error.message, "err");
    } finally {
        saveButton.disabled = false;
    }
}

// Log Out button: go back to the login page
function logOut() {
    localStorage.removeItem("currentUser");
    localStorage.removeItem("currentUserId");
    window.location.href = "../../Main.html";
}

loadProfile();
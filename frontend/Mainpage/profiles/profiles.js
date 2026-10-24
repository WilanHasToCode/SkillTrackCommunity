// Profile.js
// Changes are kept in memory only, so they reset when the page is refreshed.

var username = localStorage.getItem("currentUser") || "Member";
document.getElementById("profileName").textContent = username;
document.getElementById("avatar").textContent = username.charAt(0).toUpperCase();
document.getElementById("bigAvatar").textContent = username.charAt(0).toUpperCase();

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

// Save button
function saveProfile() {
    var newName = document.getElementById("newUser").value.trim();
    var newPassword = document.getElementById("newPass").value;

    // Nothing typed
    if (newName === "" && newPassword === "") {
        showMessage("Type a new username or a new password.", "err");
        return;
    }

    // Password too short
    if (newPassword !== "" && newPassword.length < 4) {
        showMessage("Password must be at least 4 characters.", "err");
        return;
    }

    // New username: change the name and the letter in the circles
    if (newName !== "") {
        var letter = newName.charAt(0).toUpperCase();
        localStorage.setItem("currentUser", newName);
        document.getElementById("profileName").textContent = newName;
        document.getElementById("avatar").textContent = letter;
        document.getElementById("bigAvatar").textContent = letter;
    }

    // Clear the boxes and close the edit box
    document.getElementById("newUser").value = "";
    document.getElementById("newPass").value = "";
    hideEditBox();
    showMessage("Profile updated.", "ok");
}

// Log Out button: go back to the login page
function logOut() {
    localStorage.removeItem("currentUser");
    localStorage.removeItem("currentUserId");
    window.location.href = "../Main.html";
}
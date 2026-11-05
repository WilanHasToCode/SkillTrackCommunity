var resetToken = new URLSearchParams(window.location.search).get("token");
var passwordInput = document.getElementById("newPasswordInput");
var resetButton = document.getElementById("resetPasswordBtn");
var resetResult = document.getElementById("resetResult");

function showResetResult(message, success) {
    resetResult.textContent = message;
    resetResult.className = success ? "error-box success" : "error-box";
    resetResult.style.display = "block";
}

if (!resetToken) {
    resetButton.disabled = true;
    showResetResult("This reset link is invalid or expired.", false);
}

resetButton.addEventListener("click", async function () {
    var newPassword = passwordInput.value;
    if (!resetToken) {
        return;
    }
    if (newPassword.length < 12) {
        showResetResult("Password must be at least 12 characters.", false);
        return;
    }

    resetButton.disabled = true;
    try {
        var result = await apiRequest("/auth/reset-password", {
            method: "POST",
            body: JSON.stringify({ token: resetToken, new_password: newPassword })
        });
        showResetResult(result.message, true);
        passwordInput.value = "";
    } catch (error) {
        showResetResult(error.message, false);
    } finally {
        resetButton.disabled = false;
    }
});

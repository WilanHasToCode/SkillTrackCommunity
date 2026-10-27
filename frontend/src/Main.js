// Grab HTML elements
const loginTab = document.getElementById('loginTab');
const signupTab = document.getElementById('signupTab');
const submitBtn = document.getElementById('submitBtn');
const usernameLabel = document.getElementById('usernameLabel');
const userInput = document.getElementById('userInput');
const passInput = document.getElementById('passInput');
const emailGroup = document.getElementById('emailGroup');
const emailInput = document.getElementById('emailInput');
const errorBox = document.getElementById('errorBox');
const forgotLink = document.getElementById('forgotLink');
const resetRequestBox = document.getElementById('resetRequestBox');
const resetEmailInput = document.getElementById('resetEmailInput');
const requestResetBtn = document.getElementById('requestResetBtn');
const cancelResetBtn = document.getElementById('cancelResetBtn');
const resetMessage = document.getElementById('resetMessage');

let isLoginMode = true;

// Switch to Login View
loginTab.addEventListener('click', () => {
    isLoginMode = true;
    loginTab.classList.add('active');
    signupTab.classList.remove('active');
    submitBtn.textContent = 'Log In';
    usernameLabel.textContent = 'Username';
    userInput.placeholder = 'Type Username';
    forgotLink.style.display = 'block';
    resetRequestBox.classList.add('hidden');
    emailGroup.classList.add('hidden');
    errorBox.style.display = 'none';
});

// Switch to Register (Sign Up) View
signupTab.addEventListener('click', () => {
    isLoginMode = false;
    signupTab.classList.add('active');
    loginTab.classList.remove('active');
    submitBtn.textContent = 'Sign Up';
    usernameLabel.textContent = 'Create Username';
    userInput.placeholder = 'Choose a Username';
    forgotLink.style.display = 'none';
    resetRequestBox.classList.add('hidden');
    emailGroup.classList.remove('hidden');
    errorBox.style.display = 'none';
});

forgotLink.addEventListener('click', (event) => {
    event.preventDefault();
    resetRequestBox.classList.remove('hidden');
    resetMessage.style.display = 'none';
    resetEmailInput.focus();
});

cancelResetBtn.addEventListener('click', () => {
    resetRequestBox.classList.add('hidden');
});

requestResetBtn.addEventListener('click', async () => {
    const email = resetEmailInput.value.trim();
    if (!email) {
        resetMessage.textContent = "Enter the email address for your account.";
        resetMessage.className = "error-box";
        resetMessage.style.display = 'block';
        return;
    }

    requestResetBtn.disabled = true;
    try {
        const result = await apiRequest("/auth/forgot-password", {
            method: "POST",
            body: JSON.stringify({ email })
        });
        resetMessage.textContent = result.message;
        resetMessage.className = "error-box success";
    } catch (error) {
        resetMessage.textContent = error.message;
        resetMessage.className = "error-box";
    } finally {
        resetMessage.style.display = 'block';
        requestResetBtn.disabled = false;
    }
});

submitBtn.addEventListener('click', async () => {
    const username = userInput.value.trim();
    const password = passInput.value;
    const email = emailInput.value.trim();

    if (!username || !password || (!isLoginMode && !email)) {
        errorBox.textContent = "Please enter all required account details.";
        errorBox.style.display = 'block';
        return;
    }

    submitBtn.disabled = true;
    try {
        const account = isLoginMode
            ? await apiRequest("/auth/login", {
                method: "POST",
                body: JSON.stringify({ username, password })
            })
            : await apiRequest("/auth/register", {
                method: "POST",
                body: JSON.stringify({ username, password, email })
            });

        errorBox.style.display = 'none';
        localStorage.setItem("currentUser", account.username);
        localStorage.setItem("currentUserId", String(account.user_id));
        window.location.href = "pages/DashBoard/Dashboard.html";
    } catch (error) {
        errorBox.textContent = error.message;
        errorBox.style.display = 'block';
    } finally {
        submitBtn.disabled = false;
    }
});
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
    emailGroup.classList.remove('hidden');
    errorBox.style.display = 'none';
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
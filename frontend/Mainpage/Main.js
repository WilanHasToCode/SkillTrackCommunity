// Grab HTML elements
const loginTab = document.getElementById('loginTab');
const signupTab = document.getElementById('signupTab');
const submitBtn = document.getElementById('submitBtn');
const usernameLabel = document.getElementById('usernameLabel');
const userInput = document.getElementById('userInput');
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
    errorBox.style.display = 'none';
});

// Simulate Flowchart Decision Paths on Button Click
submitBtn.addEventListener('click', () => {
    const val = userInput.value.trim();

    if (val === "") {
        // Trigger Error State matching flowchart loop
        errorBox.textContent = "Please fill in this field.";
        errorBox.style.display = 'block';
    } else {
        errorBox.style.display = 'none';
        if (isLoginMode) {
            alert("Login Successful! Moving to Dashboard (A)...");
        } else {
            alert("Registration Successful! Account created (1)...");
        }
    }
});
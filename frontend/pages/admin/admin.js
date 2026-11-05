var users = [];
var posts = [];

function showUsers() {
    var list = document.getElementById("userList");
    var template = document.getElementById("userTemplate");
    list.innerHTML = "";

    users.forEach(function (user) {
        var card = template.content.cloneNode(true);
        card.querySelector(".user-name").textContent = user.username;
        card.querySelector(".user-email").textContent = user.email;
        card.querySelector(".user-role").textContent = user.is_admin ? "Admin" : "Member";
        card.querySelector(".view-user-btn").addEventListener("click", function () {
            showUserDetail(user);
        });
        card.querySelector(".edit-user-btn").addEventListener("click", function () {
            editUserName(user);
        });
        card.querySelector(".reset-user-password-btn").addEventListener("click", function () {
            resetUserPassword(user);
        });
        list.appendChild(card);
    });

    document.getElementById("noUsers").className = users.length === 0 ? "card" : "card hidden";
}

function showPosts() {
    var list = document.getElementById("postList");
    var template = document.getElementById("postTemplate");
    list.innerHTML = "";

    posts.forEach(function (post) {
        var card = template.content.cloneNode(true);
        card.querySelector(".post-author").textContent = post.author;
        card.querySelector(".post-likes").textContent = (post.likes || 0) + " likes";
        card.querySelector(".post-text").textContent = post.text;
        card.querySelector(".view-post-btn").addEventListener("click", function () {
            showPostDetail(post);
        });
        card.querySelector(".delete-post-btn").addEventListener("click", function () {
            deletePost(post);
        });
        list.appendChild(card);
    });

    document.getElementById("noPosts").className = posts.length === 0 ? "card" : "card hidden";
}

function showView(name) {
    var showingUsers = name === "users";
    document.getElementById("usersView").className = showingUsers ? "" : "hidden";
    document.getElementById("postsView").className = showingUsers ? "hidden" : "";
    document.getElementById("userDetailView").className = "hidden";
    document.getElementById("postDetailView").className = "hidden";
    document.getElementById("navUsers").className = showingUsers ? "nav-btn active" : "nav-btn";
    document.getElementById("navPosts").className = showingUsers ? "nav-btn" : "nav-btn active";
    document.getElementById("pageTitle").textContent = showingUsers ? "Member Accounts" : "Public Posts";
}

function showUserDetail(user) {
    document.getElementById("usersView").className = "hidden";
    document.getElementById("postsView").className = "hidden";
    document.getElementById("userDetailView").className = "";
    document.getElementById("postDetailView").className = "hidden";
    document.getElementById("navUsers").className = "nav-btn active";
    document.getElementById("navPosts").className = "nav-btn";
    document.getElementById("pageTitle").textContent = "Member Details";
    document.getElementById("detailUserName").textContent = user.username;
    document.getElementById("detailUserEmail").textContent = user.email;
    document.getElementById("detailUserRole").textContent = user.is_admin ? "Admin" : "Member";
}

function showPostDetail(post) {
    document.getElementById("usersView").className = "hidden";
    document.getElementById("postsView").className = "hidden";
    document.getElementById("userDetailView").className = "hidden";
    document.getElementById("postDetailView").className = "";
    document.getElementById("navUsers").className = "nav-btn";
    document.getElementById("navPosts").className = "nav-btn active";
    document.getElementById("pageTitle").textContent = "Post Details";
    document.getElementById("detailPostAuthor").textContent = post.author;
    document.getElementById("detailPostLikes").textContent = (post.likes || 0) + " likes";
    document.getElementById("detailPostText").textContent = post.text;
}

async function initializeAdmin() {
    try {
        var currentUser = await apiRequest("/auth/me");
        if (!currentUser.is_admin) {
            window.location.replace("../../Main.html");
            return;
        }

        var results = await Promise.all([
            apiRequest("/users"),
            apiRequest("/posts")
        ]);
        users = results[0].data;
        posts = results[1];
        showUsers();
        showPosts();
    } catch (error) {
        if (error.status === 401 || error.status === 403) {
            window.location.replace("../../Main.html");
            return;
        }
        var accessError = document.getElementById("adminAccessError");
        accessError.textContent = "Could not load admin data: " + error.message;
        accessError.className = "card";
    }
}

async function editUserName(user) {
    var username = window.prompt("Enter a new username:", user.username);
    if (username === null) return;
    username = username.trim();
    if (!username) {
        showAdminError("Username cannot be empty.");
        return;
    }
    try {
        var updated = await apiRequest("/admin/users/" + user.user_id, {
            method: "PATCH",
            body: JSON.stringify({ username: username })
        });
        user.username = updated.username;
        showUsers();
    } catch (error) {
        showAdminError(error.message);
    }
}

async function resetUserPassword(user) {
    var password = window.prompt("Enter a new password of at least 12 characters:");
    if (password === null) return;
    if (password.length < 12) {
        showAdminError("Password must be at least 12 characters.");
        return;
    }
    try {
        await apiRequest("/admin/users/" + user.user_id, {
            method: "PATCH",
            body: JSON.stringify({ new_password: password })
        });
        showAdminError("Password reset for " + user.username + ".");
    } catch (error) {
        showAdminError(error.message);
    }
}

async function deletePost(post) {
    if (!window.confirm("Delete this public post? This cannot be undone.")) return;
    try {
        await apiRequest("/admin/posts/" + post.id, { method: "DELETE" });
        posts = posts.filter(function (item) { return item.id !== post.id; });
        showPosts();
        if (!document.getElementById("postDetailView").classList.contains("hidden")) {
            showView("posts");
        }
    } catch (error) {
        showAdminError(error.message);
    }
}

function showAdminError(message) {
    var box = document.getElementById("adminAccessError");
    box.textContent = message;
    box.className = "card";
}

async function logOut() {
    try {
        await apiLogout();
        window.location.href = "../../Main.html";
    } catch (error) {
        var accessError = document.getElementById("adminAccessError");
        accessError.textContent = "Could not log out: " + error.message;
        accessError.className = "card";
    }
}

initializeAdmin();

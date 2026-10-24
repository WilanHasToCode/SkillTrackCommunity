// Admin.js
// Sample data for now. When the backend is ready, this will come from the database.
// Changes are kept in memory only, so they reset when the page is refreshed.

// ----- Sample password reset requests -----
// status is "pending", "link sent" or "done"
var requests = [
    { username: "maria", gmail: "maria@gmail.com", time: "10 minutes ago", status: "pending" },
    { username: "john", gmail: "john@gmail.com", time: "1 hour ago", status: "pending" },
    { username: "ana", gmail: "ana@gmail.com", time: "Yesterday", status: "link sent" }
];

// ----- Sample public posts -----
var posts = [
    { author: "maria", time: "2 hours ago", text: "Just finished my first HTML page." },
    { author: "john", time: "Yesterday", text: "Does anyone know a good PostgreSQL tutorial?" }
];

// ----- Show the reset requests -----
function showRequests() {
    var list = document.getElementById("requestList");
    var template = document.getElementById("requestTemplate");
    var pending = 0;

    list.innerHTML = "";

    for (var i = 0; i < requests.length; i++) {
        var req = requests[i];
        if (req.status === "pending") {
            pending = pending + 1;
        }

        var card = template.content.cloneNode(true);
        card.querySelector(".req-user").textContent = req.username;
        card.querySelector(".req-gmail").textContent = req.gmail;
        card.querySelector(".req-time").textContent = req.time;
        card.querySelector(".tag").textContent = req.status;

        // The button changes with the status
        var button = card.querySelector(".act-btn");
        if (req.status === "pending") {
            button.textContent = "Create reset link";
        } else if (req.status === "link sent") {
            button.textContent = "Mark done";
        } else {
            button.className = "btn act-btn hidden";   // done: no button
        }
        button.setAttribute("onclick", "moveRequest(" + i + ")");

        list.appendChild(card);
    }

    // Show or hide the "no requests" message
    if (requests.length === 0) {
        document.getElementById("noRequests").className = "card";
    } else {
        document.getElementById("noRequests").className = "card hidden";
    }

    // Notification badge: number of pending requests
    document.getElementById("badge").textContent = pending;
    if (pending === 0) {
        document.getElementById("badge").className = "badge hidden";
    } else {
        document.getElementById("badge").className = "badge";
    }
}

// Create reset link / Mark done button
function moveRequest(index) {
    var req = requests[index];

    if (req.status === "pending") {
        req.status = "link sent";
        alert("Demo only. The real backend will make a one-time link. Email it to " + req.gmail + " from your own email.");
    } else if (req.status === "link sent") {
        req.status = "done";
    }

    showRequests();
}

// ----- Show the public posts -----
function showPosts() {
    var list = document.getElementById("postList");
    var template = document.getElementById("postTemplate");

    list.innerHTML = "";

    for (var i = 0; i < posts.length; i++) {
        var card = template.content.cloneNode(true);
        card.querySelector(".post-author").textContent = posts[i].author;
        card.querySelector(".post-time").textContent = posts[i].time;
        card.querySelector(".post-text").textContent = posts[i].text;
        card.querySelector(".delete-btn").setAttribute("onclick", "removePost(" + i + ")");
        list.appendChild(card);
    }

    if (posts.length === 0) {
        document.getElementById("noPosts").className = "card";
    } else {
        document.getElementById("noPosts").className = "card hidden";
    }
}

// Remove post button (the admin can remove any public post)
function removePost(index) {
    if (confirm("Remove this post from the community?")) {
        posts.splice(index, 1);
        showPosts();
    }
}

// ----- Switch between the two views -----
function showView(name) {
    if (name === "requests") {
        document.getElementById("requestsView").className = "";
        document.getElementById("postsView").className = "hidden";
        document.getElementById("navRequests").className = "nav-btn active";
        document.getElementById("navPosts").className = "nav-btn";
        document.getElementById("pageTitle").textContent = "Password Reset Requests";
    } else {
        document.getElementById("requestsView").className = "hidden";
        document.getElementById("postsView").className = "";
        document.getElementById("navRequests").className = "nav-btn";
        document.getElementById("navPosts").className = "nav-btn active";
        document.getElementById("pageTitle").textContent = "Public Posts";
    }
}

// Log Out button: go back to the login page
function logOut() {
    localStorage.removeItem("currentUser");
    window.location.href = "../Main.html";
}

// Show everything when the page opens
showRequests();
showPosts();
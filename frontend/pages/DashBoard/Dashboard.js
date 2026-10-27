// ----- Who is logged in? -----
var username = localStorage.getItem("currentUser") || "Member";
document.getElementById("profileName").textContent = "Username: " + username;
document.getElementById("avatar").textContent = username.charAt(0).toUpperCase();

var posts = [];
var editingId = null;

// Makes text safe to show on the page
function makeSafe(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// Shows a small message at the bottom for 2 seconds
function showToast(message) {
    var toast = document.getElementById("toast");
    toast.textContent = message;
    toast.className = "toast show";
    setTimeout(function () {
        toast.className = "toast";
    }, 2000);
}

// Draws all the posts on the page
function showPosts() {
    var html = "";

    for (var i = 0; i < posts.length; i++) {
        var post = posts[i];

        var heart = "♡";
        var likedClass = "";
        if (post.liked === true) {
            heart = "♥";
            likedClass = " liked";
        }

        html += '<div class="card">';
        html += '<div class="post-top">';
        html += '<div class="post-avatar">' + makeSafe(post.author.charAt(0).toUpperCase()) + '</div>';
        html += '<div><b>' + makeSafe(post.author) + '</b><div class="post-time">' + makeSafe(post.time) + '</div></div>';
        html += '</div>';
        html += '<p class="post-text">' + makeSafe(post.text) + '</p>';
        html += '<div class="post-actions">';
        html += '<button class="action-btn' + likedClass + '" onclick="likePost(' + post.id + ')">' + heart + ' ' + post.likes + '</button>';

        // Only your own posts have an Edit button
        if (post.author === username) {
            html += '<button class="action-btn" onclick="editPost(' + post.id + ')">Edit post</button>';
        }

        html += '</div></div>';
    }

    document.getElementById("feed").innerHTML = html;
    document.getElementById("emptyMessage").className = posts.length === 0 ? "card" : "card hidden";
}

function formatPostTime(createdAt) {
    var date = new Date(createdAt);
    if (Number.isNaN(date.getTime())) {
        return "";
    }
    return date.toLocaleString();
}

function mapPost(post) {
    return {
        id: post.id,
        author: post.author,
        time: post.time || (post.created_at ? formatPostTime(post.created_at) : "Community post"),
        text: post.text,
        likes: post.likes || 0,
        liked: post.liked === true
    };
}

async function loadPosts() {
    try {
        posts = (await apiRequest("/posts")).map(mapPost);
        showPosts();
    } catch (error) {
        showToast("Could not load posts: " + error.message);
    }
}

async function loadAccountNavigation() {
    try {
        var account = await apiRequest("/auth/me");
        if (account.is_admin) {
            document.getElementById("adminNav").classList.remove("hidden");
        }
    } catch (error) {
        if (error.status === 401) {
            window.location.replace("../../Main.html");
            return;
        }
        showToast("Could not verify account access: " + error.message);
    }
}

// Finds one post using its id
function findPost(id) {
    for (var i = 0; i < posts.length; i++) {
        if (posts[i].id === id) {
            return posts[i];
        }
    }
    return null;
}

// ----- Buttons -----

// Like Post? Click once to like, click again to unlike
async function likePost(id) {
    var post = findPost(id);
    if (!post) {
        return;
    }

    try {
        var result = await apiRequest("/posts/" + id + "/like", {
            method: post.liked ? "DELETE" : "PUT"
        });
        post.liked = result.liked;
        post.likes = result.likes;
        showPosts();
    } catch (error) {
        showToast("Could not update like: " + error.message);
    }
}

// Create Post button: opens the empty post box
function openComposer() {
    editingId = null;
    document.getElementById("composerTitle").textContent = "New post";
    document.getElementById("postBtn").textContent = "Post";
    document.getElementById("postText").value = "";
    document.getElementById("composer").className = "card";
    document.getElementById("postText").focus();
}

// Edit post button: opens the post box with the old text
function editPost(id) {
    editingId = id;
    document.getElementById("composerTitle").textContent = "Edit post";
    document.getElementById("postBtn").textContent = "Save";
    document.getElementById("postText").value = findPost(id).text;
    document.getElementById("composer").className = "card";
    document.getElementById("postText").focus();
}

// Cancel button: hides the post box
function closeComposer() {
    document.getElementById("composer").className = "card hidden";
    editingId = null;
}

// Post / Save button
async function savePost() {
    var text = document.getElementById("postText").value.trim();

    if (text === "") {
        showToast("Write something first.");
        return;
    }

    var postBtn = document.getElementById("postBtn");
    postBtn.disabled = true;
    try {
        var savedPost = await apiRequest(editingId === null ? "/posts" : "/posts/" + editingId, {
            method: editingId === null ? "POST" : "PUT",
            body: JSON.stringify({ content: text })
        });
        if (editingId === null) {
            savedPost.time = "Just now";
            posts.unshift(mapPost(savedPost));
            showToast("Posted!");
        } else {
            var index = posts.findIndex(function (post) { return post.id === editingId; });
            if (index !== -1) {
                savedPost.time = posts[index].time;
                savedPost.likes = posts[index].likes;
                savedPost.liked = posts[index].liked;
                posts[index] = mapPost(savedPost);
            }
            showToast("Post updated.");
        }
        closeComposer();
        showPosts();
    } catch (error) {
        showToast("Could not save post: " + error.message);
    } finally {
        postBtn.disabled = false;
    }
}

// Bell button: removes the red dot
function clearBell() {
    document.getElementById("dot").style.display = "none";
}

// Log Out: forget the user and go back to the login page
async function logOut() {
    try {
        await apiLogout();
        window.location.href = "../../Main.html";
    } catch (error) {
        showToast("Could not log out: " + error.message);
    }
}

// Restore a message shared from the skills page.
var draft = sessionStorage.getItem("draft");
if (draft !== null) {
    sessionStorage.removeItem("draft");
    openComposer();
    document.getElementById("postText").value = draft;
}

loadPosts();
loadAccountNavigation();
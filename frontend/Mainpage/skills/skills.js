// Skills.js
// Progress is kept in memory only, so it resets when the page is refreshed.

// ----- The list of skills (add your own here) -----
var skills = [
    { name: "HTML", info: "Structure web pages with markup.", progress: 0 },
    { name: "CSS", info: "Style and lay out web pages.", progress: 0 },
    { name: "JavaScript", info: "Add behavior to web pages.", progress: 0 },
    { name: "Python", info: "Write scripts and build the backend.", progress: 0 },
    { name: "PostgreSQL", info: "Store and read data in a database.", progress: 0 }
];

// Which skill is selected? -1 means none.
var selectedIndex = -1;

// Turns a percentage into a status word
function getStatus(percent) {
    if (percent >= 100) {
        return "Completed";
    }
    if (percent > 0) {
        return "In progress";
    }
    return "Not started";
}

// ----- Show all skills on the page -----
function showSkills() {
    var list = document.getElementById("skillList");
    var template = document.getElementById("skillTemplate");
    var total = 0;

    list.innerHTML = "";   // clear the old list

    for (var i = 0; i < skills.length; i++) {
        var skill = skills[i];
        total = total + skill.progress;

        // Make a copy of the skill layout from Skills.html and fill it in
        var card = template.content.cloneNode(true);
        card.querySelector(".skill-name").textContent = skill.name;
        card.querySelector(".tag").textContent = getStatus(skill.progress);
        card.querySelector(".bar-fill").style.width = skill.progress + "%";

        // Clicking a skill selects it
        var box = card.querySelector(".skill");
        box.setAttribute("onclick", "selectSkill(" + i + ")");
        if (i === selectedIndex) {
            box.className = "card skill selected";
        }

        list.appendChild(card);
    }

    // Track progress: the average of all skills
    var average = Math.round(total / skills.length);
    document.getElementById("overallText").textContent = "Overall: " + average + "%";
    document.getElementById("overallBar").style.width = average + "%";
}

// ----- Buttons -----

// View skill details: click a skill
function selectSkill(index) {
    selectedIndex = index;
    document.getElementById("skillName").textContent = skills[index].name;
    document.getElementById("skillInfo").textContent = skills[index].info;
    showSkills();
}

// Learn / Practice button: adds 10% progress (maximum 100%)
function practiceSkill() {
    if (selectedIndex === -1) {
        alert("Click a skill first.");
        return;
    }

    var skill = skills[selectedIndex];
    skill.progress = skill.progress + 10;
    if (skill.progress > 100) {
        skill.progress = 100;
    }
    showSkills();
}

// Share and post button: goes to the dashboard with the message ready to post
function shareSkill() {
    if (selectedIndex === -1) {
        alert("Click a skill first.");
        return;
    }

    var skill = skills[selectedIndex];
    var message = "I'm at " + skill.progress + "% in " + skill.name + "!";
    sessionStorage.setItem("draft", message);
    window.location.href = "../DashBoard/Dashboard.html";
}

// Log Out button: go back to the login page
function logOut() {
    localStorage.removeItem("currentUser");
    localStorage.removeItem("currentUserId");
    window.location.href = "../Main.html";
}

// Show the skills when the page opens
showSkills();
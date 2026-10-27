var skills = [];

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

    if (skills.length === 0) {
        list.textContent = "No skills are available yet.";
        document.getElementById("overallText").textContent = "Overall: 0%";
        document.getElementById("overallBar").style.width = "0%";
        return;
    }

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
    if (!skills[index]) {
        return;
    }
    selectedIndex = index;
    document.getElementById("skillName").textContent = skills[index].name;
    document.getElementById("skillInfo").textContent = skills[index].info;
    showSkills();
}

// Learn / Practice button: adds 10% progress (maximum 100%)
async function practiceSkill() {
    var skill = skills[selectedIndex];
    if (!skill) {
        alert("Click a skill first.");
        return;
    }

    var button = document.getElementById("practiceSkillBtn");
    button.disabled = true;
    try {
        var result = await apiRequest("/skills/" + skill.skill_id + "/practice", {
            method: "POST"
        });
        skill.progress = result.progress;
        showSkills();
    } catch (error) {
        alert("Could not save skill progress: " + error.message);
    } finally {
        button.disabled = false;
    }
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
async function logOut() {
    try {
        await apiLogout();
        window.location.href = "../../Main.html";
    } catch (error) {
        alert("Could not log out: " + error.message);
    }
}

async function loadSkills() {
    try {
        skills = await apiRequest("/skills");
        showSkills();
    } catch (error) {
        if (error.status === 401) {
            window.location.replace("../../Main.html");
            return;
        }
        document.getElementById("skillList").textContent =
            "Could not load skills: " + error.message;
    }
}

loadSkills();
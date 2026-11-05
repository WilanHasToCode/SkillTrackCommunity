var skills = [];
var selectedIndex = -1;
var learningModules = [];
var activeModule = null;
var activeLessonIndex = 0;
var activeAttempt = null;
var answerPending = false;
var showAnswerFeedback = false;
var categoryOrder = ["Sports & Physical Skills", "Coding & Digital Skills", "Everyday & Creative Skills", "Uncategorized"];

function getStatus(percent) {
    if (percent >= 100) return "Completed";
    if (percent > 0) return "In progress";
    return "Not started";
}
function makeElement(tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}
function showLearningMessage(message, isSuccess) {
    var element = document.getElementById("learningMessage");
    element.textContent = message || "";
    element.className = "learning-message" + (isSuccess ? " success" : "");
}
function redirectForAuth(error) {
    if (error.status === 401) {
        window.location.replace("../../Main.html");
        return true;
    }
    return false;
}
function showSkills() {
    var list = document.getElementById("skillList");
    var categoryTemplate = document.getElementById("skillTemplate");
    var cardTemplate = document.getElementById("skillCardTemplate");
    var total = 0;
    list.innerHTML = "";
    if (skills.length === 0) {
        list.textContent = "No skills are available yet.";
        document.getElementById("overallText").textContent = "Overall: 0%";
        document.getElementById("overallBar").style.width = "0%";
        return;
    }
    var groupedSkills = {};
    for (var i = 0; i < skills.length; i++) {
        var skill = skills[i];
        var category = categoryOrder.indexOf(skill.category) === -1 ? "Uncategorized" : skill.category;
        if (!groupedSkills[category]) groupedSkills[category] = [];
        groupedSkills[category].push({ skill: skill, index: i });
        total += skill.progress;
    }
    categoryOrder.forEach(function (categoryName) {
        var categorySkills = groupedSkills[categoryName];
        if (!categorySkills) return;
        var categoryCard = categoryTemplate.content.cloneNode(true);
        categoryCard.querySelector(".category-name").textContent = categoryName;
        var categorySkillsElement = categoryCard.querySelector(".category-skills");
        categorySkills.forEach(function (skillItem) {
            var card = cardTemplate.content.cloneNode(true);
            card.querySelector(".skill-name").textContent = skillItem.skill.name;
            card.querySelector(".tag").textContent = getStatus(skillItem.skill.progress);
            card.querySelector(".bar-fill").style.width = skillItem.skill.progress + "%";
            var box = card.querySelector(".skill");
            box.tabIndex = 0;
            box.setAttribute("role", "button");
            box.setAttribute("aria-label", "Select " + skillItem.skill.name);
            box.addEventListener("click", function () { selectSkill(skillItem.index); });
            box.addEventListener("keydown", function (event) {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    selectSkill(skillItem.index);
                }
            });
            if (skillItem.index === selectedIndex) box.className = "card skill selected";
            categorySkillsElement.appendChild(card);
        });
        list.appendChild(categoryCard);
    });
    var average = Math.round(total / skills.length);
    document.getElementById("overallText").textContent = "Module progress: " + average + "%";
    document.getElementById("overallBar").style.width = average + "%";
}
function selectSkill(index) {
    if (!skills[index]) return;
    selectedIndex = index;
    var skill = skills[index];
    document.getElementById("skillName").textContent = skill.name;
    document.getElementById("skillInfo").textContent =
        (skill.info || "Explore original lessons and practice assessments.") +
        " Legacy progress: " + skill.legacy_progress + "%";
    showSkills();
}
function closeLearning() {
    document.getElementById("learningWorkspace").hidden = true;
    document.getElementById("skillList").hidden = false;
}
async function practiceSkill() {
    var skill = skills[selectedIndex];
    if (!skill) {
        alert("Click a skill first.");
        return;
    }
    var button = document.getElementById("practiceSkillBtn");
    button.disabled = true;
    try {
        await openLearning(skill);
    } catch (error) {
        if (!redirectForAuth(error)) showLearningMessage(error.message);
    } finally {
        button.disabled = false;
    }
}
async function openLearning(skill) {
    var workspace = document.getElementById("learningWorkspace");
    document.getElementById("skillList").hidden = true;
    workspace.hidden = false;
    document.getElementById("learningTitle").textContent = skill.name;
    document.getElementById("learningProgress").textContent = "Module progress: loading... | Legacy progress: " + skill.legacy_progress + "%";
    document.getElementById("moduleView").hidden = true;
    document.getElementById("assessmentView").hidden = true;
    showLearningMessage("Loading modules...");
    learningModules = await apiRequest("/skills/" + skill.skill_id + "/modules");
    var progressResults = await Promise.all(learningModules.map(function (module) {
        return apiRequest("/skills/" + skill.skill_id + "/modules/" + module.module_id + "/progress");
    }));
    var progress = progressResults[0];
    document.getElementById("learningProgress").textContent =
        "Module progress: " + (progress ? progress.progress : 0) + "% (" +
        (progress ? progress.completed_modules : 0) + " of " +
        (progress ? progress.total_modules : learningModules.length) + " modules) | Legacy progress: " + skill.legacy_progress + "%";
    renderModuleList(progressResults);
}
function renderModuleList(progressResults) {
    var list = document.getElementById("moduleList");
    list.innerHTML = "";
    showLearningMessage("Lessons do not affect progress. Complete practice to finish a module.");
    if (!learningModules.length) {
        list.appendChild(makeElement("p", "empty-state", "No learning modules are available yet."));
        return;
    }
    var progressByModule = {};
    (progressResults || []).forEach(function (progress) { progressByModule[progress.module_id] = progress; });
    learningModules.forEach(function (module, index) {
        var card = makeElement("article", "module-card");
        var header = makeElement("div", "module-card-header");
        var titleGroup = makeElement("div");
        titleGroup.appendChild(makeElement("h3", "", module.title));
        titleGroup.appendChild(makeElement("p", "", module.summary));
        var status = makeElement("span", module.completed ? "status-complete" : "status-open", module.completed ? "Completed" : "Not completed");
        header.append(titleGroup, status);
        var actions = makeElement("div");
        var lessonsButton = makeElement("button", "btn", "Read lessons");
        lessonsButton.type = "button";
        lessonsButton.addEventListener("click", function () { openModule(module.module_id); });
        var practiceButton = makeElement("button", "btn grey", module.completed ? "Completed" : "Practice");
        practiceButton.type = "button";
        practiceButton.disabled = module.completed;
        practiceButton.addEventListener("click", function () { startAssessment(module); });
        actions.append(lessonsButton, practiceButton);
        var progress = progressByModule[module.module_id];
        if (progress) actions.appendChild(makeElement("p", "lesson-meta", "Module " + (index + 1) + " of " + learningModules.length + " | Skill modules: " + progress.progress + "%"));
        card.append(header, actions);
        list.appendChild(card);
    });
}
async function openModule(moduleId) {
    showLearningMessage("Loading lessons...");
    document.getElementById("assessmentView").hidden = true;
    try {
        var skill = skills[selectedIndex];
        activeModule = await apiRequest("/skills/" + skill.skill_id + "/modules/" + moduleId);
        activeLessonIndex = 0;
        renderLesson();
        showLearningMessage("Reading lessons does not award progress.");
    } catch (error) {
        if (!redirectForAuth(error)) showLearningMessage(error.message);
    }
}
function renderLesson() {
    var view = document.getElementById("moduleView");
    view.innerHTML = "";
    view.hidden = false;
    var lessons = activeModule.lessons;
    if (!lessons.length) {
        view.appendChild(makeElement("p", "empty-state", "This module has no lessons yet."));
        return;
    }
    var lesson = lessons[activeLessonIndex];
    view.appendChild(makeElement("p", "lesson-meta", "Lesson " + (activeLessonIndex + 1) + " of " + lessons.length));
    view.appendChild(makeElement("h3", "", lesson.title));
    view.appendChild(makeElement("p", "lesson-body", lesson.body));
    var nav = makeElement("div", "lesson-navigation");
    var previous = makeElement("button", "btn grey", "Previous lesson");
    previous.type = "button";
    previous.disabled = activeLessonIndex === 0;
    previous.addEventListener("click", function () {
        if (activeLessonIndex > 0) { activeLessonIndex--; renderLesson(); }
    });
    var next = makeElement("button", "btn", activeLessonIndex === lessons.length - 1 ? "Practice module" : "Next lesson");
    next.type = "button";
    next.addEventListener("click", function () {
        if (activeLessonIndex < lessons.length - 1) {
            activeLessonIndex++;
            renderLesson();
        } else {
            startAssessment(activeModule);
        }
    });
    nav.append(previous, next);
    view.appendChild(nav);
}
async function startAssessment(module) {
    activeModule = module;
    showLearningMessage("Starting assessment...");
    document.getElementById("moduleView").hidden = true;
    var assessment = document.getElementById("assessmentView");
    assessment.hidden = false;
    assessment.innerHTML = "";
    assessment.appendChild(makeElement("p", "loading", "Preparing the practice assessment..."));
    try {
        var skill = skills[selectedIndex];
        activeAttempt = await apiRequest("/skills/" + skill.skill_id + "/modules/" + module.module_id + "/assessment", { method: "POST", body: "{}" });
        showAnswerFeedback = false;
        showLearningMessage("");
        renderQuestion();
    } catch (error) {
        assessment.innerHTML = "";
        if (!redirectForAuth(error)) showLearningMessage(error.message);
    }
}
function renderQuestion() {
    var assessment = document.getElementById("assessmentView");
    assessment.innerHTML = "";
    if (!activeAttempt) return;
    if (activeAttempt.final_result) {
        renderFinalResult();
        return;
    }
    var question = activeAttempt.current_question;
    if (!question) {
        assessment.appendChild(makeElement("p", "empty-state", "No question is available for this assessment."));
        return;
    }
    var card = makeElement("div", "question-card");
    card.appendChild(makeElement("p", "difficulty", "Difficulty: " + question.difficulty));
    card.appendChild(makeElement("h3", "", "Question " + question.question_number + " of 5"));
    card.appendChild(makeElement("p", "", question.prompt));
    var form = document.createElement("form");
    form.setAttribute("aria-label", "Question " + question.question_number);
    Object.keys(question.options).forEach(function (optionKey) {
        var label = makeElement("label", "answer-option");
        var input = document.createElement("input");
        input.type = "radio";
        input.name = "answer";
        input.value = optionKey;
        input.required = true;
        var text = makeElement("span", "", optionKey.toUpperCase() + ". " + question.options[optionKey]);
        label.append(input, text);
        form.appendChild(label);
    });
    var actions = makeElement("div", "answer-actions");
    var submit = makeElement("button", "btn", "Submit answer");
    submit.type = "submit";
    actions.appendChild(submit);
    actions.appendChild(makeElement("span", "lesson-meta", "Select one answer. It cannot be changed after submission."));
    form.appendChild(actions);
    form.addEventListener("submit", submitAnswer);
    card.appendChild(form);
    assessment.appendChild(card);
}
async function submitAnswer(event) {
    event.preventDefault();
    if (answerPending || showAnswerFeedback) return;
    var form = event.currentTarget;
    var selected = form.querySelector("input[name='answer']:checked");
    if (!selected) {
        showLearningMessage("Choose an answer before submitting.");
        return;
    }
    answerPending = true;
    var submit = form.querySelector("button[type='submit']");
    submit.disabled = true;
    form.querySelectorAll("input").forEach(function (input) { input.disabled = true; });
    showLearningMessage("Checking answer...");
    try {
        var skill = skills[selectedIndex];
        var moduleId = activeModule ? activeModule.module_id : activeAttempt.module_id;
        var response = await apiRequest("/skills/" + skill.skill_id + "/modules/" + moduleId + "/assessment/" + activeAttempt.attempt_id + "/answers", {
            method: "POST",
            body: JSON.stringify({ question_id: activeAttempt.current_question.question_id, selected_option: selected.value })
        });
        showAnswerFeedback = true;
        showLearningMessage("");
        activeAttempt = {
            attempt_id: response.attempt_id,
            status: response.status,
            questions_answered: response.questions_answered,
            correct_answers: response.correct_answers,
            current_question: response.next_question,
            final_result: response.final_result
        };
        renderAnswerFeedback(form, response);
    } catch (error) {
        if (!redirectForAuth(error)) showLearningMessage(error.message);
        submit.disabled = false;
        form.querySelectorAll("input").forEach(function (input) { input.disabled = false; });
    } finally {
        answerPending = false;
    }
}
function renderAnswerFeedback(form, response) {
    form.querySelectorAll("input").forEach(function (input) { input.disabled = true; });
    var feedback = makeElement("div", "answer-feedback " + (response.is_correct ? "correct" : "incorrect"));
    feedback.setAttribute("role", "status");
    feedback.appendChild(makeElement("strong", "", response.is_correct ? "Correct." : "Not quite."));
    feedback.appendChild(makeElement("p", "", response.explanation));
    feedback.appendChild(makeElement("p", "lesson-meta", "Correct answer: " + response.correct_option.toUpperCase() + " | Score: " + response.correct_answers + " correct so far"));
    var continueButton = makeElement("button", "btn", response.final_result ? "View result" : "Continue to next question");
    continueButton.type = "button";
    continueButton.addEventListener("click", function () {
        showAnswerFeedback = false;
        if (response.final_result) renderFinalResult();
        else renderQuestion();
    });
    feedback.appendChild(continueButton);
    form.appendChild(feedback);
}
function renderFinalResult() {
    var assessment = document.getElementById("assessmentView");
    assessment.innerHTML = "";
    var result = activeAttempt.final_result;
    var card = makeElement("div", "assessment-result " + (result.passed ? "passed" : "failed"));
    card.appendChild(makeElement("h3", "", result.passed ? "Module completed" : "Practice not passed"));
    card.appendChild(makeElement("p", "", result.message));
    card.appendChild(makeElement("p", "", result.correct_answers + " of " + result.total_questions + " correct (" + result.score_percentage + "%). Passing score: " + result.passing_score + "%."));
    if (result.passed) card.appendChild(makeElement("p", "lesson-meta", "Completion is saved. Module progress has been refreshed."));
    assessment.appendChild(card);
    var actions = makeElement("div", "answer-actions");
    var retry = makeElement("button", "btn", result.passed ? "Back to modules" : "Retry assessment");
    retry.type = "button";
    retry.addEventListener("click", async function () {
        if (result.passed) await refreshAfterCompletion();
        else await startAssessment(activeModule);
    });
    actions.appendChild(retry);
    assessment.appendChild(actions);
}
async function refreshAfterCompletion() {
    showLearningMessage("Refreshing module progress...");
    try {
        var skill = skills[selectedIndex];
        await openLearning(skill);
        showLearningMessage("Module completion saved.", true);
    } catch (error) {
        if (!redirectForAuth(error)) showLearningMessage(error.message);
    }
}
function shareSkill() {
    if (selectedIndex === -1) { alert("Click a skill first."); return; }
    var skill = skills[selectedIndex];
    sessionStorage.setItem("draft", "I'm at " + skill.progress + "% in " + skill.name + "!");
    window.location.href = "../DashBoard/Dashboard.html";
}
async function logOut() {
    try {
        await apiLogout();
        window.location.href = "../../Main.html";
    } catch (error) { alert("Could not log out: " + error.message); }
}
async function loadSkills() {
    try {
        skills = await apiRequest("/skills");
        showSkills();
    } catch (error) {
        if (error.status === 401) { window.location.replace("../../Main.html"); return; }
        document.getElementById("skillList").textContent = "Could not load skills: " + error.message;
    }
}
document.getElementById("closeLearningBtn").addEventListener("click", closeLearning);
loadSkills();

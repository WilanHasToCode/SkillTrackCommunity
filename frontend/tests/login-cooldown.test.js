const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const mainScript = fs.readFileSync(
    path.join(__dirname, "..", "src", "Main.js"),
    "utf8"
);
const elements = new Map();
let intervalCount = 0;
let loginAttempts = 0;

function getElement(id) {
    if (!elements.has(id)) {
        const classes = new Set();
        const handlers = {};
        elements.set(id, {
            value: id === "userInput" ? "member" : id === "passInput" ? "wrong" : "",
            textContent: "",
            placeholder: "",
            disabled: false,
            style: {},
            className: "",
            handlers,
            classList: {
                add(name) {
                    classes.add(name);
                },
                remove(name) {
                    classes.delete(name);
                }
            },
            addEventListener(name, callback) {
                handlers[name] = callback;
            },
            focus() {}
        });
    }
    return elements.get(id);
}

const context = {
    document: { getElementById: getElement },
    window: { location: { href: "" } },
    localStorage: { setItem() {} },
    apiRequest: async function () {
        loginAttempts += 1;
        if (loginAttempts < 3) {
            throw Object.assign(new Error("Invalid username or password."), {
                status: 401
            });
        }
        throw Object.assign(
            new Error("Login temporarily unavailable. Try again in 30 seconds."),
            { status: 429, retryAfterSeconds: 30 }
        );
    },
    apiLogout: async function () {},
    setInterval() {
        intervalCount += 1;
        return intervalCount;
    },
    clearInterval() {}
};

async function main() {
    vm.runInNewContext(mainScript, context);
    const submit = getElement("submitBtn");
    const error = getElement("errorBox");

    await submit.handlers.click();
    assert.equal(error.textContent, "Invalid username or password.");
    assert.equal(intervalCount, 0, "first incorrect password must not start a timer");

    await submit.handlers.click();
    assert.equal(error.textContent, "Invalid username or password.");
    assert.equal(intervalCount, 0, "second incorrect password must not start a timer");

    await submit.handlers.click();
    assert.equal(intervalCount, 1, "backend cooldown must start the countdown");
    assert.equal(submit.disabled, true, "login must be disabled during cooldown");
    assert.match(error.textContent, /30 seconds/);
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});

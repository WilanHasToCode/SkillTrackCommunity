const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const dashboardScript = fs.readFileSync(
    path.join(root, "pages", "DashBoard", "Dashboard.js"),
    "utf8"
);
const dashboardHtml = fs.readFileSync(
    path.join(root, "pages", "DashBoard", "Dashboard.html"),
    "utf8"
);
const adminHtml = fs.readFileSync(
    path.join(root, "pages", "admin", "admin.html"),
    "utf8"
);

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

function runDashboard(authResponse) {
    const elements = new Map();
    function element(id) {
        if (!elements.has(id)) {
            const classes = new Set();
            elements.set(id, {
                hidden: false,
                className: "",
                textContent: "",
                innerHTML: "",
                style: {},
                classList: {
                    add(name) {
                        classes.add(name);
                    },
                    remove(name) {
                        classes.delete(name);
                    },
                    contains(name) {
                        return classes.has(name);
                    },
                    toggle(name, force) {
                        if (force === undefined ? !classes.has(name) : force) {
                            classes.add(name);
                        } else {
                            classes.delete(name);
                        }
                    }
                },
                addEventListener() {},
                setAttribute() {},
                focus() {}
            });
        }
        return elements.get(id);
    }

    const context = {
        document: {
            getElementById: element,
            addEventListener() {},
            createElement() {
                return element("created");
            }
        },
        window: {
            location: {
                protocol: "http:",
                origin: "http://localhost",
                replace() {}
            }
        },
        localStorage: { getItem: () => "Stale Admin Name" },
        sessionStorage: { getItem: () => null, removeItem() {} },
        setTimeout() {},
        apiRequest(endpoint) {
            return endpoint === "/auth/me"
                ? authResponse.promise
                : Promise.resolve([]);
        },
        apiLogout: async function () {}
    };
    vm.runInNewContext(dashboardScript, context);
    return { context, adminNav: element("adminNav") };
}

async function main() {
    const adminLink = dashboardHtml.match(/<a\b[^>]*id="adminNav"[^>]*>Admin<\/a>/g) || [];
    assert.equal(adminLink.length, 1, "dashboard should contain exactly one Admin link");
    assert.match(adminLink[0], /\bhidden\b/, "Admin link should start hidden");

    const regularAuth = deferred();
    const regularDashboard = runDashboard(regularAuth);
    assert.equal(regularDashboard.adminNav.hidden, true, "Admin stays hidden while auth loads");
    regularAuth.resolve({ is_admin: false });
    await regularAuth.promise;
    await new Promise(setImmediate);
    assert.equal(regularDashboard.adminNav.hidden, true, "regular users must not see Admin");

    const failedAuth = deferred();
    const failedDashboard = runDashboard(failedAuth);
    failedAuth.reject(new Error("authentication unavailable"));
    await failedAuth.promise.catch(() => {});
    await new Promise(setImmediate);
    assert.equal(failedDashboard.adminNav.hidden, true, "failed auth must keep Admin hidden");

    const adminAuth = deferred();
    const adminDashboard = runDashboard(adminAuth);
    assert.equal(adminDashboard.adminNav.hidden, true, "Admin stays hidden before verification");
    adminAuth.resolve({ is_admin: true });
    await adminAuth.promise;
    await new Promise(setImmediate);
    assert.equal(adminDashboard.adminNav.hidden, false, "confirmed admin may see Admin");

    const dashboardUrl = new URL(
        "../DashBoard/Dashboard.html",
        "http://localhost/pages/admin/admin.html"
    );
    assert.equal(dashboardUrl.pathname, "/pages/DashBoard/Dashboard.html");
    assert.match(adminHtml, /href="\.\.\/DashBoard\/Dashboard\.html"[^>]*>Back to Dashboard<\/a>/);
    assert.match(adminHtml, />Back to Users<\/button>/);
    assert.match(adminHtml, />Back to Posts<\/button>/);
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});

// Example Project login UI. API is the identity/authorization authority.
const el = id => document.getElementById(id);
let csrf = null;
async function get(path) {
    const response = await fetch(path, {credentials:"same-origin",cache:"no-store"});
    if (response.status === 401) return null;
    if (!response.ok) throw new Error("Authentication service unavailable");
    return response.json();
}
async function initialize() {
    const [person, proof] = await Promise.all([get("/api/auth/me"), get("/api/auth/csrf")]);
    csrf = proof?.requestToken ?? null;
    el("anti").value = csrf ?? "";
    if (!person) {
        el("status").textContent = "Sign in or accept an administrator-issued Project invitation.";
        el("login").hidden = false;
        el("join").hidden = false;
        return;
    }
    el("status").textContent = "Signed in to this Project.";
    el("approved").hidden = false;
    el("admin").hidden = person.isAdministrator !== true;
}
async function post(path, body) {
    if (!csrf) throw new Error("CSRF protection unavailable");
    return fetch(path, {
        method:"POST",credentials:"same-origin",cache:"no-store",
        headers:{"Content-Type":"application/json","X-PF-CSRF":csrf},
        body:JSON.stringify(body)
    });
}
el("logout").addEventListener("click", async () => {
    try {
        const response = await post("/api/auth/logout", {});
        if (response.ok) location.reload();
        else el("status").textContent = "Sign-out was not completed.";
    } catch {el("status").textContent = "Unable to sign out."; }
});
el("create-invite").addEventListener("submit", async event => {
    event.preventDefault();
    const field = event.currentTarget.elements.namedItem("recipientEmail");
    try {
        const response = await post("/api/auth/invitations",
            {recipientEmail:field.value});
        if (!response.ok) {
            el("invite-result").textContent = "Invitation not created.";
            return;
        }
        if (response.status === 204) {
            el("invite-result").textContent =
                "Invitation submitted to the Project's configured email provider.";
            field.value = "";
            return;
        }
        const ticket = await response.json();
        el("invite-result").textContent =
            "Share this one-time token privately (never in a URL): " + ticket.token;
        field.value = "";
    } catch {el("invite-result").textContent = "Invitation not created."; }
});
initialize().catch(() => {
    el("status").textContent = "Unable to verify Project authentication status.";
    el("login").hidden = true;
    el("join").hidden = true;
});

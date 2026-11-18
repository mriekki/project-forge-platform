// Project Forge Auth Kit: optional passkey UI for the generated reference app.
// This script never enables the server feature and never creates an account.
// If capability discovery fails, the existing Google-only UI remains intact.
(() => {
  const el = id => document.getElementById(id);
  let csrf = "";
  const base64url = bytes =>
    btoa(String.fromCharCode(...new Uint8Array(bytes)))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  function binary(value) {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/");
    const text = atob(padded + "=".repeat((4 - padded.length % 4) % 4));
    return Uint8Array.from(text, c => c.charCodeAt(0));
  }
  function supportsWebAuthn() {
    return !!(window.PublicKeyCredential && navigator.credentials &&
      navigator.credentials.create && navigator.credentials.get);
  }
  async function jsonPost(path, payload) {
    if (!csrf) throw new Error("Project security token is missing.");
    const response = await fetch(path, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-PF-CSRF": csrf },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      if (response.status === 403) throw new Error("Sign in with Google again before managing passkeys.");
      if (response.status === 401) throw new Error("Your passkey could not be verified. You can use Google.");
      if (response.status === 429) throw new Error("Too many attempts. Try later or use Google.");
      throw new Error("Passkey request could not be completed. You can continue with Google.");
    }
    return response;
  }
  async function capability() {
    if (!supportsWebAuthn()) return false;
    try {
      const response = await fetch("/api/auth/passkeys/capabilities", {
        credentials: "same-origin", cache: "no-store"
      });
      if (!response.ok || !response.headers.get("content-type")?.includes("application/json"))
        return false; // The unqualified sample may return its HTML SPA fallback.
      const body = await response.json();
      return body.enabled === true &&
        body.relyingPartyId === location.hostname &&
        body.userVerification === "required";
    } catch { return false; }
  }
  function publicKeyResponse(credential) {
    if (typeof credential.toJSON === "function") return credential.toJSON();
    const response = credential.response;
    const base = {
      id: credential.id,
      rawId: base64url(credential.rawId),
      type: credential.type,
      clientExtensionResults: credential.getClientExtensionResults()
    };
    if (response.attestationObject) {
      return { ...base, response: {
        attestationObject: base64url(response.attestationObject),
        clientDataJSON: base64url(response.clientDataJSON),
        transports: typeof response.getTransports === "function"
          ? response.getTransports() : []
      }};
    }
    return { ...base, response: {
      authenticatorData: base64url(response.authenticatorData),
      clientDataJSON: base64url(response.clientDataJSON),
      signature: base64url(response.signature),
      userHandle: response.userHandle ? base64url(response.userHandle) : null
    }};
  }
  function message(cause) {
    if (cause?.name === "NotAllowedError") return "Passkey prompt canceled or timed out.";
    if (cause?.name === "NotSupportedError" || cause?.name === "NotReadableError")
      return "Passkeys are unavailable on this device. Continue with Google.";
    return cause instanceof Error ? cause.message : "Passkey authentication unavailable.";
  }
  async function listOwn() {
    const response = await fetch("/api/auth/passkeys", {
      credentials: "same-origin", cache: "no-store"
    });
    if (!response.ok) throw new Error("Unable to load passkey settings.");
    const keys = await response.json();
    if (!Array.isArray(keys)) throw new Error("Invalid Project passkey list.");
    const list = el("passkey-list");
    list.replaceChildren();
    if (!keys.length) {
      const item = document.createElement("li");
      item.textContent = "No passkeys enrolled yet.";
      list.append(item);
    }
    for (const key of keys) {
      if (typeof key.id !== "string" || !/^[0-9a-f]{32,2048}$/i.test(key.id)) continue;
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = (typeof key.label === "string" ? key.label : "Passkey") + " ";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.setAttribute("aria-label", "Remove " + label.textContent.trim());
      remove.addEventListener("click", async () => {
        if (!confirm("Remove this passkey and invalidate other account sessions?")) return;
        remove.disabled = true;
        try {
          await jsonPost("/api/auth/passkeys/revoke", { id: key.id });
          el("passkey-result").textContent = "Passkey revoked. Google login remains available.";
          await listOwn();
        } catch (error) {
          el("passkey-result").textContent = message(error);
          remove.disabled = false;
        }
      });
      item.append(label, remove);
      list.append(item);
    }
  }
  async function login() {
    const button = el("signin-passkey");
    button.disabled = true;
    try {
      const response = await jsonPost("/api/auth/passkeys/authentication/options", {});
      const o = await response.json();
      if (o.rpId !== location.hostname || o.userVerification !== "required")
        throw new Error("Unexpected Project passkey request.");
      const credential = await navigator.credentials.get({ publicKey: {
        ...o,
        challenge: binary(o.challenge),
        allowCredentials: (o.allowCredentials || []).map(c => ({
          ...c, id: binary(c.id)
        }))
      }});
      if (!(credential instanceof PublicKeyCredential))
        throw new Error("No passkey provided by your device.");
      await jsonPost("/api/auth/passkeys/authentication/complete",
        publicKeyResponse(credential));
      location.reload();
    } catch (error) {
      el("status").textContent = message(error);
      button.disabled = false;
    }
  }
  async function enroll() {
    const button = el("add-passkey");
    button.disabled = true;
    try {
      const response = await jsonPost("/api/auth/passkeys/registration/options", {});
      const o = await response.json();
      if (o.rp?.id !== location.hostname ||
          o.authenticatorSelection?.userVerification !== "required")
        throw new Error("Unexpected Project passkey registration request.");
      const credential = await navigator.credentials.create({ publicKey: {
        ...o,
        user: { ...o.user, id: binary(o.user.id) },
        challenge: binary(o.challenge),
        excludeCredentials: (o.excludeCredentials || []).map(c => ({
          ...c, id: binary(c.id)
        }))
      }});
      if (!(credential instanceof PublicKeyCredential))
        throw new Error("No passkey created by your device.");
      await jsonPost("/api/auth/passkeys/registration/complete",
        publicKeyResponse(credential));
      await listOwn();
      el("passkey-result").textContent = "Passkey registered for future sign-ins.";
    } catch (error) {
      el("passkey-result").textContent = message(error);
    } finally { button.disabled = false; }
  }
  async function initialize() {
    if (!await capability()) return;
    const [account, proof] = await Promise.all([
      fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" }),
      fetch("/api/auth/csrf", { credentials: "same-origin", cache: "no-store" })
    ]);
    if ((!account.ok && account.status !== 401) || !proof.ok) return;
    const token = await proof.json();
    if (typeof token.requestToken !== "string" || !token.requestToken) return;
    csrf = token.requestToken;
    if (account.status === 401) {
      el("passkey-login").hidden = false;
      el("signin-passkey").addEventListener("click", login);
      return;
    }
    el("passkey-management").hidden = false;
    el("add-passkey").addEventListener("click", enroll);
    await listOwn();
  }
  initialize().catch(() => {
    // Fail closed: the Google-only reference UI stays visible and functional.
    el("passkey-login").hidden = true;
    el("passkey-management").hidden = true;
  });
})();

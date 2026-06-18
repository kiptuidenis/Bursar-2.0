// Bursar 2.0 Client App Logic (Multi-Tenant Auth Edition)

// Global State
let currentSettings = {};
let countdownInterval = null;
let pollInterval = null;
let currentAuthAction = "login"; // "login" or "signup"
let isAuthenticated = false;

document.addEventListener("DOMContentLoaded", () => {
    // Check initial authentication status
    checkAuth();

    // Setup Event Handlers
    setupEventHandlers();

    // Start countdown timer immediately (ticks client-side)
    startCountdownTimer();
});

// Check if user session cookie is valid
async function checkAuth() {
    try {
        const res = await fetch("/api/auth/me");
        if (res.status === 200) {
            const user = await res.json();
            isAuthenticated = true;
            
            // Show logged-in UI elements
            document.getElementById("auth-overlay").classList.remove("active");
            document.getElementById("user-phone-number").innerText = user.phone_number;
            document.getElementById("user-badge").style.display = "flex";
            document.getElementById("logout-btn").style.display = "inline-flex";

            // Load user data
            pollDashboardData();
            
            // Start dashboard polling if not already running
            if (!pollInterval) {
                pollInterval = setInterval(pollDashboardData, 5000);
            }
        } else {
            showAuthScreen();
        }
    } catch (err) {
        console.error("Auth check failed:", err);
        showAuthScreen();
    }
}

// Forces auth overlay display
function showAuthScreen() {
    isAuthenticated = false;
    document.getElementById("auth-overlay").classList.add("active");
    document.getElementById("user-badge").style.display = "none";
    document.getElementById("logout-btn").style.display = "none";
    
    // Stop dashboard polling
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

// Setup DOM elements and event binders
function setupEventHandlers() {
    const depositModal = document.getElementById("deposit-modal");
    const settingsDrawer = document.getElementById("settings-drawer");

    // Open/Close Deposit
    document.getElementById("open-deposit-btn").addEventListener("click", () => {
        document.getElementById("deposit-amount").value = "";
        depositModal.classList.add("active");
    });
    document.getElementById("close-deposit-btn").addEventListener("click", () => {
        depositModal.classList.remove("active");
    });
    depositModal.addEventListener("click", (e) => {
        if (e.target === depositModal) depositModal.classList.remove("active");
    });

    // Open/Close Settings
    document.getElementById("toggle-settings-btn").addEventListener("click", () => {
        settingsDrawer.classList.add("active");
    });
    document.getElementById("close-settings-btn").addEventListener("click", () => {
        settingsDrawer.classList.remove("active");
    });
    settingsDrawer.addEventListener("click", (e) => {
        if (e.target === settingsDrawer) settingsDrawer.classList.remove("active");
    });

    // Toggle credentials panel based on mode radio selection
    const modeRadios = document.querySelectorAll('input[name="mode"]');
    modeRadios.forEach(radio => {
        radio.addEventListener("change", (e) => {
            toggleCredentialsFields(e.target.value);
        });
    });

    // Deposit Submit Form
    document.getElementById("deposit-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const amount = parseFloat(document.getElementById("deposit-amount").value);
        if (isNaN(amount) || amount <= 0) return;

        try {
            const res = await fetch("/api/deposit", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ amount })
            });
            if (res.status === 401) return showAuthScreen();
            if (!res.ok) throw new Error("Deposit failed.");
            
            depositModal.classList.remove("active");
            pollDashboardData();
            addLocalLog("INFO", `Client triggered deposit of KES ${amount.toFixed(2)}.`);
        } catch (err) {
            console.error(err);
            alert("Failed to deposit funds. Please check server logs.");
        }
    });

    // Settings Submit Form
    document.getElementById("settings-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const mode = document.querySelector('input[name="mode"]:checked').value;
        const daily_budget = parseFloat(document.getElementById("settings-budget").value);
        const payout_time = document.getElementById("settings-time").value;
        const phone_number = document.getElementById("settings-phone").value;
        
        const payload = {
            mode,
            daily_budget,
            payout_time,
            phone_number,
            mpesa_consumer_key: document.getElementById("settings-key").value,
            mpesa_consumer_secret: document.getElementById("settings-secret").value,
            mpesa_shortcode: document.getElementById("settings-shortcode").value,
            mpesa_initiator_name: document.getElementById("settings-initiator").value,
            mpesa_initiator_password: document.getElementById("settings-password").value,
            mpesa_b2c_result_url: document.getElementById("settings-result-url").value,
            mpesa_b2c_timeout_url: document.getElementById("settings-timeout-url").value
        };

        try {
            const res = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.status === 401) return showAuthScreen();
            if (!res.ok) throw new Error("Saving settings failed.");
            
            settingsDrawer.classList.remove("active");
            pollDashboardData();
            addLocalLog("INFO", "Client saved updated configuration settings.");
        } catch (err) {
            console.error(err);
            alert("Failed to save settings. Check inputs.");
        }
    });

    // Clear logs view
    document.getElementById("clear-logs-btn").addEventListener("click", () => {
        document.getElementById("logs-console").innerHTML = "";
    });

    // Auth Overlay Form Events
    const tabLogin = document.getElementById("tab-login");
    const tabSignup = document.getElementById("tab-signup");
    const authForm = document.getElementById("auth-form");
    const errorMsg = document.getElementById("auth-error-msg");
    const authSubmitBtn = document.getElementById("auth-submit-btn");
    const authSubtitle = document.getElementById("auth-subtitle");
    const passwordLabel = document.getElementById("password-label");
    const authPassword = document.getElementById("auth-password");

    tabLogin.addEventListener("click", () => {
        currentAuthAction = "login";
        tabLogin.classList.add("active");
        tabSignup.classList.remove("active");
        authSubmitBtn.innerText = "Log In";
        authSubtitle.innerText = "Log in to manage your daily allowances";
        passwordLabel.innerText = "Password PIN";
        authPassword.placeholder = "Enter password (min 4 chars)";
        errorMsg.style.display = "none";
    });

    tabSignup.addEventListener("click", () => {
        currentAuthAction = "signup";
        tabSignup.classList.add("active");
        tabLogin.classList.remove("active");
        authSubmitBtn.innerText = "Register";
        authSubtitle.innerText = "Create an account with your Safaricom number";
        passwordLabel.innerText = "Create Password PIN";
        authPassword.placeholder = "Choose password (min 4 chars)";
        errorMsg.style.display = "none";
    });

    authForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        errorMsg.style.display = "none";

        const phone_number = document.getElementById("auth-phone").value.trim();
        const password = authPassword.value;

        const url = currentAuthAction === "login" ? "/api/auth/login" : "/api/auth/signup";

        try {
            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ phone_number, password })
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || "Authentication request failed.");
            }

            if (currentAuthAction === "signup") {
                // If register succeeded, perform auto-login for top-tier UX
                currentAuthAction = "login";
                tabLogin.click();
                document.getElementById("auth-password").value = password;
                authForm.dispatchEvent(new Event("submit"));
            } else {
                // Login succeeded
                document.getElementById("auth-phone").value = "";
                authPassword.value = "";
                checkAuth();
            }
        } catch (err) {
            errorMsg.innerText = err.message;
            errorMsg.style.display = "block";
        }
    });

    // Logout Click
    document.getElementById("logout-btn").addEventListener("click", async () => {
        try {
            await fetch("/api/auth/logout", { method: "POST" });
            showAuthScreen();
        } catch (err) {
            console.error("Logout failed:", err);
            showAuthScreen();
        }
    });

    // Inline daily budget editing events
    const editBudgetBtn = document.getElementById("edit-budget-btn");
    const saveBudgetBtn = document.getElementById("save-budget-btn");
    const cancelBudgetBtn = document.getElementById("cancel-budget-btn");
    const inlineBudgetControls = document.getElementById("inline-budget-controls");
    const dailyBudgetVal = document.getElementById("daily-budget-value");
    const inlineBudgetInput = document.getElementById("inline-budget-input");

    editBudgetBtn.addEventListener("click", () => {
        editBudgetBtn.style.display = "none";
        inlineBudgetControls.style.display = "flex";
        
        inlineBudgetInput.value = currentSettings.daily_budget || 0;
        dailyBudgetVal.style.display = "none";
        inlineBudgetInput.style.display = "inline-block";
        inlineBudgetInput.focus();
    });

    const cancelInlineEdit = () => {
        editBudgetBtn.style.display = "inline-flex";
        inlineBudgetControls.style.display = "none";
        dailyBudgetVal.style.display = "inline";
        inlineBudgetInput.style.display = "none";
    };
    
    cancelBudgetBtn.addEventListener("click", cancelInlineEdit);

    const saveInlineEdit = async () => {
        const newBudget = parseFloat(inlineBudgetInput.value);
        if (isNaN(newBudget) || newBudget < 0) {
            alert("Please enter a valid daily budget amount.");
            return;
        }

        try {
            const res = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ daily_budget: newBudget })
            });
            if (res.status === 401) return showAuthScreen();
            if (!res.ok) throw new Error("Saving inline budget failed.");
            
            cancelInlineEdit();
            pollDashboardData();
            addLocalLog("INFO", `Updated daily budget to KES ${newBudget.toFixed(2)} directly from dashboard.`);
        } catch (err) {
            console.error(err);
            alert("Failed to save daily budget.");
        }
    };

    saveBudgetBtn.addEventListener("click", saveInlineEdit);

    inlineBudgetInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            saveInlineEdit();
        } else if (e.key === "Escape") {
            cancelInlineEdit();
        }
    });
}

// Shows/Hides Daraja fields in settings form
function toggleCredentialsFields(mode) {
    const credGroup = document.getElementById("mpesa-credentials-fields");
    if (mode === "simulation") {
        credGroup.classList.remove("active");
    } else {
        credGroup.classList.add("active");
    }
}

// Fetch general configuration & state
async function fetchSettings() {
    try {
        const res = await fetch("/api/settings");
        if (res.status === 401) return showAuthScreen();
        const data = await res.json();
        currentSettings = data;

        // Update indicators
        updateDashboardMetrics(data);
    } catch (err) {
        console.error("Error fetching settings:", err);
    }
}

// Update UI dashboard labels based on backend model state
function updateDashboardMetrics(settings) {
    const badge = document.getElementById("mode-badge");
    const text = document.getElementById("current-mode-text");
    
    badge.className = "status-badge";
    if (settings.mode === "simulation") {
        text.innerText = "Simulation Mode";
    } else if (settings.mode === "sandbox") {
        badge.classList.add("sandbox-mode");
        text.innerText = "Sandbox Mode";
    } else if (settings.mode === "live") {
        badge.classList.add("live-mode");
        text.innerText = "Live M-Pesa";
    }

    document.getElementById("wallet-balance").innerText = parseFloat(settings.balance || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    
    const inlineInput = document.getElementById("inline-budget-input");
    if (inlineInput && inlineInput.style.display !== "inline-block") {
        document.getElementById("daily-budget-value").innerText = parseFloat(settings.daily_budget || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    
    document.getElementById("payout-time-info").innerText = `Payout at ${settings.payout_time || "08:00"} to ${settings.phone_number || "none"}`;

    document.getElementById(`settings-budget`).value = settings.daily_budget || 0;
    document.getElementById(`settings-time`).value = settings.payout_time || "08:00";
    document.getElementById(`settings-phone`).value = settings.phone_number || "";
    
    document.getElementById(`settings-key`).value = settings.mpesa_consumer_key || "";
    document.getElementById(`settings-secret`).value = settings.mpesa_consumer_secret || "";
    document.getElementById(`settings-shortcode`).value = settings.mpesa_shortcode || "";
    document.getElementById(`settings-initiator`).value = settings.mpesa_initiator_name || "";
    document.getElementById(`settings-password`).value = settings.mpesa_initiator_password || "";
    document.getElementById(`settings-result-url`).value = settings.mpesa_b2c_result_url || "";
    document.getElementById(`settings-timeout-url`).value = settings.mpesa_b2c_timeout_url || "";

    const radio = document.querySelector(`input[name="mode"][value="${settings.mode || "simulation"}"]`);
    if (radio) radio.checked = true;

    toggleCredentialsFields(settings.mode || "simulation");
}

// Fetch historical payout transaction rows
async function fetchPayouts() {
    try {
        const res = await fetch("/api/payouts");
        if (res.status === 401) return showAuthScreen();
        const data = await res.json();
        
        document.getElementById("payout-count-badge").innerText = `${data.length} total`;

        const body = document.getElementById("payout-history-body");
        if (data.length === 0) {
            body.innerHTML = `<tr><td colspan="5" class="empty-state">No payouts recorded yet.</td></tr>`;
            return;
        }

        body.innerHTML = data.map(payout => {
            let statusClass = "badge-pending";
            let statusText = payout.status;
            let tooltip = "";

            if (payout.status === "SUCCESS") {
                statusClass = "badge-success";
            } else if (payout.status === "FAILED") {
                statusClass = "badge-failed";
                tooltip = `title="${payout.error_message || 'Transaction rejected'}"`;
            }

            return `
                <tr>
                    <td><strong>${payout.payout_date}</strong></td>
                    <td>KES ${parseFloat(payout.amount).toFixed(2)}</td>
                    <td>${payout.phone_number}</td>
                    <td class="text-mono">${payout.transaction_id || payout.conversation_id || '—'}</td>
                    <td><span class="badge ${statusClass}" ${tooltip}>${statusText}</span></td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        console.error("Error fetching payouts:", err);
    }
}

// Fetch system logger events
async function fetchLogs() {
    try {
        const res = await fetch("/api/logs");
        if (res.status === 401) return showAuthScreen();
        const data = await res.json();

        const consoleBox = document.getElementById("logs-console");
        if (data.length === 0) {
            consoleBox.innerHTML = `<div class="log-line log-info">[System] Ready...</div>`;
            return;
        }

        consoleBox.innerHTML = data.map(log => {
            const timeStr = new Date(log.created_at + "Z").toLocaleTimeString();
            let levelClass = "log-info";
            if (log.level === "WARNING") levelClass = "log-warning";
            if (log.level === "ERROR") levelClass = "log-error";

            return `
                <div class="log-line ${levelClass}">
                    <span class="log-timestamp">[${timeStr}]</span> ${log.message}
                </div>
            `;
        }).join("");
    } catch (err) {
        console.error("Error fetching logs:", err);
    }
}

// Adds log locally on immediate action triggers without waiting for poll
function addLocalLog(level, message) {
    const timeStr = new Date().toLocaleTimeString();
    let levelClass = "log-info";
    if (level === "WARNING") levelClass = "log-warning";
    if (level === "ERROR") levelClass = "log-error";

    const consoleBox = document.getElementById("logs-console");
    const logLine = document.createElement("div");
    logLine.className = `log-line ${levelClass}`;
    logLine.innerHTML = `<span class="log-timestamp">[${timeStr}]</span> ${message}`;
    consoleBox.insertBefore(logLine, consoleBox.firstChild);
}

// Tick the distribution countdown live
function startCountdownTimer() {
    if (countdownInterval) clearInterval(countdownInterval);

    const timerLabel = document.getElementById("countdown-timer");

    countdownInterval = setInterval(() => {
        if (!currentSettings.payout_time || !isAuthenticated) {
            timerLabel.innerText = "--h --m --s";
            return;
        }

        const now = new Date();
        const [hour, minute] = currentSettings.payout_time.split(":").map(Number);
        
        let target = new Date();
        target.setHours(hour, minute, 0, 0);

        if (now >= target) {
            target.setDate(target.getDate() + 1);
        }

        const diffMs = target - now;
        
        const hours = Math.floor(diffMs / (1000 * 60 * 60));
        const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((diffMs % (1000 * 60)) / 1000);

        const pad = (num) => String(num).padStart(2, '0');

        timerLabel.innerText = `${pad(hours)}h ${pad(minutes)}m ${pad(seconds)}s`;
    }, 1000);
}

// Background poll function
function pollDashboardData() {
    if (!isAuthenticated) return;
    fetchSettings();
    fetchPayouts();
    fetchLogs();
}

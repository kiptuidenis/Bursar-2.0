// CSRF Protection Interceptor
function getCsrfToken() {
    const match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : "";
}

const originalFetch = window.fetch;
window.fetch = function (url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) {
        options.headers = options.headers || {};
        const csrfToken = getCsrfToken();
        if (csrfToken) {
            if (options.headers instanceof Headers) {
                options.headers.set("X-CSRF-Token", csrfToken);
            } else if (Array.isArray(options.headers)) {
                options.headers.push(["X-CSRF-Token", csrfToken]);
            } else {
                options.headers["X-CSRF-Token"] = csrfToken;
            }
        }
    }
    return originalFetch.call(this, url, options);
};

// Global State
let currentSettings = {};
let currentPayouts = [];
let budgetItems = [];
let countdownInterval = null;
let pollInterval = null;
let currentAuthAction = "login"; // "login" or "signup"
let isAuthenticated = false;
let balanceChartInstance = null;
let lastInteractionTime = Date.now();
let lastPingTime = Date.now();
let inactivityInterval = null;
let activityListenersAttached = false;

document.addEventListener("DOMContentLoaded", () => {
    // Check initial authentication status
    checkAuth();

    // Setup Event Handlers
    setupEventHandlers();
    setupWithdrawalHandlers();

    // Start countdown timer immediately (ticks client-side)
    startCountdownTimer();

    // Initialize lucide icons for static elements
    if (window.lucide) {
        window.lucide.createIcons();
    }

    // Select correct auth tab based on hash routing
    if (window.location.hash === "#signup") {
        const tabSignup = document.getElementById("tab-signup");
        if (tabSignup) tabSignup.click();
    } else if (window.location.hash === "#login") {
        const tabLogin = document.getElementById("tab-login");
        if (tabLogin) tabLogin.click();
    }

    // Listen for hash changes (browser back/forward navigation)
    window.addEventListener("hashchange", () => {
        const validTabs = ["dashboard", "transactions", "profile", "deposit", "budget", "settings", "notifications"];
        const currentTab = window.location.hash.replace("#", "") || "dashboard";
        if (validTabs.includes(currentTab)) {
            const activeView = document.querySelector(".tab-view.active");
            if (!activeView || activeView.id !== `view-${currentTab}`) {
                switchTab(currentTab);
            }
        }
    });
});

// Check if user session cookie is valid
async function checkAuth() {
    try {
        const res = await fetch("/api/auth/me");
        if (res.status === 200) {
            const user = await res.json();
            isAuthenticated = true;
            
            // Show logged-in UI elements
            const authOverlay = document.getElementById("auth-overlay");
            if (authOverlay) authOverlay.classList.remove("active");
            
            const userPhone = document.getElementById("user-phone-number");
            if (userPhone) userPhone.innerText = user.phone_number;
            
            const userBadge = document.getElementById("user-badge");
            if (userBadge) userBadge.style.display = "flex";
            
            const logoutBtn = document.getElementById("logout-btn");
            if (logoutBtn) logoutBtn.style.display = "inline-flex";

            const cardPhone = document.getElementById("cardholder-phone");
            if (cardPhone) cardPhone.innerText = user.phone_number;
            
            const sidebarBadge = document.getElementById("sidebar-user-badge");
            if (sidebarBadge) sidebarBadge.style.display = "flex";
            const sidebarPhone = document.getElementById("sidebar-user-phone-number");
            if (sidebarPhone) sidebarPhone.innerText = user.phone_number;

            // Initialize/refresh icons when UI state changes
            if (window.lucide) {
                window.lucide.createIcons();
            }

            // Load user data
            pollDashboardData();
            fetchProfile();
            initActivityTracking();

            // Hash routing on load
            const validTabs = ["dashboard", "transactions", "profile", "deposit", "budget", "settings"];
            const initialTab = window.location.hash.replace("#", "");
            if (validTabs.includes(initialTab)) {
                switchTab(initialTab);
            }
            
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

// Forces auth overlay display and redirects to landing page
function showAuthScreen() {
    isAuthenticated = false;
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
    if (inactivityInterval) {
        clearInterval(inactivityInterval);
        inactivityInterval = null;
    }
    const expiryModal = document.getElementById("session-expiry-modal");
    if (expiryModal) {
        expiryModal.classList.remove("active");
    }
    window.location.href = "/#login";
}

// Module-level logout function
async function handleLogout() {
    try {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
        if (inactivityInterval) {
            clearInterval(inactivityInterval);
            inactivityInterval = null;
        }
        const expiryModal = document.getElementById("session-expiry-modal");
        if (expiryModal) {
            expiryModal.classList.remove("active");
        }
        await fetch("/api/auth/logout", { method: "POST" });
        window.location.href = "/";
    } catch (err) {
        console.error("Logout failed:", err);
        window.location.href = "/";
    }
}

// Initialize inactivity and keep-alive timers
function initActivityTracking() {
    lastInteractionTime = Date.now();
    lastPingTime = Date.now();
    
    // Start periodic inactivity check interval if not already running
    if (!inactivityInterval) {
        inactivityInterval = setInterval(checkInactivity, 1000);
    }
    
    // Attach event listeners to window (once only)
    if (!activityListenersAttached) {
        const events = ["mousemove", "keydown", "click", "scroll", "touchstart"];
        events.forEach(evt => {
            window.addEventListener(evt, handleUserActivity);
        });
        
        // Modal button listeners
        const extendBtn = document.getElementById("session-extend-btn");
        if (extendBtn) {
            extendBtn.addEventListener("click", () => {
                // Explicitly reset the idle timer and extend the backend session
                lastInteractionTime = Date.now();
                const expiryModal = document.getElementById("session-expiry-modal");
                if (expiryModal) expiryModal.classList.remove("active");
                pingSession();
            });
        }
        
        const logoutBtn = document.getElementById("session-logout-btn");
        if (logoutBtn) {
            logoutBtn.addEventListener("click", () => {
                const expiryModal = document.getElementById("session-expiry-modal");
                if (expiryModal) expiryModal.classList.remove("active");
                handleLogout();
            });
        }
        
        activityListenersAttached = true;
    }
}

// Resets idle timer and triggers keep-alive ping if threshold is reached.
// Ignores all input while the session warning modal is visible — only the
// modal's own buttons are allowed to resolve that state.
function handleUserActivity() {
    const expiryModal = document.getElementById("session-expiry-modal");
    if (expiryModal && expiryModal.classList.contains("active")) {
        // Modal is showing — block passive activity from affecting the timer
        return;
    }
    
    lastInteractionTime = Date.now();
    
    if (Date.now() - lastPingTime > 60000) { // ping every 1 minute of real activity
        pingSession();
    }
}

// Calls ping API to extend session on the backend
async function pingSession() {
    try {
        lastPingTime = Date.now();
        await fetch("/api/auth/ping", { method: "POST" });
    } catch (err) {
        console.error("Keep-alive ping failed:", err);
    }
}

// Periodic check for inactivity timeout
function checkInactivity() {
    if (!isAuthenticated) return;
    
    const elapsed = Date.now() - lastInteractionTime;
    const timeout = 300000; // 5 minutes
    const warning = 270000; // 4 minutes 30 seconds
    
    if (elapsed >= timeout) {
        // Idle timeout reached
        if (inactivityInterval) {
            clearInterval(inactivityInterval);
            inactivityInterval = null;
        }
        const expiryModal = document.getElementById("session-expiry-modal");
        if (expiryModal) expiryModal.classList.remove("active");
        handleLogout();
    } else if (elapsed >= warning) {
        // Show session expiry warning modal and start countdown
        const expiryModal = document.getElementById("session-expiry-modal");
        if (expiryModal && !expiryModal.classList.contains("active")) {
            expiryModal.classList.add("active");
        }
        
        const timerEl = document.getElementById("session-expiry-timer");
        if (timerEl) {
            const remaining = Math.max(0, Math.ceil((timeout - elapsed) / 1000));
            timerEl.innerText = remaining;
        }
    }
    // Note: no else branch — once the modal is open, only the buttons can dismiss it
}

// Switch View — module-level so it's accessible from checkAuth(), event handlers, etc.
function switchTab(tabId) {
    // Update hash in URL
    if (window.location.hash.replace("#", "") !== tabId) {
        window.location.hash = tabId;
    }

    // Handle DOM re-parenting for Deposit
    const depositModal = document.getElementById("deposit-modal");
    const depositContent = document.getElementById("deposit-modal-content");
    const viewDeposit = document.getElementById("view-deposit");

    if (tabId === "deposit") {
        if (depositContent && viewDeposit) {
            viewDeposit.appendChild(depositContent);
        }
        if (depositModal) {
            depositModal.classList.remove("active");
        }
        // Reset input
        const depositAmt = document.getElementById("deposit-amount");
        if (depositAmt) depositAmt.value = "";
    } else {
        // Return to modal overlay if not on deposit tab
        if (depositContent && depositModal && depositContent.parentNode !== depositModal) {
            depositModal.appendChild(depositContent);
        }
    }

    // Handle DOM re-parenting for Budget Designer
    const budgetModal = document.getElementById("budget-designer-modal");
    const budgetContent = document.getElementById("budget-designer-modal-content");
    const viewBudget = document.getElementById("view-budget");

    if (tabId === "budget") {
        if (budgetContent && viewBudget) {
            viewBudget.appendChild(budgetContent);
        }
        if (budgetModal) {
            budgetModal.classList.remove("active");
        }
        // Reset input and states
        const newCatName = document.getElementById("new-category-name");
        const newCatAmount = document.getElementById("new-category-amount");
        if (newCatName) newCatName.value = "";
        if (newCatAmount) newCatAmount.value = "";

        const startDateInput = document.getElementById("lock-start-date");
        const endDateInput = document.getElementById("lock-end-date");
        if (startDateInput) startDateInput.value = currentSettings.start_date || "";
        if (endDateInput) endDateInput.value = currentSettings.end_date || "";
        
        const collBody = document.getElementById("schedule-collapse-body");
        const collChevron = document.getElementById("schedule-chevron");
        if (collBody) collBody.style.display = "none";
        if (collChevron) collChevron.classList.remove("expanded");

        renderBudgetBreakdown();

        if (newCatName) {
            const isLocked = currentSettings && currentSettings.is_budget_locked;
            if (!isLocked) {
                setTimeout(() => {
                    newCatName.focus();
                }, 50);
            }
        }
    } else {
        // Return to modal overlay if not on budget tab
        if (budgetContent && budgetModal && budgetContent.parentNode !== budgetModal) {
            budgetModal.appendChild(budgetContent);
        }
    }

    // Handle DOM re-parenting for Settings
    const settingsDrawer = document.getElementById("settings-drawer");
    const settingsContent = document.getElementById("settings-drawer-content");
    const viewSettings = document.getElementById("view-settings");

    if (tabId === "settings") {
        if (settingsContent && viewSettings) {
            viewSettings.appendChild(settingsContent);
        }
        if (settingsDrawer) {
            settingsDrawer.classList.remove("active");
        }
        if (currentSettings) {
            const phoneEl = document.getElementById("settings-phone");
            const timeEl = document.getElementById("settings-time");
            const budgetEl = document.getElementById("settings-budget");
            if (phoneEl) phoneEl.value = currentSettings.phone_number || "";
            if (timeEl) timeEl.value = currentSettings.payout_time || "08:00";
            if (budgetEl) budgetEl.value = currentSettings.daily_budget || 0;
        }
    } else {
        // Return to drawer overlay if not on settings tab
        if (settingsContent && settingsDrawer && settingsContent.parentNode !== settingsDrawer) {
            settingsDrawer.appendChild(settingsContent);
        }
    }

    // Handle DOM re-parenting for Notifications
    const notificationsDrawer = document.getElementById("notifications-drawer");
    const notificationsContent = document.getElementById("notifications-drawer-content");
    const viewNotifications = document.getElementById("view-notifications");

    if (tabId === "notifications") {
        if (notificationsContent && viewNotifications) {
            viewNotifications.appendChild(notificationsContent);
        }
        if (notificationsDrawer) {
            notificationsDrawer.classList.remove("active");
        }
        fetchNotifications();
    } else {
        // Return to drawer overlay if not on notifications tab
        if (notificationsContent && notificationsDrawer && notificationsContent.parentNode !== notificationsDrawer) {
            notificationsDrawer.appendChild(notificationsContent);
        }
    }

    // Toggle view containers
    const allViews = ["dashboard", "transactions", "profile", "deposit", "budget", "settings", "notifications"];
    allViews.forEach(v => {
        const view = document.getElementById(`view-${v}`);
        if (view) {
            if (v === tabId) {
                view.classList.remove("hidden");
                view.classList.add("active");
            } else {
                view.classList.add("hidden");
                view.classList.remove("active");
            }
        }
    });

    if (tabId === "profile") {
        fetchProfile();
        fetchSessions();
    }
    
    // Update active class on sidebar links
    document.querySelectorAll(".sidebar-link").forEach(btn => {
        if (btn.getAttribute("data-tab") === tabId) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
    
    // Hide mobile sidebar
    const sidebar = document.getElementById("sidebar-nav");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (sidebar) sidebar.classList.remove("active");
    if (backdrop) backdrop.classList.remove("active");
}

// Budget wizard step navigation — module-level so openBudgetDesignerModal can call it
function goToBudgetWizardStep(stepNumber) {
    const track = document.getElementById("budget-wizard-track");
    const stepTitle = document.getElementById("budget-wizard-step-title");
    const dots = document.querySelectorAll("#budget-wizard-dots .wizard-dot");

    if (track) {
        // Track width is 300% (3 tiles), so each tile is exactly (100 / 3)% = 33.333333%
        const offset = (stepNumber - 1) * (100 / 3);
        track.style.transform = `translateX(-${offset}%)`;
    }

    if (stepTitle) {
        if (stepNumber === 1) stepTitle.textContent = "Step 1 of 3: Allocations";
        else if (stepNumber === 2) stepTitle.textContent = "Step 2 of 3: Payout Schedule";
        else if (stepNumber === 3) stepTitle.textContent = "Step 3 of 3: Payout Destination";
    }

    dots.forEach(dot => {
        const dStep = parseInt(dot.getAttribute("data-step"), 10);
        if (dStep === stepNumber) {
            dot.classList.add("active");
        } else {
            dot.classList.remove("active");
        }
    });
}

// Setup DOM elements and event binders
function setupEventHandlers() {
    const depositModal = document.getElementById("deposit-modal");
    const settingsDrawer = document.getElementById("settings-drawer");

    // Sidebar Tab switching & mobile menu handling
    const sidebar = document.getElementById("sidebar-nav");
    const backdrop = document.getElementById("sidebar-backdrop");
    const toggleBtn = document.getElementById("sidebar-toggle-btn");
    
    // Toggle Mobile Sidebar
    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            if (sidebar) sidebar.classList.add("active");
            if (backdrop) backdrop.classList.add("active");
        });
    }
    if (backdrop) {
        backdrop.addEventListener("click", () => {
            if (sidebar) sidebar.classList.remove("active");
            if (backdrop) backdrop.classList.remove("active");
        });
    }

    // Collapse/Expand Sidebar Navigation
    const collapseBtn = document.getElementById("sidebar-collapse-btn");
    if (collapseBtn) {
        collapseBtn.addEventListener("click", () => {
            if (sidebar) sidebar.classList.toggle("collapsed");
            
            // Store state in localStorage
            const isCollapsed = sidebar && sidebar.classList.contains("collapsed");
            localStorage.setItem("sidebar-collapsed", isCollapsed);
        });
    }

    // Load initial collapse state (default to true/collapsed if not set)
    const storedCollapseState = localStorage.getItem("sidebar-collapsed");
    const wasCollapsed = storedCollapseState === null ? true : (storedCollapseState === "true");
    if (sidebar) {
        if (wasCollapsed) {
            sidebar.classList.add("collapsed");
        } else {
            sidebar.classList.remove("collapsed");
        }
    }

    // switchTab is now a module-level function (defined above setupEventHandlers)

    // Click link events
    document.querySelectorAll(".sidebar-link").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const tab = btn.getAttribute("data-tab");
            if (tab === "dashboard" || tab === "transactions" || tab === "profile" || tab === "deposit" || tab === "budget" || tab === "settings" || tab === "notifications") {
                switchTab(tab);
            }
        });
    });

    // Delete budget category event delegation (CSP compliant)
    const designerList = document.getElementById("designer-category-list");
    if (designerList) {
        designerList.addEventListener("click", (e) => {
            const btn = e.target.closest('[data-action="delete-category"]');
            if (btn) {
                const itemId = parseInt(btn.getAttribute("data-id"), 10);
                if (!isNaN(itemId)) {
                    deleteCategory(itemId);
                }
            }
        });
    }

    // "View All" link on recent payouts card
    const viewAllBtn = document.getElementById("view-all-payouts-btn");
    if (viewAllBtn) {
        viewAllBtn.addEventListener("click", () => {
            switchTab("transactions");
        });
    }

    // 3D Debit Card Flip Handlers
    const cardContainer = document.getElementById("debit-card-container");
    if (cardContainer) {
        cardContainer.addEventListener("click", () => {
            cardContainer.classList.toggle("flipped");
        });
        
        // Prevent card from flipping back when clicking action buttons
        const cardBackActions = cardContainer.querySelector(".card-back-actions");
        if (cardBackActions) {
            cardBackActions.addEventListener("click", (e) => {
                e.stopPropagation();
            });
        }
    }


    // Open/Close Deposit
    const openDeposit = () => {
        // Ensure content is in deposit modal overlay before showing it as modal
        const depositModal = document.getElementById("deposit-modal");
        const depositContent = document.getElementById("deposit-modal-content");
        if (depositModal && depositContent && depositContent.parentNode !== depositModal) {
            depositModal.appendChild(depositContent);
        }

        const depositAmt = document.getElementById("deposit-amount");
        if (depositAmt) depositAmt.value = "";

        const depositPhone = document.getElementById("deposit-phone");
        const depositPhoneBadge = document.getElementById("deposit-phone-status-badge");
        const depositPhoneHint = document.getElementById("deposit-phone-hint");

        if (depositPhone) {
            if (currentSettings && currentSettings.phone_number) {
                if (!depositPhone.value) {
                    depositPhone.value = currentSettings.phone_number;
                }
                if (depositPhoneBadge) depositPhoneBadge.style.display = "none";
                if (depositPhoneHint) depositPhoneHint.innerText = "The M-Pesa STK prompt will be sent to this number. You can change it to pay from any line.";
            } else {
                if (depositPhoneBadge) depositPhoneBadge.style.display = "none";
                if (depositPhoneHint) depositPhoneHint.innerText = "The M-Pesa STK prompt will be sent to this number. You can pay from any line.";
            }
        }

        if (depositModal) depositModal.classList.add("active");
    };
    const openDepositBtn = document.getElementById("open-deposit-btn");
    if (openDepositBtn) {
        openDepositBtn.addEventListener("click", openDeposit);
    }
    const closeDepositBtn = document.getElementById("close-deposit-btn");
    if (closeDepositBtn) {
        closeDepositBtn.addEventListener("click", () => {
            if (depositModal) depositModal.classList.remove("active");
        });
    }
    depositModal.addEventListener("click", (e) => {
        if (e.target === depositModal) depositModal.classList.remove("active");
    });

    // Quick presets handler
    document.querySelectorAll(".quick-amt-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const amtInput = document.getElementById("deposit-amount");
            if (amtInput) {
                amtInput.value = btn.getAttribute("data-amount");
            }
        });
    });

    // Open/Close Settings
    document.getElementById("toggle-settings-btn").addEventListener("click", () => {
        // Only open drawer overlay if settings content is in the drawer overlay (not flat tab view)
        const settingsContent = document.getElementById("settings-drawer-content");
        if (settingsContent && settingsContent.parentNode === settingsDrawer) {
            if (currentSettings) {
                const phoneEl = document.getElementById("settings-phone");
                const timeEl = document.getElementById("settings-time");
                const budgetEl = document.getElementById("settings-budget");
                if (phoneEl) phoneEl.value = currentSettings.phone_number || "";
                if (timeEl) timeEl.value = currentSettings.payout_time || "08:00";
                if (budgetEl) budgetEl.value = currentSettings.daily_budget || 0;
            }
            settingsDrawer.classList.add("active");
        }
    });
    document.getElementById("close-settings-btn").addEventListener("click", () => {
        settingsDrawer.classList.remove("active");
    });
    settingsDrawer.addEventListener("click", (e) => {
        if (e.target === settingsDrawer) settingsDrawer.classList.remove("active");
    });



    // Deposit Submit Form
    document.getElementById("deposit-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const amount = parseFloat(document.getElementById("deposit-amount").value);
        if (isNaN(amount) || amount < 10 || amount > 250000 || !Number.isInteger(amount)) {
            alert("Invalid Amount.");
            return;
        }

        const phoneInput = document.getElementById("deposit-phone");
        const phone = phoneInput ? phoneInput.value.trim() : "";
        if (!phone && (!currentSettings || !currentSettings.phone_number)) {
            alert("Please enter a valid Safaricom M-Pesa phone number.");
            if (phoneInput) phoneInput.focus();
            return;
        }

        const payload = { amount };
        if (phone) {
            payload.phone_number = phone;
        }

        try {
            const idempKey = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `idemp_${Date.now()}_${Math.random()}`;
            const res = await fetch("/api/deposit/initiate", {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempKey
                },
                body: JSON.stringify(payload)
            });
            if (res.status === 401) return showAuthScreen();
            if (res.status === 429) {
                alert("Rate limit exceeded. Please wait a moment before trying again.");
                return;
            }
            
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Initiation failed.");
            
            // Close input modal or switch back to dashboard if flat
            const depositContent = depositModal ? depositModal.querySelector(".modal-content") : null;
            if (depositContent && depositContent.parentNode !== depositModal) {
                switchTab("dashboard");
            } else {
                depositModal.classList.remove("active");
            }
            
            // Open polling overlay
            const pollingOverlay = document.getElementById("deposit-polling-overlay");
            const progressBar = document.getElementById("stk-progress-bar");
            const statusText = document.getElementById("stk-status-text");
            
            pollingOverlay.classList.add("active");
            progressBar.style.width = "100%";
            statusText.innerText = "Waiting for confirmation (60s)...";
            
            // Start polling status
            const checkoutRequestId = data.checkout_request_id;
            let secondsLeft = 60;
            const pollIntervalTime = 2000; // 2 seconds
            
            const pollTimer = setInterval(async () => {
                secondsLeft -= 2;
                if (secondsLeft <= 0) {
                    clearInterval(pollTimer);
                    pollingOverlay.classList.remove("active");
                    alert("Payment confirmation timed out. If you completed M-Pesa PIN entry, please check dashboard balance in a few moments.");
                    pollDashboardData();
                    return;
                }
                
                // Update progress indicator
                progressBar.style.width = `${(secondsLeft / 60) * 100}%`;
                statusText.innerText = `Waiting for confirmation (${secondsLeft}s)...`;
                
                try {
                    const statusRes = await fetch(`/api/deposit/status/${checkoutRequestId}`);
                    if (statusRes.ok) {
                        const statusData = await statusRes.json();
                        if (statusData.status === "SUCCESS") {
                            clearInterval(pollTimer);
                            pollingOverlay.classList.remove("active");
                            alert("KES " + amount.toFixed(2) + " M-Pesa deposit completed successfully! 🚀🔒");
                            pollDashboardData();
                        } else if (statusData.status === "FAILED") {
                            clearInterval(pollTimer);
                            pollingOverlay.classList.remove("active");
                            alert("M-Pesa payment failed or was cancelled by user.");
                            pollDashboardData();
                        }
                    }
                } catch (pollErr) {
                    console.error("Polling error:", pollErr);
                }
            }, pollIntervalTime);
            
        } catch (err) {
            console.error(err);
            alert(err.message || "Failed to initiate M-Pesa STK Push. Make sure your phone number starts with 254 in Settings.");
        }
    });

    // Settings Submit Form
    document.getElementById("settings-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const daily_budget = parseFloat(document.getElementById("settings-budget").value);
        const payout_time = document.getElementById("settings-time").value;
        const phone_number = document.getElementById("settings-phone").value.trim();
        
        // Validate payout_time is not in the past today if changed
        if (payout_time !== currentSettings.payout_time) {
            const [hour, minute] = payout_time.split(":").map(Number);
            const now = new Date();
            const currentHour = now.getHours();
            const currentMinute = now.getMinutes();
            if (hour < currentHour || (hour === currentHour && minute <= currentMinute)) {
                alert("Payout time cannot be in the past today. Please choose a future time.");
                return;
            }
        }
        
        const payload = {
            daily_budget,
            payout_time,
            phone_number
        };

        const currentPhone = currentSettings ? (currentSettings.phone_number || "") : "";
        const hasChangedPhone = currentPhone && phone_number && (normalizePhone(phone_number) !== normalizePhone(currentPhone));

        if (hasChangedPhone) {
            const saveBtn = document.getElementById("save-settings-btn") || e.target.querySelector('button[type="submit"]');
            const errEl = document.getElementById("settings-error");
            await triggerStepupFlow(payload, "settings", saveBtn, errEl);
            return;
        }

        try {
            const res = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.status === 401) return showAuthScreen();
            
            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || "Saving settings failed.");
            }
            
            // Determine if settings was opened via sidebar (flat tab) or top nav (drawer)
            const viewSettings = document.getElementById("view-settings");
            const inFlatTabMode = viewSettings && !viewSettings.classList.contains("hidden") && viewSettings.classList.contains("active");
            if (inFlatTabMode) {
                switchTab("dashboard");
            } else {
                settingsDrawer.classList.remove("active");
            }
            pollDashboardData();
        } catch (err) {
            console.error(err);
            alert(err.message || "Failed to save settings. Check inputs.");
        }
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

    const confirmGroup = document.getElementById("auth-confirm-password-group");
    const confirmInput = document.getElementById("auth-confirm-password");

    if (tabLogin) {
        tabLogin.addEventListener("click", () => {
            currentAuthAction = "login";
            tabLogin.classList.add("active");
            if (tabSignup) tabSignup.classList.remove("active");
            if (authSubmitBtn) authSubmitBtn.innerText = "Log In";
            if (authSubtitle) authSubtitle.innerText = "Log in to manage your daily allowances";
            if (passwordLabel) passwordLabel.innerText = "Password";
            if (authPassword) authPassword.placeholder = "Enter password (min 8 chars)";
            if (confirmGroup) confirmGroup.style.display = "none";
            if (confirmInput) confirmInput.required = false;
            if (errorMsg) errorMsg.style.display = "none";
        });
    }

    if (tabSignup) {
        tabSignup.addEventListener("click", () => {
            currentAuthAction = "signup";
            tabSignup.classList.add("active");
            if (tabLogin) tabLogin.classList.remove("active");
            if (authSubmitBtn) authSubmitBtn.innerText = "Register";
            if (authSubtitle) authSubtitle.innerText = "Create an account with your Safaricom number";
            if (passwordLabel) passwordLabel.innerText = "Create Strong Password";
            if (authPassword) authPassword.placeholder = "Password (min 8 chars, A-Z, a-z, 0-9, symbol)";
            if (confirmGroup) confirmGroup.style.display = "block";
            if (confirmInput) confirmInput.required = true;
            if (errorMsg) errorMsg.style.display = "none";
        });
    }

    if (authForm) {
        authForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (errorMsg) errorMsg.style.display = "none";

            const rawVal = document.getElementById("auth-phone").value.trim();
            const isEmail = rawVal.includes("@");
            const password = authPassword ? authPassword.value : "";

            if (currentAuthAction === "signup") {
                if (!isEmail) {
                    if (errorMsg) {
                        errorMsg.innerText = "Registration requires a valid email address. Phone-only registration is disabled.";
                        errorMsg.style.display = "block";
                    }
                    return;
                }
                const confirmPassword = confirmInput ? confirmInput.value : "";
                if (password !== confirmPassword) {
                    if (errorMsg) {
                        errorMsg.innerText = "Passwords do not match.";
                        errorMsg.style.display = "block";
                    }
                    return;
                }
            }

            const url = currentAuthAction === "login" ? "/api/auth/login" : "/api/auth/signup";

            try {
                const res = await fetch(url, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ phone_number, password })
                });

                const data = await res.json();

                if (!res.ok) {
                    let detailStr = "Authentication request failed.";
                    if (data && data.detail) {
                        if (typeof data.detail === "string") {
                            detailStr = data.detail;
                        } else if (Array.isArray(data.detail)) {
                            detailStr = data.detail.map(e => e.msg || e.detail || JSON.stringify(e)).join("; ");
                        } else if (typeof data.detail === "object") {
                            detailStr = data.detail.msg || JSON.stringify(data.detail);
                        }
                    }
                    throw new Error(detailStr);
                }

                if (currentAuthAction === "signup") {
                    // If register succeeded, perform auto-login for top-tier UX
                    currentAuthAction = "login";
                    if (tabLogin) tabLogin.click();
                    const pwdEl = document.getElementById("auth-password");
                    if (pwdEl) pwdEl.value = password;
                    authForm.dispatchEvent(new Event("submit"));
                } else {
                    // Login succeeded
                    const phoneEl = document.getElementById("auth-phone");
                    if (phoneEl) phoneEl.value = "";
                    if (authPassword) authPassword.value = "";
                    
                    if (data.force_password_change) {
                        alert("Security Notice: Your account is using a legacy password. Please update your password in Profile Settings to meet the new security requirements (minimum 8 characters with uppercase, lowercase, digit, and symbol).");
                    }
                    checkAuth();
                }
            } catch (err) {
                if (errorMsg) {
                    errorMsg.innerText = err.message;
                    errorMsg.style.display = "block";
                }
            }
        });
    }

    // Logout Click
    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", handleLogout);
    }
    const sidebarLogoutBtn = document.getElementById("sidebar-logout-btn");
    if (sidebarLogoutBtn) {
        sidebarLogoutBtn.addEventListener("click", handleLogout);
    }

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

    // Budget Designer Wizard State & Handlers

    const budgetDesignerModal = document.getElementById("budget-designer-modal");
    
    const openBudgetDesignerBtn = document.getElementById("open-budget-designer-btn");
    if (openBudgetDesignerBtn) {
        openBudgetDesignerBtn.addEventListener("click", () => {
            openBudgetDesignerModal();
        });
    }
    
    const closeBudgetDesignerBtn = document.getElementById("close-budget-designer-btn");
    if (closeBudgetDesignerBtn) {
        closeBudgetDesignerBtn.addEventListener("click", () => {
            budgetDesignerModal.classList.remove("active");
        });
    }
    
    if (budgetDesignerModal) {
        budgetDesignerModal.addEventListener("click", (e) => {
            if (e.target === budgetDesignerModal) budgetDesignerModal.classList.remove("active");
        });
    }

    // Step Navigation Buttons
    const wizardNext1 = document.getElementById("budget-wizard-next-1");
    if (wizardNext1) {
        wizardNext1.addEventListener("click", () => {
            if (budgetItems.length === 0) {
                alert("Please add at least one budget category allocation before proceeding to schedule.");
                const catInput = document.getElementById("new-category-name");
                if (catInput) catInput.focus();
                return;
            }
            goToBudgetWizardStep(2);
        });
    }

    const wizardBack2 = document.getElementById("budget-wizard-back-2");
    if (wizardBack2) {
        wizardBack2.addEventListener("click", () => {
            goToBudgetWizardStep(1);
        });
    }

    const wizardNext2 = document.getElementById("budget-wizard-next-2");
    if (wizardNext2) {
        wizardNext2.addEventListener("click", () => {
            const start_date = document.getElementById("lock-start-date").value || "";
            const end_date = document.getElementById("lock-end-date").value || "";
            if (!start_date || !end_date) {
                alert("Please select both start and end dates for the payout schedule.");
                return;
            }
            goToBudgetWizardStep(3);
        });
    }

    const wizardBack3 = document.getElementById("budget-wizard-back-3");
    if (wizardBack3) {
        wizardBack3.addEventListener("click", () => {
            goToBudgetWizardStep(2);
        });
    }
    
    // Add Category Form Submit
    const addCatForm = document.getElementById("add-category-form");
    if (addCatForm) {
        addCatForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const category = document.getElementById("new-category-name").value.trim();
            const amount = parseFloat(document.getElementById("new-category-amount").value);
            if (!category || isNaN(amount) || amount <= 0) return;
            if (!Number.isInteger(amount)) {
                alert("Budget allocation amount must be a whole positive integer (no decimal places).");
                return;
            }
            
            try {
                const res = await fetch("/api/budget/items", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ category, amount })
                });
                if (res.status === 401) return showAuthScreen();
                if (!res.ok) {
                    const data = await res.json();
                    throw new Error(data.detail || "Failed to add category.");
                }
                
                document.getElementById("new-category-name").value = "";
                document.getElementById("new-category-amount").value = "";
                
                await pollDashboardData();
                const newCatName = document.getElementById("new-category-name");
                if (newCatName) newCatName.focus();
            } catch (err) {
                console.error(err);
                alert(err.message || "Failed to save category.");
            }
        });
    }

    // Helper to sanitize phone for comparison
    function normalizePhone(p) {
        if (!p) return "";
        let clean = p.replace(/\s+/g, "").replace(/\+/g, "");
        if (clean.startsWith("0")) clean = "254" + clean.substring(1);
        return clean;
    }

    let pendingStepupPayload = null;
    let stepupContext = "budget_lock"; // "budget_lock" or "settings"
    let stepupTimer = null;

    async function triggerStepupFlow(payload, context, triggerBtn, errorEl = null) {
        let originalHtml = "";
        if (triggerBtn) {
            triggerBtn.disabled = true;
            originalHtml = triggerBtn.innerHTML;
            triggerBtn.innerHTML = '<span style="display:inline-block;width:0.9rem;height:0.9rem;border:2px solid currentColor;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;margin-right:0.4rem;vertical-align:middle;"></span> Requesting authorization...';
        }
        if (errorEl) {
            errorEl.style.display = "none";
            errorEl.innerText = "";
        }

        try {
            // Request OTP before opening modal
            const res = await fetch("/api/profile/request-stepup-otp", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ purpose: "payout_stepup" })
            });

            if (res.status === 401) {
                showAuthScreen();
                return;
            }

            if (res.status === 429) {
                throw new Error("Too many requests.");
            }

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                const detail = data.detail || "";
                if (detail.includes("verified email address") || detail.includes("link an email")) {
                    throw new Error("Email verification required: Please link an email address in your Profile before updating your phone number.");
                }
                throw new Error(detail || "Failed to initiate verification code.");
            }

            // OTP dispatched successfully -> Now open step-up confirmation modal
            openStepupModal(payload, context);
        } catch (err) {
            console.error("Step-up trigger error:", err);
            if (errorEl) {
                errorEl.innerText = err.message || "Failed to initiate verification code.";
                errorEl.style.display = "block";
            } else {
                alert(err.message || "Failed to initiate verification code.");
            }
        } finally {
            if (triggerBtn) {
                triggerBtn.disabled = false;
                triggerBtn.innerHTML = originalHtml;
            }
        }
    }

    function openStepupModal(payload, context = "budget_lock") {
        pendingStepupPayload = payload;
        stepupContext = context;
        const modal = document.getElementById("stepup-payout-modal");
        const titleEl = document.getElementById("stepup-payout-title");
        const subtitleEl = document.getElementById("stepup-payout-subtitle");
        const errorEl = document.getElementById("stepup-payout-error");
        const passwordInput = document.getElementById("stepup-payout-password");
        const otpInput = document.getElementById("stepup-payout-otp");
        const resendBtn = document.getElementById("stepup-resend-otp-btn");
        const confirmBtn = document.getElementById("confirm-stepup-payout-btn");

        if (titleEl) {
            titleEl.innerHTML = context === "settings"
                ? '<i data-lucide="shield-alert" style="color: #f59e0b; width: 1.3rem; height: 1.3rem;"></i> Confirm Phone Number Change'
                : '<i data-lucide="shield-alert" style="color: #f59e0b; width: 1.3rem; height: 1.3rem;"></i> Confirm Payout Line Change';
        }
        if (subtitleEl) {
            subtitleEl.innerText = context === "settings"
                ? "For your financial protection, updating your account phone number requires your account password and email verification."
                : "For your financial protection, modifying your automated daily payout destination requires your account password and email verification.";
        }

        if (confirmBtn) {
            if (context === "settings") {
                confirmBtn.innerHTML = '<i data-lucide="check" style="width: 1rem; height: 1rem;"></i> Save';
            } else {
                confirmBtn.innerHTML = '<i data-lucide="lock" style="width: 1rem; height: 1rem;"></i> Lock Budget';
            }
        }
        if (window.lucide) lucide.createIcons();

        if (errorEl) { errorEl.style.display = "none"; errorEl.innerText = ""; }
        if (passwordInput) passwordInput.value = "";
        if (otpInput) otpInput.value = "";

        // Start 60-second cooldown timer since OTP was just sent
        if (resendBtn) {
            resendBtn.disabled = true;
            let countdown = 60;
            resendBtn.innerText = `Resend in ${countdown}s`;
            clearInterval(stepupTimer);
            stepupTimer = setInterval(() => {
                countdown--;
                if (countdown <= 0) {
                    clearInterval(stepupTimer);
                    resendBtn.disabled = false;
                    resendBtn.innerText = "Resend Code";
                } else {
                    resendBtn.innerText = `Resend in ${countdown}s`;
                }
            }, 1000);
        }

        if (modal) modal.classList.add("active");
        if (passwordInput) passwordInput.focus();
    }

    async function requestStepupOtp() {
        const resendBtn = document.getElementById("stepup-resend-otp-btn");
        const errorEl = document.getElementById("stepup-payout-error");
        try {
            if (errorEl) { errorEl.style.display = "none"; errorEl.innerText = ""; }
            if (resendBtn) {
                resendBtn.disabled = true;
                let countdown = 60;
                resendBtn.innerText = `Resend in ${countdown}s`;
                clearInterval(stepupTimer);
                stepupTimer = setInterval(() => {
                    countdown--;
                    if (countdown <= 0) {
                        clearInterval(stepupTimer);
                        resendBtn.disabled = false;
                        resendBtn.innerText = "Resend Code";
                    } else {
                        resendBtn.innerText = `Resend in ${countdown}s`;
                    }
                }, 1000);
            }

            const res = await fetch("/api/profile/request-stepup-otp", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ purpose: "payout_stepup" })
            });
            if (res.status === 401) return showAuthScreen();
            if (res.status === 429) {
                throw new Error("Too many requests. Please wait a minute before requesting another verification code.");
            }
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || "Failed to send authorization code.");
            }
        } catch (err) {
            console.error("Step-up OTP request error:", err);
            if (errorEl) {
                errorEl.innerText = err.message || "Failed to send verification code.";
                errorEl.style.display = "block";
            }
        }
    }

    const closeStepupBtn = document.getElementById("close-stepup-payout-btn");
    const cancelStepupBtn = document.getElementById("cancel-stepup-payout-btn");
    if (closeStepupBtn) {
        closeStepupBtn.addEventListener("click", () => {
            const modal = document.getElementById("stepup-payout-modal");
            if (modal) modal.classList.remove("active");
            clearInterval(stepupTimer);
        });
    }
    if (cancelStepupBtn) {
        cancelStepupBtn.addEventListener("click", () => {
            const modal = document.getElementById("stepup-payout-modal");
            if (modal) modal.classList.remove("active");
            clearInterval(stepupTimer);
        });
    }

    const resendStepupBtn = document.getElementById("stepup-resend-otp-btn");
    if (resendStepupBtn) {
        resendStepupBtn.addEventListener("click", (e) => {
            e.preventDefault();
            requestStepupOtp();
        });
    }

    const stepupForm = document.getElementById("stepup-payout-form");
    if (stepupForm) {
        stepupForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const password = document.getElementById("stepup-payout-password").value;
            const otp_code = document.getElementById("stepup-payout-otp").value.trim();
            const errorEl = document.getElementById("stepup-payout-error");
            const confirmBtn = document.getElementById("confirm-stepup-payout-btn");

            if (!password || !otp_code || otp_code.length !== 6) {
                if (errorEl) {
                    errorEl.innerText = "Please enter your password and complete 6-digit verification code.";
                    errorEl.style.display = "block";
                }
                return;
            }

            try {
                if (confirmBtn) confirmBtn.disabled = true;
                if (errorEl) errorEl.style.display = "none";

                const finalPayload = {
                    ...pendingStepupPayload,
                    password,
                    otp_code
                };

                const endpoint = stepupContext === "settings" ? "/api/settings" : "/api/budget/lock";

                const res = await fetch(endpoint, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(finalPayload)
                });
                if (!res.ok) {
                    const data = await res.json();
                    throw new Error(data.detail || "Failed to authorize changes.");
                }

                const stepupModal = document.getElementById("stepup-payout-modal");
                if (stepupModal) stepupModal.classList.remove("active");
                clearInterval(stepupTimer);

                if (stepupContext === "settings") {
                    alert("Settings successfully updated!");
                    const viewSettings = document.getElementById("view-settings");
                    const inFlatTabMode = viewSettings && !viewSettings.classList.contains("hidden") && viewSettings.classList.contains("active");
                    if (inFlatTabMode) {
                        switchTab("dashboard");
                    } else {
                        const settingsDrawer = document.getElementById("settings-drawer");
                        if (settingsDrawer) settingsDrawer.classList.remove("active");
                    }
                } else {
                    alert("Budget successfully finalized and locked for this month! 🔒");
                    // Close Budget Designer Modal
                    const budgetModal = document.getElementById("budget-designer-modal");
                    const budgetContent = document.getElementById("budget-designer-modal-content");
                    if (budgetContent && budgetModal && budgetContent.parentNode !== budgetModal) {
                        switchTab("dashboard");
                    } else if (budgetModal) {
                        budgetModal.classList.remove("active");
                    }
                }

                await pollDashboardData();
            } catch (err) {
                console.error("Step-up authorization error:", err);
                if (errorEl) {
                    errorEl.innerText = err.message || "Invalid credentials or verification code.";
                    errorEl.style.display = "block";
                }
            } finally {
                if (confirmBtn) confirmBtn.disabled = false;
            }
        });
    }

    const lockBudgetBtn = document.getElementById("lock-budget-btn");
    if (lockBudgetBtn) {
        lockBudgetBtn.addEventListener("click", async () => {
            const start_date = document.getElementById("lock-start-date").value || "";
            const end_date = document.getElementById("lock-end-date").value || "";
            const payout_phone_el = document.getElementById("budget-lock-payout-phone");
            const payout_phone = payout_phone_el ? payout_phone_el.value.trim() : "";
            
            const hasExistingPhone = currentSettings && (currentSettings.phone_number || currentSettings.payout_phone_number);
            if (!hasExistingPhone && !payout_phone) {
                alert("Please enter a valid Safaricom M-Pesa phone number to receive your daily disbursements.");
                if (payout_phone_el) payout_phone_el.focus();
                return;
            }

            if (!start_date || !end_date) {
                alert("Please select both start and end dates for the payout schedule.");
                goToBudgetWizardStep(2);
                return;
            }

            if (budgetItems.length === 0) {
                alert("Cannot lock an empty budget. Please add budget items first.");
                goToBudgetWizardStep(1);
                return;
            }
            
            if (!confirm("Are you sure you want to finalize and lock your budget? Once locked, you cannot add or delete allocation categories until the first day of next month.")) {
                return;
            }

            const currentSavedPhone = currentSettings && (currentSettings.payout_phone_number || currentSettings.phone_number);
            const hasChangedPhone = currentSavedPhone && payout_phone && (normalizePhone(payout_phone) !== normalizePhone(currentSavedPhone));

            if (hasChangedPhone) {
                const lockPayload = { start_date, end_date, payout_phone_number: payout_phone };
                await triggerStepupFlow(lockPayload, "budget_lock", lockBudgetBtn);
                return;
            }
            
            try {
                const lockPayload = { start_date, end_date };
                if (payout_phone) {
                    lockPayload.payout_phone_number = payout_phone;
                }
                const res = await fetch("/api/budget/lock", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(lockPayload)
                });
                if (res.status === 401) return showAuthScreen();
                if (!res.ok) {
                    const data = await res.json();
                    throw new Error(data.detail || "Failed to lock budget.");
                }
                alert("Budget successfully finalized and locked for this month! 🔒");
                await pollDashboardData();
                
                // Close modal or switch back to dashboard if flat
                const budgetModal = document.getElementById("budget-designer-modal");
                const budgetContent = document.getElementById("budget-designer-modal-content");
                if (budgetContent && budgetModal && budgetContent.parentNode !== budgetModal) {
                    switchTab("dashboard");
                } else if (budgetModal) {
                    budgetModal.classList.remove("active");
                }
            } catch (err) {
                console.error(err);
                alert(err.message || "Failed to finalize and lock budget.");
            }
        });
    }

    // Manual Payout Run Handler — uses event delegation because button visibility is dynamic
    document.addEventListener("click", async (e) => {
        const btn = e.target.closest("#trigger-payout-btn");
        if (!btn) return;

        btn.disabled = true;
        const originalHTML = btn.innerHTML;
        btn.innerHTML = `<i data-lucide="loader" class="spin" style="width: 1rem; height: 1rem; display: inline-block; vertical-align: middle;"></i> Running...`;
        if (window.lucide) window.lucide.createIcons();

        try {
            const res = await fetch("/api/payout/trigger", { method: "POST" });
            if (res.status === 401) return showAuthScreen();
            const data = await res.json();

            if (res.ok) {
                if (data.triggered) {
                    alert("Daily allowance distribution completed! 🚀");
                } else {
                    alert(data.reason || "No payout due or payout already completed today.");
                }
            } else {
                alert(data.detail || "Payout trigger failed. Please check your configuration.");
            }
            pollDashboardData();
        } catch (err) {
            console.error("Payout trigger error:", err);
            alert("Failed to contact server. Please try again.");
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
            if (window.lucide) window.lucide.createIcons();
        }
    });

    // Collapsible Payout Schedule in Budget Creator Modal
    const scheduleHdr = document.getElementById("schedule-toggle-hdr");
    const scheduleBody = document.getElementById("schedule-collapse-body");
    const scheduleChevron = document.getElementById("schedule-chevron");
    
    if (scheduleHdr) {
        scheduleHdr.addEventListener("click", () => {
            if (scheduleBody) {
                const isCollapsed = scheduleBody.style.display === "none";
                scheduleBody.style.display = isCollapsed ? "block" : "none";
                if (scheduleChevron) {
                    if (isCollapsed) {
                        scheduleChevron.classList.add("expanded");
                    } else {
                        scheduleChevron.classList.remove("expanded");
                    }
                }
            }
        });
    }
    // Notification Drawer Toggle Listeners
    const navNotifBtn = document.getElementById("nav-notifications-btn");
    const closeNotifBtn = document.getElementById("close-notifications-btn");
    const notifDrawer = document.getElementById("notifications-drawer");
    const markAllReadBtn = document.getElementById("mark-all-read-btn");
    const bannerQuickDepositBtn = document.getElementById("banner-quick-deposit-btn");

    if (navNotifBtn) {
        navNotifBtn.addEventListener("click", () => {
            const notifContent = document.getElementById("notifications-drawer-content");
            if (notifContent && notifContent.parentNode === notifDrawer) {
                notifDrawer.classList.add("active");
            }
            fetchNotifications();
        });
    }

    if (closeNotifBtn) {
        closeNotifBtn.addEventListener("click", () => {
            const viewNotifications = document.getElementById("view-notifications");
            const inFlatTabMode = viewNotifications && !viewNotifications.classList.contains("hidden") && viewNotifications.classList.contains("active");
            if (inFlatTabMode) {
                switchTab("dashboard");
            } else if (notifDrawer) {
                notifDrawer.classList.remove("active");
            }
        });
    }

    if (notifDrawer) {
        notifDrawer.addEventListener("click", (e) => {
            if (e.target === notifDrawer) notifDrawer.classList.remove("active");
        });
    }

    if (markAllReadBtn) markAllReadBtn.addEventListener("click", markAllNotificationsAsRead);

    if (bannerQuickDepositBtn) {
        bannerQuickDepositBtn.addEventListener("click", () => {
            const depositModal = document.getElementById("deposit-modal");
            if (depositModal) depositModal.classList.add("active");
        });
    }

    setupProfileHandlers();
}

// Notifications API Controllers
async function fetchNotifications() {
    if (!isAuthenticated) return;
    try {
        const res = await fetch("/api/notifications", { headers: { "X-Background-Poll": "true" } });
        if (res.status === 401) return;
        const data = await res.json();
        if (data.status === "success") {
            updateNotificationUI(data.notifications, data.unread_count);
        }
    } catch (err) {
        console.error("Error fetching notifications:", err);
    }
}

function updateNotificationUI(notifications, unreadCount) {
    const navBadge = document.getElementById("nav-notifications-badge");
    const sidebarBadge = document.getElementById("sidebar-notifications-badge");
    const badgeText = unreadCount > 99 ? "99+" : String(unreadCount);

    [navBadge, sidebarBadge].forEach(badge => {
        if (badge) {
            if (unreadCount > 0) {
                badge.innerText = badgeText;
                badge.style.display = "inline-flex";
            } else {
                badge.style.display = "none";
            }
        }
    });

    const listEl = document.getElementById("notifications-list");
    const emptyState = document.getElementById("notifications-empty-state");
    if (listEl) {
        if (!notifications || notifications.length === 0) {
            listEl.innerHTML = "";
            if (emptyState) emptyState.style.display = "block";
        } else {
            if (emptyState) emptyState.style.display = "none";
            listEl.innerHTML = notifications.map(n => `
                <div class="notification-item ${n.is_read ? '' : 'unread'}" data-id="${n.id}">
                    <div class="notification-item-header">
                        <span class="notification-item-title">${escapeHTML(n.title)}</span>
                        <span class="notification-item-time">${n.created_at || ''}</span>
                    </div>
                    <p class="notification-item-message">${escapeHTML(n.message)}</p>
                    ${!n.is_read ? `<button class="btn btn-ghost btn-sm mark-single-read-btn" data-id="${n.id}" style="font-size: 0.75rem; padding: 0.2rem 0.5rem; margin-top: 0.4rem; color: var(--color-accent-violet); background: transparent; border: 1px solid rgba(139,92,246,0.3); border-radius: 0.35rem; cursor: pointer;">Mark as read</button>` : ''}
                </div>
            `).join("");

            listEl.querySelectorAll(".mark-single-read-btn").forEach(btn => {
                btn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    const notifId = btn.getAttribute("data-id");
                    await markNotificationAsRead(notifId);
                });
            });
        }
    }

    const banner = document.getElementById("insufficient-balance-alert-banner");
    if (banner) {
        const unreadWarning = notifications.find(n => !n.is_read && n.type === "WARNING");
        if (unreadWarning) {
            const titleEl = document.getElementById("alert-banner-title");
            const msgEl = document.getElementById("alert-banner-msg");
            if (titleEl) titleEl.innerText = unreadWarning.title;
            if (msgEl) msgEl.innerText = unreadWarning.message;
            banner.style.display = "flex";
        } else {
            banner.style.display = "none";
        }
    }
}

async function markNotificationAsRead(id) {
    try {
        const res = await fetch(`/api/notifications/${id}/read`, { method: "POST" });
        if (res.ok) fetchNotifications();
    } catch (err) {
        console.error("Error marking notification as read:", err);
    }
}

async function markAllNotificationsAsRead() {
    try {
        const res = await fetch("/api/notifications/read-all", { method: "POST" });
        if (res.ok) fetchNotifications();
    } catch (err) {
        console.error("Error marking all notifications as read:", err);
    }
}



// Fetch general configuration & state
async function fetchSettings() {
    try {
        const res = await fetch("/api/settings", { headers: { "X-Background-Poll": "true" } });
        if (res.status === 401) return showAuthScreen();
        const data = await res.json();
        currentSettings = data;

        // Update indicators
        updateDashboardMetrics(data);
        refreshChart();
    } catch (err) {
        console.error("Error fetching settings:", err);
    }
}

// Update UI dashboard labels based on backend model state
function updateDashboardMetrics(settings) {
    document.getElementById("wallet-balance").innerText = parseFloat(settings.balance || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    
    const inlineInput = document.getElementById("inline-budget-input");
    if (inlineInput && inlineInput.style.display !== "inline-block") {
        const displayBudget = settings.is_budget_locked ? parseFloat(settings.daily_budget || 0) : 0.00;
        document.getElementById("daily-budget-value").innerText = displayBudget.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    
    document.getElementById("payout-time-info").innerText = `Payout: ${settings.payout_time || "08:00"}`;

    const settingsDrawer = document.getElementById("settings-drawer");
    const isSettingsDrawerOpen = settingsDrawer && settingsDrawer.classList.contains("active");
    const viewSettings = document.getElementById("view-settings");
    const inFlatTabMode = viewSettings && !viewSettings.classList.contains("hidden") && viewSettings.classList.contains("active");
    const isEditingSettings = isSettingsDrawerOpen || inFlatTabMode || [
        document.getElementById("settings-phone"),
        document.getElementById("settings-time"),
        document.getElementById("settings-budget")
    ].some(el => el && el === document.activeElement);

    const settingsBudgetInput = document.getElementById("settings-budget");
    if (settingsBudgetInput) {
        if (!isEditingSettings) {
            settingsBudgetInput.value = settings.daily_budget || 0;
        }
        if (settings.is_budget_locked) {
            settingsBudgetInput.disabled = true;
            settingsBudgetInput.title = "Budget is locked until the end of the month.";
        } else {
            settingsBudgetInput.disabled = false;
            settingsBudgetInput.title = "";
        }
    }

    const editBudgetBtn = document.getElementById("edit-budget-btn");
    const budgetLockBadge = document.getElementById("budget-lock-badge");
    const budgetWarningBadge = document.getElementById("budget-warning-badge");
    
    if (settings.is_budget_locked) {
        if (editBudgetBtn) editBudgetBtn.style.display = "none";
        if (budgetLockBadge) budgetLockBadge.style.display = "inline-flex";
    } else {
        if (editBudgetBtn) editBudgetBtn.style.display = "inline-flex";
        if (budgetLockBadge) budgetLockBadge.style.display = "none";
    }
    
    if (budgetWarningBadge) {
        const budget = parseFloat(settings.daily_budget || 0);
        const bal = parseFloat(settings.balance || 0);
        if (budget > bal && bal > 0) {
            budgetWarningBadge.style.display = "inline-flex";
            budgetWarningBadge.title = "Your daily budget is greater than your current deposit balance.";
        } else {
            budgetWarningBadge.style.display = "none";
        }
    }

    if (!isEditingSettings) {
        const timeEl = document.getElementById("settings-time");
        const phoneEl = document.getElementById("settings-phone");
        if (timeEl) timeEl.value = settings.payout_time || "08:00";
        if (phoneEl) phoneEl.value = settings.phone_number || "";
    }

    const depositPhone = document.getElementById("deposit-phone");
    const depositPhoneBadge = document.getElementById("deposit-phone-status-badge");
    const depositPhoneHint = document.getElementById("deposit-phone-hint");
    if (depositPhone && settings.phone_number) {
        if (!depositPhone.value || depositPhone.value === "") {
            depositPhone.value = settings.phone_number;
        }
        if (depositPhoneBadge) depositPhoneBadge.style.display = "inline-block";
        if (depositPhoneHint) depositPhoneHint.innerText = "The STK push prompt will be sent to your saved Safaricom line.";
    }

    // Update Withdraw Button Visibility (Only visible when deposit is NOT locked and balance >= 10)
    const openWithdrawBtn = document.getElementById("open-withdraw-btn");
    if (openWithdrawBtn) {
        const bal = parseFloat(settings.balance || 0);
        if (!settings.is_deposit_locked && bal >= 10) {
            openWithdrawBtn.style.display = "inline-flex";
        } else {
            openWithdrawBtn.style.display = "none";
        }
    }
}

// Fetch historical payout transaction rows
async function fetchPayouts() {
    try {
        const res = await fetch("/api/payouts", { headers: { "X-Background-Poll": "true" } });
        if (res.status === 401) return showAuthScreen();
        const data = await res.json();
        currentPayouts = data;

        // Always sync the Run Payout retry button visibility after any data refresh.
        // This runs unconditionally — independent of budget lock state — so it works
        // for fresh users and users with no budget configured.
        updatePayoutRetryFooter();

        document.getElementById("payout-count-badge").innerText = `${data.length} total`;

        const body = document.getElementById("payout-history-body");
        const bodyRecent = document.getElementById("payout-history-body-recent");
        
        if (data.length === 0) {
            const emptyHTML = `<tr><td colspan="6" class="empty-state">No transactions recorded yet.</td></tr>`;
            if (body) body.innerHTML = emptyHTML;
            if (bodyRecent) bodyRecent.innerHTML = emptyHTML;
            refreshChart();
            return;
        }

        const renderRows = (items) => {
            return items.map(payout => {
                let statusClass = "badge-pending";
                let statusText = payout.status;
                let tooltip = "";

                if (payout.status === "SUCCESS") {
                    statusClass = "badge-success";
                } else if (payout.status === "FAILED") {
                    statusClass = "badge-failed";
                    tooltip = `title="${escapeHTML(payout.error_message || 'Transaction rejected')}"`;
                }

                // Show the exact timestamp of completion or failure
                const exactTime = payout.completed_at || payout.failed_at || "";
                const timeDisplay = exactTime ? escapeHTML(exactTime.split(" ")[1] || exactTime) : "—";

                return `
                    <tr>
                        <td data-label="Date"><strong>${escapeHTML(payout.payout_date || '')}</strong></td>
                        <td data-label="Time" class="text-mono" style="font-size:0.82rem; color: var(--text-muted);">${timeDisplay}</td>
                        <td data-label="Amount">KES ${parseFloat(payout.amount || 0).toFixed(2)}</td>
                        <td data-label="Recipient">${escapeHTML(payout.phone_number || '')}</td>
                        <td data-label="M-Pesa Ref" class="text-mono">${escapeHTML(payout.transaction_id || payout.conversation_id || '—')}</td>
                        <td data-label="Status"><span class="badge ${statusClass}" ${tooltip}>${escapeHTML(statusText || '')}</span></td>
                    </tr>
                `;
            }).join("");
        };

        if (body) body.innerHTML = renderRows(data);
        if (bodyRecent) bodyRecent.innerHTML = renderRows(data.slice(0, 5));
        
        refreshChart();
    } catch (err) {
        console.error("Error fetching payouts:", err);
    }
}

// Updates the Run Payout retry footer visibility based on today's payout status.
// Called after every fetchPayouts() so state is always current.
function updatePayoutRetryFooter() {
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const failedToday = currentPayouts.some(p => p.payout_date === todayStr && p.status === 'FAILED');
    const retryFooter = document.getElementById("payout-retry-footer");
    if (retryFooter) {
        retryFooter.style.display = failedToday ? "block" : "none";
        if (window.lucide) window.lucide.createIcons();
    }
}

// Render interactive Chart.js spent vs remaining doughnut chart
function renderBalanceChart(payouts, settings) {
    const canvas = document.getElementById("balance-chart");
    if (!canvas) return;
    
    let remaining = parseFloat(settings.balance || 0);
    let spent = payouts.filter(p => p.status === "SUCCESS").reduce((acc, curr) => acc + parseFloat(curr.amount || 0), 0);
    
    // Fallback if both are zero to render a clean, empty available circle
    let chartData = [spent, remaining];
    let isDefaultEmpty = spent === 0 && remaining === 0;
    if (isDefaultEmpty) {
        chartData = [0, 100]; // 100% default placeholder for remaining
    }
    
    // Update custom HTML legend
    const legendContainer = document.getElementById("chart-legend");
    if (legendContainer) {
        const total = spent + remaining;
        const spentPercent = total > 0 ? ((spent / total) * 100).toFixed(0) : 0;
        const remainingPercent = total > 0 ? ((remaining / total) * 100).toFixed(0) : (isDefaultEmpty ? 0 : 100);
        
        legendContainer.innerHTML = `
            <div class="legend-pill" title="Current Wallet Balance available for future payouts">
                <span class="legend-color-dot" style="background-color: var(--color-accent-violet);"></span>
                <span class="legend-label">Remaining:</span>
                <span class="legend-value">KES ${remaining.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                <span class="legend-percent">${remainingPercent}%</span>
            </div>
            <div class="legend-pill" title="Sum of successful daily payout distributions">
                <span class="legend-color-dot" style="background-color: #2E3244;"></span>
                <span class="legend-label">Spent:</span>
                <span class="legend-value">KES ${spent.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                <span class="legend-percent">${spentPercent}%</span>
            </div>
        `;
    }
    
    const ctx = canvas.getContext("2d");
    
    // Create spent color (Dark Slate)
    const spentGrad = '#2E3244';
    
    // Create remaining gradient (Safety Orange to Lighter Brand Orange)
    const remainingGrad = ctx.createLinearGradient(0, 0, 0, 120);
    remainingGrad.addColorStop(0, '#FF5B22'); // Safety Orange
    remainingGrad.addColorStop(1, '#FF7A45'); // Lighter Orange
    
    const chartColors = [spentGrad, remainingGrad];
    const hoverColors = [
        '#3A3F56', // Dark Slate hover
        '#FF6B35'  // Safety Orange hover
    ];
    
    if (balanceChartInstance) {
        // Re-assign gradients in case canvas dimensions resized
        balanceChartInstance.data.datasets[0].data = chartData;
        balanceChartInstance.data.datasets[0].backgroundColor = chartColors;
        balanceChartInstance.update();
    } else {
        balanceChartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Spent', 'Remaining'],
                datasets: [{
                    data: chartData,
                    backgroundColor: chartColors,
                    borderColor: [
                        '#16171E',
                        '#16171E'
                    ],
                    borderWidth: 2,
                    hoverBackgroundColor: hoverColors,
                    hoverBorderColor: [
                        '#2E3244',
                        'rgba(255, 91, 34, 0.4)'
                    ],
                    hoverOffset: 12
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%', // Donut thickness
                plugins: {
                    legend: {
                        display: false // Hide default legend to use our premium custom HTML UI legends
                    },
                    tooltip: {
                        backgroundColor: 'rgba(18, 22, 37, 0.95)',
                        titleFont: {
                            family: 'Outfit',
                            size: 13,
                            weight: '600'
                        },
                        bodyFont: {
                            family: 'Outfit',
                            size: 12
                        },
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        padding: 10,
                        displayColors: true,
                        boxWidth: 8,
                        boxHeight: 8,
                        boxPadding: 4,
                        callbacks: {
                            label: function(context) {
                                let val = context.raw;
                                if (isDefaultEmpty && context.dataIndex === 1) {
                                    val = 0; // Show 0 for default placeholder
                                }
                                return ` ${context.label}: KES ${val.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                            }
                        }
                    }
                }
            }
        });
    }
}

// Wrapper function to trigger chart update with latest state
function refreshChart() {
    renderBalanceChart(currentPayouts, currentSettings);
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
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        const todayStr = `${year}-${month}-${day}`;

        // 1. A failed payout takes priority over all other timer states (preserves dashboard.spec.js E2E test)
        const failedToday = currentPayouts.some(p => p.payout_date === todayStr && p.status === 'FAILED');
        if (failedToday) {
            timerLabel.innerText = "Payout Failed — Use Run Payout";
            return;
        }

        const dailyBudget = parseFloat(currentSettings.daily_budget || 0);
        const balance = parseFloat(currentSettings.balance || 0);

        // 2. No Budget Set (unset, zero budget, or unlocked budget)
        if (dailyBudget <= 0 || !currentSettings.is_budget_locked) {
            timerLabel.innerText = "No Budget Set";
            return;
        }

        // 4. Schedule Ended
        if (currentSettings.end_date && todayStr > currentSettings.end_date) {
            timerLabel.innerText = "Schedule Ended";
            return;
        }

        // 5. Low Balance (wallet balance < daily budget when budget is locked)
        if (balance < dailyBudget) {
            timerLabel.innerText = "Top-up Required";
            return;
        }

        // 6. Live Payout Countdown or Payout is Due (when balance >= daily budget)
        const payoutToday = currentPayouts.some(p => p.payout_date === todayStr && (p.status === 'SUCCESS' || p.status === 'PENDING'));
        const [hour, minute] = currentSettings.payout_time.split(":").map(Number);
        
        let target = new Date();
        target.setHours(hour, minute, 0, 0);

        if (currentSettings.start_date && todayStr < currentSettings.start_date) {
            const [sYear, sMonth, sDay] = currentSettings.start_date.split("-").map(Number);
            target = new Date(sYear, sMonth - 1, sDay, hour, minute, 0, 0);
        } else if (payoutToday) {
            target.setDate(target.getDate() + 1);
        } else if (now >= target) {
            timerLabel.innerText = "Payout is due";
            return;
        }

        const diffMs = target - now;
        if (diffMs <= 0) {
            timerLabel.innerText = "00h 00m 00s";
            return;
        }
        
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
    fetchProfile();
    fetchPayouts();
    fetchBudgetItems();
    fetchNotifications();
}

// Fetch user's custom budget categories
async function fetchBudgetItems() {
    try {
        const res = await fetch("/api/budget/items", { headers: { "X-Background-Poll": "true" } });
        if (res.status === 401) return showAuthScreen();
        const data = await res.json();
        budgetItems = data;
        
        renderBudgetBreakdown();
    } catch (err) {
        console.error("Error fetching budget items:", err);
    }
}

// Render the breakdown pills in the Daily Budget card and inside the Budget Creator modal
function renderBudgetBreakdown() {
    const designerList = document.getElementById("designer-category-list");
    const designerTotal = document.getElementById("designer-total-budget");
    const mainBreakdownList = document.getElementById("budget-breakdown-list");
    
    // Check lock states
    const isLocked = currentSettings && currentSettings.is_budget_locked;
    
    // Render pills on the main dashboard Daily Budget card
    if (mainBreakdownList) {
        if (!isLocked || budgetItems.length === 0) {
            mainBreakdownList.innerHTML = `<span style="font-size: 0.8rem; color: var(--text-muted); font-style: italic;">No categories configured. Click 'Create' to begin.</span>`;
        } else {
            mainBreakdownList.innerHTML = budgetItems.map(item => `
                <span class="category-pill" title="Daily allocation: KES ${item.amount.toFixed(2)}">
                    <span class="legend-color-dot" style="background-color: var(--color-accent-violet); width: 6px; height: 6px; display: inline-block; border-radius: 50%; margin-right: 0.2rem;"></span>
                    <span class="category-name">${escapeHTML(item.category)}</span>
                    <span class="category-pill-amount">KES ${item.amount.toFixed(0)}</span>
                </span>
            `).join("");
        }
    }

    // Render rows inside the designer modal list
    if (designerList) {
        if (budgetItems.length === 0) {
            designerList.innerHTML = `<div class="empty-state" style="padding: 1.5rem 0; color: var(--text-muted); text-align: center; font-style: italic;">No categories defined. Add one below to start.</div>`;
        } else {
            designerList.innerHTML = budgetItems.map(item => `
                <div class="designer-row">
                    <div class="designer-row-info">
                        <span class="designer-category-name">${escapeHTML(item.category)}</span>
                        <span class="designer-category-val">Daily allocation: <span>KES ${item.amount.toFixed(2)}</span></span>
                    </div>
                    ${isLocked ? '' : `
                    <button class="icon-link-btn cancel-btn" data-action="delete-category" data-id="${item.id}" title="Delete allocation category">
                        <i data-lucide="trash-2" style="width: 1.1rem; height: 1.1rem; pointer-events: none;"></i>
                    </button>
                    `}
                </div>
            `).join("");
            // Re-render Lucide icons for trash bin
            if (window.lucide) {
                window.lucide.createIcons();
            }
        }
    }
    
    // Render total sum in modal
    if (designerTotal) {
        const totalSum = budgetItems.reduce((acc, curr) => acc + curr.amount, 0);
        designerTotal.innerText = `KES ${totalSum.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    
    // Handle lock banner and add form states
    const lockNotice = document.getElementById("budget-creator-lock-notice");
    const lockNoticeText = document.getElementById("budget-lock-notice-text");
    const lockBtn = document.getElementById("lock-budget-btn");
    const addForm = document.getElementById("add-category-form");

    // Populate Payout Phone & Status Badge
    const payoutPhoneInput = document.getElementById("budget-lock-payout-phone");
    const payoutPhoneStatus = document.getElementById("budget-lock-phone-status");
    if (payoutPhoneInput) {
        if (currentSettings && (currentSettings.phone_number || currentSettings.payout_phone_number)) {
            if (!payoutPhoneInput.value) {
                payoutPhoneInput.value = currentSettings.payout_phone_number || currentSettings.phone_number;
            }
            if (payoutPhoneStatus) payoutPhoneStatus.innerText = "Configured Line";
        } else {
            if (payoutPhoneStatus) payoutPhoneStatus.innerText = "Required";
        }
    }

    if (isLocked) {
        if (lockNotice) {
            lockNotice.style.display = "flex";
            if (lockNoticeText) {
                let text = `<strong>Locked:</strong> Allocations are locked until the end of the month to prevent overspending.`;
                if (currentSettings.start_date || currentSettings.end_date) {
                    text += `<br><span style="display:inline-block; margin-top:0.25rem; font-size:0.75rem;"><i data-lucide="calendar" style="width:0.85rem; height:0.85rem; vertical-align:middle; margin-right:0.15rem; display:inline-block;"></i> Payout schedule: <strong>${escapeHTML(currentSettings.start_date || 'immediate')}</strong> to <strong>${escapeHTML(currentSettings.end_date || 'indefinite')}</strong></span>`;
                }
                lockNoticeText.innerHTML = text;
                if (window.lucide) {
                    window.lucide.createIcons();
                }
            }
        }
        if (lockBtn) lockBtn.style.display = "none";
        
        // Disable inputs when locked
        const allModalInputs = document.querySelectorAll("#budget-designer-modal-content input, #budget-designer-modal-content form button");
        allModalInputs.forEach(el => el.disabled = true);
    } else {
        if (lockNotice) lockNotice.style.display = "none";
        if (lockBtn) lockBtn.style.display = "flex";
        
        const allModalInputs = document.querySelectorAll("#budget-designer-modal-content input, #budget-designer-modal-content form button");
        allModalInputs.forEach(el => el.disabled = false);
    }
}

// Simple HTML Escaper for security
function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, 
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

// Call API to delete budget category allocation item
async function deleteCategory(itemId) {
    const isLocked = currentSettings && currentSettings.is_budget_locked;
    if (isLocked) {
        alert("Budget is locked until the end of the month.");
        return;
    }
    
    if (!window.__SKIP_CONFIRM__ && !confirm("Are you sure you want to delete this category?")) return;
    
    try {
        const res = await fetch(`/api/budget/items/${itemId}`, { method: "DELETE" });
        if (res.status === 401) return showAuthScreen();
        if (!res.ok) throw new Error("Deletion failed");
        
        await pollDashboardData();
    } catch (err) {
        console.error(err);
        alert("Failed to delete category.");
    }
}

// Attach to window so onclick attribute can bind successfully
window.deleteCategory = deleteCategory;

// Opens the Budget Creator modal and resets scroll positions & focus for optimal UX
async function openBudgetDesignerModal() {
    const budgetModal = document.getElementById("budget-designer-modal");
    if (!budgetModal) return;

    // Ensure content is in budget modal overlay before showing it as modal
    const budgetContent = document.getElementById("budget-designer-modal-content");
    if (budgetModal && budgetContent && budgetContent.parentNode !== budgetModal) {
        budgetModal.appendChild(budgetContent);
    }

    // Reset input fields
    const newCatName = document.getElementById("new-category-name");
    const newCatAmount = document.getElementById("new-category-amount");
    if (newCatName) newCatName.value = "";
    if (newCatAmount) newCatAmount.value = "";

    // Reset wizard track to Step 1
    goToBudgetWizardStep(1);

    // Reset scroll positions of both the modal overlay and the inner designer body to 0
    budgetModal.scrollTop = 0;

    // Show modal
    budgetModal.classList.add("active");

    // Fetch fresh settings before rendering so lock state is always current
    await fetchSettings();

    // Fill date fields now that currentSettings is refreshed
    const startDateInput = document.getElementById("lock-start-date");
    const endDateInput = document.getElementById("lock-end-date");
    if (startDateInput && currentSettings.start_date) startDateInput.value = currentSettings.start_date;
    if (endDateInput && currentSettings.end_date) endDateInput.value = currentSettings.end_date;

    // Render latest data with correct lock state
    renderBudgetBreakdown();

    // Focus on Category Name input field if budget is not locked
    const isLocked = currentSettings && currentSettings.is_budget_locked;
    if (!isLocked && newCatName) {
        setTimeout(() => {
            newCatName.focus();
        }, 50);
    }
}


// Profile Settings Frontend Controllers
function setupProfileHandlers() {
    const profileForm = document.getElementById("profile-info-form");
    if (profileForm) {
        profileForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const first_name = document.getElementById("profile-first-name").value.trim();
            const last_name = document.getElementById("profile-last-name").value.trim();
            const email = document.getElementById("profile-email").value.trim();
            const bio = document.getElementById("profile-bio").value.trim();
            
            if (!first_name || !last_name || !email) {
                alert("First Name, Last Name, and Email are required and cannot be empty.");
                return;
            }
            
            try {
                const res = await fetch("/api/profile", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ first_name, last_name, email, bio })
                });
                if (res.status === 401) return showAuthScreen();
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Failed to update profile.");
                alert("Profile details saved successfully!");
                fetchProfile();
            } catch (err) {
                alert(err.message || "Failed to save profile.");
            }
        });
    }

    const passwordForm = document.getElementById("profile-password-form");
    if (passwordForm) {
        passwordForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const current_password = document.getElementById("pwd-current").value;
            const new_password = document.getElementById("pwd-new").value;
            const confirm_password = document.getElementById("pwd-confirm").value;
            
            if (new_password !== confirm_password) {
                alert("New password and confirm password do not match.");
                return;
            }
            if (new_password.length < 8) {
                alert("New password must be at least 8 characters long.");
                return;
            }
            
            try {
                const res = await fetch("/api/profile/password", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ current_password, new_password })
                });
                if (res.status === 401) return showAuthScreen();
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Failed to update password.");
                alert("Password updated successfully!");
                passwordForm.reset();
            } catch (err) {
                alert(err.message || "Failed to update password.");
            }
        });
    }

    const avatarInput = document.getElementById("avatar-input");
    if (avatarInput) {
        avatarInput.addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            if (file.size > 2 * 1024 * 1024) {
                alert("File size must be less than 2MB.");
                return;
            }
            
            const formData = new FormData();
            formData.append("file", file);
            
            try {
                const res = await fetch("/api/profile/avatar", {
                    method: "POST",
                    body: formData
                });
                if (res.status === 401) return showAuthScreen();
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Avatar upload failed.");
                alert("Avatar updated successfully!");
                fetchProfile();
            } catch (err) {
                alert(err.message || "Failed to upload avatar.");
            }
        });
    }



    const notifToggle = document.getElementById("notifications-toggle");
    if (notifToggle) {
        notifToggle.addEventListener("change", async () => {
            const enabled = notifToggle.checked;
            try {
                const res = await fetch("/api/profile", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ notifications_enabled: enabled })
                });
                if (res.status === 401) return showAuthScreen();
            } catch (err) {
                console.error(err);
            }
        });
    }

    const revokeOthersBtn = document.getElementById("revoke-other-sessions-btn");
    if (revokeOthersBtn) {
        revokeOthersBtn.addEventListener("click", async () => {
            if (!confirm("Are you sure you want to log out of all other devices?")) return;
            try {
                const res = await fetch("/api/profile/sessions/other", {
                    method: "DELETE"
                });
                if (res.status === 401) return showAuthScreen();
                if (res.ok) {
                    alert("Successfully logged out of other devices.");
                    fetchSessions();
                }
            } catch (err) {
                console.error(err);
            }
        });
    }

    const openDeactivateBtn = document.getElementById("open-deactivate-modal-btn");
    const deactivateModal = document.getElementById("deactivate-modal");
    const closeDeactivateBtn = document.getElementById("close-deactivate-btn");
    const deactivateForm = document.getElementById("deactivate-form");
    
    if (openDeactivateBtn) {
        openDeactivateBtn.addEventListener("click", () => {
            if (deactivateModal) {
                document.getElementById("deactivate-confirm-phrase").value = "";
                document.getElementById("deactivate-password").value = "";
                deactivateModal.classList.add("active");
            }
        });
    }
    if (closeDeactivateBtn) {
        closeDeactivateBtn.addEventListener("click", () => {
            if (deactivateModal) deactivateModal.classList.remove("active");
        });
    }
    if (deactivateForm) {
        deactivateForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const confirmation = document.getElementById("deactivate-confirm-phrase").value.trim();
            const password = document.getElementById("deactivate-password").value;
            
            if (confirmation !== "DELETE") {
                alert("Please type the confirmation phrase exactly: DELETE");
                return;
            }
            
            if (!confirm("This is your last warning! Are you absolutely sure you want to deactivate and permanently delete your account? This cannot be undone.")) {
                return;
            }
            
            try {
                const res = await fetch("/api/profile/deactivate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ password, confirmation })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Deactivation failed.");
                
                alert("Your account has been permanently deleted. Goodbye!");
                window.location.href = "/";
            } catch (err) {
                alert(err.message || "Failed to delete account.");
            }
        });
    }
}

async function fetchProfile() {
    try {
        const res = await fetch("/api/profile");
        if (res.status === 401) return showAuthScreen();
        const profile = await res.json();
        
        document.getElementById("profile-first-name").value = profile.first_name || "";
        document.getElementById("profile-last-name").value = profile.last_name || "";
        document.getElementById("profile-email").value = profile.email || "";
        document.getElementById("profile-bio").value = profile.bio || "";
        document.getElementById("notifications-toggle").checked = !!profile.notifications_enabled;
        
        setTheme(profile.theme || "dark");
        
        const avatarImg = document.getElementById("profile-avatar-img");
        const avatarPlaceholder = document.getElementById("profile-avatar-placeholder");
        const headerAvatar = document.getElementById("user-avatar");
        const headerIcon = document.getElementById("user-icon");

        // --- Dashboard profile mini-card ---
        const dashName = document.getElementById("dash-profile-name");
        const dashPhone = document.getElementById("dash-profile-phone");
        const dashEmail = document.getElementById("dash-profile-email");
        const dashInitials = document.getElementById("dash-profile-initials");
        const dashAvatarImg = document.getElementById("dash-profile-avatar-img");

        const firstName = profile.first_name || "";
        const lastName = profile.last_name || "";
        const fullName = [firstName, lastName].filter(Boolean).join(" ");

        if (dashName) dashName.textContent = fullName || profile.phone_number || "—";
        const payoutDisplay = profile.payout_phone_number || profile.phone_number;
        if (dashPhone) dashPhone.textContent = payoutDisplay || "—";
        if (dashEmail) dashEmail.textContent = profile.email || "No email set";
        if (dashInitials) {
            const initials = [firstName[0], lastName[0]].filter(Boolean).join("").toUpperCase();
            dashInitials.textContent = initials || (profile.phone_number ? profile.phone_number.slice(-2) : "?");
        }
        // --- End dashboard mini-card ---
        
        if (profile.avatar_url) {
            const cacheBuster = `${profile.avatar_url}?v=${Date.now()}`;
            if (avatarImg) {
                avatarImg.src = cacheBuster;
                avatarImg.style.display = "block";
            }
            if (avatarPlaceholder) avatarPlaceholder.style.display = "none";
            
            if (headerAvatar) {
                headerAvatar.src = cacheBuster;
                headerAvatar.style.display = "block";
            }
            if (headerIcon) headerIcon.style.display = "none";

            // Dashboard mini-card: show avatar photo
            if (dashAvatarImg) {
                dashAvatarImg.src = cacheBuster;
                dashAvatarImg.style.display = "block";
            }
            if (dashInitials) dashInitials.style.display = "none";
        } else {
            if (avatarImg) {
                avatarImg.src = "";
                avatarImg.style.display = "none";
            }
            if (avatarPlaceholder) avatarPlaceholder.style.display = "flex";
            
            if (headerAvatar) {
                headerAvatar.src = "";
                headerAvatar.style.display = "none";
            }
            if (headerIcon) headerIcon.style.display = "block";

            // Dashboard mini-card: show initials
            if (dashAvatarImg) {
                dashAvatarImg.src = "";
                dashAvatarImg.style.display = "none";
            }
            if (dashInitials) dashInitials.style.display = "block";
        }
        if (window.lucide) {
            window.lucide.createIcons();
        }
    } catch (err) {
        console.error("Error fetching profile:", err);
    }
}

async function fetchSessions() {
    try {
        const res = await fetch("/api/profile/sessions");
        if (res.status === 401) return showAuthScreen();
        const sessions = await res.json();
        
        const tbody = document.getElementById("active-sessions-body");
        if (!tbody) return;
        
        if (sessions.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No active sessions.</td></tr>`;
            return;
        }
        
        tbody.innerHTML = sessions.map(s => {
            const actionBtn = s.is_current 
                ? `<span class="text-muted" style="font-size: 0.85rem; font-weight:600;">Current Session</span>`
                : `<button type="button" class="btn btn-secondary btn-sm revoke-session-btn" data-session-id="${escapeHTML(String(s.id))}" style="padding: 0.35rem 0.6rem; font-size: 0.75rem; color: var(--color-accent-rose); border-color: rgba(239, 68, 68, 0.2);">Revoke</button>`;
                
            return `
                <tr>
                    <td data-label="Device"><strong>${escapeHTML(s.device || '')}</strong></td>
                    <td data-label="IP Address">${escapeHTML(s.ip_address || '')}</td>
                    <td data-label="Login Time">${escapeHTML(s.created_at || '')}</td>
                    <td data-label="Action">${actionBtn}</td>
                </tr>
            `;
        }).join("");
        
        tbody.querySelectorAll(".revoke-session-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                const sessionId = btn.getAttribute("data-session-id");
                if (!confirm("Are you sure you want to revoke this session? The device will be logged out.")) return;
                
                try {
                    const revokeRes = await fetch(`/api/profile/sessions/${sessionId}`, {
                        method: "DELETE"
                    });
                    if (revokeRes.status === 401) return showAuthScreen();
                    if (revokeRes.ok) {
                        alert("Session revoked successfully.");
                        fetchSessions();
                    } else {
                        const errData = await revokeRes.json();
                        alert(errData.detail || "Failed to revoke session.");
                    }
                } catch (err) {
                    console.error(err);
                }
            });
        });
    } catch (err) {
        console.error("Error fetching sessions:", err);
    }
}

function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", "dark");
}

// Global Password Visibility Toggle Event Delegation
document.addEventListener("click", (e) => {
    const btn = e.target.closest(".btn-toggle-password");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();

    const targetId = btn.getAttribute("data-target");
    const input = targetId ? document.getElementById(targetId) : btn.previousElementSibling;
    if (!input) return;

    if (input.type === "password") {
        input.type = "text";
        btn.innerHTML = `<i data-lucide="eye-off"></i>`;
    } else {
        input.type = "password";
        btn.innerHTML = `<i data-lucide="eye"></i>`;
    }
    if (window.lucide && window.lucide.createIcons) {
        window.lucide.createIcons();
    }
});

// ==========================================
// Cash Withdrawal & 2FA Flow
// ==========================================
let withdrawPendingData = {
    amount: 0,
    payout_phone_number: ""
};
let withdrawOtpCooldownTimer = null;

function setupWithdrawalHandlers() {
    const openWithdrawBtn = document.getElementById("open-withdraw-btn");
    const withdrawModal = document.getElementById("withdraw-modal");
    const closeWithdrawBtn = document.getElementById("close-withdraw-btn");
    const cancelWithdrawBtn = document.getElementById("cancel-withdraw-btn");
    const withdrawForm = document.getElementById("withdraw-form");
    const withdrawAmountInput = document.getElementById("withdraw-amount-input");
    const withdrawModalError = document.getElementById("withdraw-modal-error");
    const withdrawAvailableBal = document.getElementById("withdraw-available-bal");
    const withdrawDestPhone = document.getElementById("withdraw-dest-phone");
    const proceedWithdrawBtn = document.getElementById("proceed-withdraw-btn");

    const withdraw2faModal = document.getElementById("withdraw-2fa-modal");
    const closeWithdraw2faBtn = document.getElementById("close-withdraw-2fa-btn");
    const backWithdraw2faBtn = document.getElementById("back-withdraw-2fa-btn");
    const withdraw2faForm = document.getElementById("withdraw-2fa-form");
    const withdrawConfirmAmount = document.getElementById("withdraw-confirm-amount");
    const withdrawConfirmDest = document.getElementById("withdraw-confirm-dest");
    const withdrawAuthPassword = document.getElementById("withdraw-auth-password");
    const withdrawAuthOtp = document.getElementById("withdraw-auth-otp");
    const withdraw2faError = document.getElementById("withdraw-2fa-error");
    const confirmWithdrawSubmitBtn = document.getElementById("confirm-withdraw-submit-btn");
    const resendWithdrawOtpBtn = document.getElementById("resend-withdraw-otp-btn");

    // Open Initial Withdrawal Modal
    if (openWithdrawBtn) {
        openWithdrawBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            if (withdrawModalError) withdrawModalError.style.display = "none";
            if (withdrawAmountInput) withdrawAmountInput.value = "";

            // Check if user has an email
            try {
                const profileRes = await fetch("/api/profile");
                if (profileRes.status === 401) return showAuthScreen();
                const profile = await profileRes.json();
                if (!profile.email) {
                    alert("Please link and verify an email address in Profile Settings before withdrawing cash.");
                    switchTab("profile");
                    return;
                }
                const currentBal = parseFloat(currentSettings.balance || 0);
                if (withdrawAvailableBal) withdrawAvailableBal.innerText = currentBal.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                const destPhone = profile.payout_phone_number || profile.phone_number || currentSettings.phone_number || "";
                if (withdrawDestPhone) withdrawDestPhone.innerText = destPhone || "N/A";
                withdrawPendingData.payout_phone_number = destPhone;

                if (withdrawModal) withdrawModal.classList.add("active");
                if (withdrawAmountInput) withdrawAmountInput.focus();
            } catch (err) {
                console.error("Error preparing withdrawal modal:", err);
            }
        });
    }

    // Quick chip buttons
    document.querySelectorAll(".btn-quick-withdraw").forEach(btn => {
        btn.addEventListener("click", () => {
            const amt = parseInt(btn.getAttribute("data-amt"), 10);
            if (withdrawAmountInput) withdrawAmountInput.value = amt;
        });
    });

    const btnWithdrawMax = document.getElementById("btn-withdraw-max");
    if (btnWithdrawMax) {
        btnWithdrawMax.addEventListener("click", () => {
            const maxAmt = Math.floor(parseFloat(currentSettings.balance || 0));
            if (withdrawAmountInput) withdrawAmountInput.value = maxAmt;
        });
    }

    // Close Withdrawal Modal
    function closeWithdrawModal() {
        if (withdrawModal) withdrawModal.classList.remove("active");
        if (withdrawModalError) withdrawModalError.style.display = "none";
    }

    if (closeWithdrawBtn) closeWithdrawBtn.addEventListener("click", closeWithdrawModal);
    if (cancelWithdrawBtn) cancelWithdrawBtn.addEventListener("click", closeWithdrawModal);

    // Proceed from Amount to 2FA Confirmation Modal
    if (withdrawForm) {
        withdrawForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (withdrawModalError) withdrawModalError.style.display = "none";

            const rawVal = withdrawAmountInput.value.trim();
            const amount = parseInt(rawVal, 10);
            const currentBal = parseFloat(currentSettings.balance || 0);

            if (!rawVal || isNaN(amount) || amount < 10 || amount > 250000) {
                if (withdrawModalError) {
                    withdrawModalError.innerText = "Please enter a valid whole integer amount between KES 10 and KES 250,000.";
                    withdrawModalError.style.display = "block";
                }
                return;
            }

            if (amount > currentBal) {
                if (withdrawModalError) {
                    withdrawModalError.innerText = `Insufficient balance. You have KES ${currentBal.toFixed(2)} available.`;
                    withdrawModalError.style.display = "block";
                }
                return;
            }

            withdrawPendingData.amount = amount;

            // Trigger Pre-OTP dispatch
            if (proceedWithdrawBtn) {
                proceedWithdrawBtn.disabled = true;
                proceedWithdrawBtn.innerHTML = `<span class="spinner-sm"></span> Sending Code...`;
            }

            try {
                const otpRes = await fetch("/api/profile/request-stepup-otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        purpose: "wallet_withdrawal",
                        amount: amount
                    })
                });
                const otpData = await otpRes.json();
                if (!otpRes.ok) throw new Error(otpData.detail || "Failed to dispatch verification code.");

                // Switch modals
                closeWithdrawModal();
                if (withdrawConfirmAmount) withdrawConfirmAmount.innerText = amount.toLocaleString("en-US");
                if (withdrawConfirmDest) withdrawConfirmDest.innerText = withdrawPendingData.payout_phone_number;
                if (withdrawAuthPassword) withdrawAuthPassword.value = "";
                if (withdrawAuthOtp) withdrawAuthOtp.value = "";
                if (withdraw2faError) withdraw2faError.style.display = "none";

                if (withdraw2faModal) withdraw2faModal.classList.add("active");
                if (withdrawAuthPassword) withdrawAuthPassword.focus();

                startWithdrawOtpCooldown();
            } catch (err) {
                if (withdrawModalError) {
                    withdrawModalError.innerText = err.message || "Failed to initiate withdrawal.";
                    withdrawModalError.style.display = "block";
                }
            } finally {
                if (proceedWithdrawBtn) {
                    proceedWithdrawBtn.disabled = false;
                    proceedWithdrawBtn.innerHTML = `<i data-lucide="arrow-up-right" style="width: 1rem; height: 1rem;"></i> Continue to 2FA`;
                    if (window.lucide) window.lucide.createIcons();
                }
            }
        });
    }

    // Close 2FA Modal
    function closeWithdraw2faModal() {
        if (withdraw2faModal) withdraw2faModal.classList.remove("active");
        if (withdraw2faError) withdraw2faError.style.display = "none";
    }

    if (closeWithdraw2faBtn) closeWithdraw2faBtn.addEventListener("click", closeWithdraw2faModal);
    if (backWithdraw2faBtn) {
        backWithdraw2faBtn.addEventListener("click", () => {
            closeWithdraw2faModal();
            if (withdrawModal) withdrawModal.classList.add("active");
        });
    }

    // Resend OTP in 2FA Modal
    if (resendWithdrawOtpBtn) {
        resendWithdrawOtpBtn.addEventListener("click", async () => {
            if (resendWithdrawOtpBtn.disabled) return;
            try {
                resendWithdrawOtpBtn.innerText = "Sending...";
                const res = await fetch("/api/profile/request-stepup-otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        purpose: "wallet_withdrawal",
                        amount: withdrawPendingData.amount
                    })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Failed to resend code.");
                startWithdrawOtpCooldown();
            } catch (err) {
                if (withdraw2faError) {
                    withdraw2faError.innerText = err.message || "Failed to resend code.";
                    withdraw2faError.style.display = "block";
                }
                resendWithdrawOtpBtn.innerText = "Resend Code";
            }
        });
    }

    function startWithdrawOtpCooldown() {
        if (!resendWithdrawOtpBtn) return;
        let seconds = 30;
        resendWithdrawOtpBtn.disabled = true;
        resendWithdrawOtpBtn.innerText = `Resend in ${seconds}s`;
        if (withdrawOtpCooldownTimer) clearInterval(withdrawOtpCooldownTimer);
        withdrawOtpCooldownTimer = setInterval(() => {
            seconds--;
            if (seconds <= 0) {
                clearInterval(withdrawOtpCooldownTimer);
                resendWithdrawOtpBtn.disabled = false;
                resendWithdrawOtpBtn.innerText = "Resend Code";
            } else {
                resendWithdrawOtpBtn.innerText = `Resend in ${seconds}s`;
            }
        }, 1000);
    }

    // Submit 2FA and Execute Withdrawal
    if (withdraw2faForm) {
        withdraw2faForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (withdraw2faError) withdraw2faError.style.display = "none";

            const password = withdrawAuthPassword.value;
            const otpCode = withdrawAuthOtp.value.trim();

            if (!password) {
                if (withdraw2faError) {
                    withdraw2faError.innerText = "Please enter your password.";
                    withdraw2faError.style.display = "block";
                }
                return;
            }

            if (!/^[0-9]{6}$/.test(otpCode)) {
                if (withdraw2faError) {
                    withdraw2faError.innerText = "Please enter a valid 6-digit numeric OTP code.";
                    withdraw2faError.style.display = "block";
                }
                return;
            }

            if (confirmWithdrawSubmitBtn) {
                confirmWithdrawSubmitBtn.disabled = true;
                confirmWithdrawSubmitBtn.innerHTML = `<span class="spinner-sm"></span> Processing Withdrawal...`;
            }

            try {
                const idempotencyKey = "wd_" + Date.now() + "_" + Math.random().toString(36).substring(2, 9);
                const res = await fetch("/api/wallet/withdraw", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Idempotency-Key": idempotencyKey
                    },
                    body: JSON.stringify({
                        amount: withdrawPendingData.amount,
                        password: password,
                        otp_code: otpCode,
                        payout_phone_number: withdrawPendingData.payout_phone_number
                    })
                });

                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Withdrawal failed.");

                closeWithdraw2faModal();
                alert(`✅ Withdrawal Successful!\nKES ${withdrawPendingData.amount.toLocaleString()} has been sent to ${withdrawPendingData.payout_phone_number}.`);
                
                fetchSettings();
                fetchPayouts();
                fetchProfile();
            } catch (err) {
                if (withdraw2faError) {
                    withdraw2faError.innerText = err.message || "Failed to process withdrawal.";
                    withdraw2faError.style.display = "block";
                }
            } finally {
                if (confirmWithdrawSubmitBtn) {
                    confirmWithdrawSubmitBtn.disabled = false;
                    confirmWithdrawSubmitBtn.innerHTML = `<i data-lucide="send" style="width: 1rem; height: 1rem;"></i> Confirm & Withdraw`;
                    if (window.lucide) window.lucide.createIcons();
                }
            }
        });
    }
}

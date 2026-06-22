// Bursar 2.0 Client App Logic (Multi-Tenant Auth Edition)

// Global State
let currentSettings = {};
let currentPayouts = [];
let budgetItems = [];
let countdownInterval = null;
let pollInterval = null;
let currentAuthAction = "login"; // "login" or "signup"
let isAuthenticated = false;
let balanceChartInstance = null;

document.addEventListener("DOMContentLoaded", () => {
    // Check initial authentication status
    checkAuth();

    // Setup Event Handlers
    setupEventHandlers();

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
    window.location.href = "/#login";
}

// Switch View — module-level so it's accessible from checkAuth(), event handlers, etc.
function switchTab(tabId) {
    // Update hash in URL
    if (window.location.hash.replace("#", "") !== tabId) {
        window.location.hash = tabId;
    }

    // Handle DOM re-parenting for Deposit
    const depositModal = document.getElementById("deposit-modal");
    const depositContent = depositModal ? depositModal.querySelector(".modal-content") : null;
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
    const settingsContent = settingsDrawer ? settingsDrawer.querySelector(".drawer-content") : null;
    const viewSettings = document.getElementById("view-settings");

    if (tabId === "settings") {
        if (settingsContent && viewSettings) {
            viewSettings.appendChild(settingsContent);
        }
        if (settingsDrawer) {
            settingsDrawer.classList.remove("active");
        }
    } else {
        // Return to drawer overlay if not on settings tab
        if (settingsContent && settingsDrawer && settingsContent.parentNode !== settingsDrawer) {
            settingsDrawer.appendChild(settingsContent);
        }
    }

    // Toggle view containers
    const allViews = ["dashboard", "transactions", "profile", "deposit", "budget", "settings"];
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
            if (tab === "dashboard" || tab === "transactions" || tab === "profile" || tab === "deposit" || tab === "budget" || tab === "settings") {
                switchTab(tab);
            }
        });
    });

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
        const depositContent = depositModal ? depositModal.querySelector(".modal-content") : null;
        if (depositModal && depositContent && depositContent.parentNode !== depositModal) {
            depositModal.appendChild(depositContent);
        }

        const depositAmt = document.getElementById("deposit-amount");
        if (depositAmt) depositAmt.value = "";
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
        const settingsContent = settingsDrawer ? settingsDrawer.querySelector(".drawer-content") : null;
        if (settingsContent && settingsContent.parentNode === settingsDrawer) {
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
        if (isNaN(amount) || amount <= 0) return;

        try {
            const res = await fetch("/api/deposit/initiate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ amount })
            });
            if (res.status === 401) return showAuthScreen();
            
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
        const phone_number = document.getElementById("settings-phone").value;
        
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
            // When in flat tab mode, drawer-content is parented to #view-settings (not settingsDrawer)
            const viewSettings = document.getElementById("view-settings");
            const inFlatTabMode = viewSettings && !viewSettings.classList.contains("hidden") && viewSettings.classList.contains("active");
            if (inFlatTabMode) {
                // Flat tab mode: navigate back to dashboard after save
                switchTab("dashboard");
            } else {
                // Drawer mode: close the drawer
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

    if (tabLogin) {
        tabLogin.addEventListener("click", () => {
            currentAuthAction = "login";
            tabLogin.classList.add("active");
            if (tabSignup) tabSignup.classList.remove("active");
            if (authSubmitBtn) authSubmitBtn.innerText = "Log In";
            if (authSubtitle) authSubtitle.innerText = "Log in to manage your daily allowances";
            if (passwordLabel) passwordLabel.innerText = "Password PIN";
            if (authPassword) authPassword.placeholder = "Enter password (min 4 chars)";
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
            if (passwordLabel) passwordLabel.innerText = "Create Password PIN";
            if (authPassword) authPassword.placeholder = "Choose password (min 4 chars)";
            if (errorMsg) errorMsg.style.display = "none";
        });
    }

    if (authForm) {
        authForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (errorMsg) errorMsg.style.display = "none";

            const phone_number = document.getElementById("auth-phone").value.trim();
            const password = authPassword ? authPassword.value : "";

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
                    if (tabLogin) tabLogin.click();
                    const pwdEl = document.getElementById("auth-password");
                    if (pwdEl) pwdEl.value = password;
                    authForm.dispatchEvent(new Event("submit"));
                } else {
                    // Login succeeded
                    const phoneEl = document.getElementById("auth-phone");
                    if (phoneEl) phoneEl.value = "";
                    if (authPassword) authPassword.value = "";
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
    const handleLogout = async () => {
        try {
            await fetch("/api/auth/logout", { method: "POST" });
            window.location.href = "/";
        } catch (err) {
            console.error("Logout failed:", err);
            window.location.href = "/";
        }
    };
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

    // Budget Designer Modal Handlers
    const budgetDesignerModal = document.getElementById("budget-designer-modal");
    
    document.getElementById("open-budget-designer-btn").addEventListener("click", () => {
        openBudgetDesignerModal();
    });
    
    document.getElementById("close-budget-designer-btn").addEventListener("click", () => {
        budgetDesignerModal.classList.remove("active");
    });
    
    budgetDesignerModal.addEventListener("click", (e) => {
        if (e.target === budgetDesignerModal) budgetDesignerModal.classList.remove("active");
    });
    
    // Add Category Form Submit
    document.getElementById("add-category-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const category = document.getElementById("new-category-name").value.trim();
        const amount = parseFloat(document.getElementById("new-category-amount").value);
        if (!category || isNaN(amount) || amount <= 0) return;
        
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
            
            pollDashboardData();
            // Refocus Category Name input field
            const newCatName = document.getElementById("new-category-name");
            if (newCatName) newCatName.focus();
        } catch (err) {
            console.error(err);
            alert(err.message || "Failed to save category.");
        }
    });

    const lockBudgetBtn = document.getElementById("lock-budget-btn");
    if (lockBudgetBtn) {
        lockBudgetBtn.addEventListener("click", async () => {
            const start_date = document.getElementById("lock-start-date").value || "";
            const end_date = document.getElementById("lock-end-date").value || "";
            
            if (!start_date || !end_date) {
                alert("Please select both start and end dates for the payout schedule.");
                // Expand the collapsible section if it was closed
                const scheduleBody = document.getElementById("schedule-collapse-body");
                const scheduleChevron = document.getElementById("schedule-chevron");
                if (scheduleBody && scheduleBody.style.display === "none") {
                    scheduleBody.style.display = "block";
                    if (scheduleChevron) scheduleChevron.classList.add("expanded");
                }
                return;
            }

            if (budgetItems.length === 0) {
                alert("Cannot lock an empty budget. Please add budget items first.");
                return;
            }
            
            if (!confirm("Are you sure you want to finalize and lock your budget? Once locked, you cannot add or delete allocation categories until the first day of next month.")) {
                return;
            }
            
            try {
                const res = await fetch("/api/budget/lock", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ start_date, end_date })
                });
                if (res.status === 401) return showAuthScreen();
                if (!res.ok) {
                    const data = await res.json();
                    throw new Error(data.detail || "Failed to lock budget.");
                }
                alert("Budget successfully finalized and locked for this month! 🔒");
                
                // Close modal or switch back to dashboard if flat
                const budgetDesignerModal = document.getElementById("budget-designer-modal");
                const budgetContent = document.getElementById("budget-designer-modal-content");
                if (budgetContent && budgetDesignerModal && budgetContent.parentNode !== budgetDesignerModal) {
                    switchTab("dashboard");
                } else if (budgetDesignerModal) {
                    budgetDesignerModal.classList.remove("active");
                }
                
                pollDashboardData();
            } catch (err) {
                console.error(err);
                alert(err.message || "Failed to lock budget.");
            }
        });
    }

    // Manual Payout Daemon Trigger Handler
    const triggerPayoutBtn = document.getElementById("trigger-payout-btn");
    if (triggerPayoutBtn) {
        triggerPayoutBtn.addEventListener("click", async () => {
            triggerPayoutBtn.disabled = true;
            const originalHTML = triggerPayoutBtn.innerHTML;
            triggerPayoutBtn.innerHTML = `<i data-lucide="loader" class="spin" style="width: 1rem; height: 1rem; display: inline-block; vertical-align: middle;"></i> Evaluated...`;
            if (window.lucide) window.lucide.createIcons();
            
            try {
                const res = await fetch("/api/payout/trigger", { method: "POST" });
                if (res.status === 401) return showAuthScreen();
                const data = await res.json();
                
                if (data.triggered) {
                    alert("Daily allowance scheduled distribution run completed! 🚀");
                } else {
                    alert("Payout trigger evaluation completed. No payout due or daily limit already hit today.");
                }
                pollDashboardData();
            } catch (err) {
                console.error("Payout trigger error:", err);
                alert("Failed to manual trigger payout daemon.");
            } finally {
                triggerPayoutBtn.disabled = false;
                triggerPayoutBtn.innerHTML = originalHTML;
                if (window.lucide) window.lucide.createIcons();
            }
        });
    }

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
    setupProfileHandlers();
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

    const settingsBudgetInput = document.getElementById("settings-budget");
    if (settingsBudgetInput) {
        settingsBudgetInput.value = settings.daily_budget || 0;
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
    if (settings.is_budget_locked) {
        if (editBudgetBtn) editBudgetBtn.style.display = "none";
        if (budgetLockBadge) budgetLockBadge.style.display = "inline-flex";
    } else {
        if (editBudgetBtn) editBudgetBtn.style.display = "inline-flex";
        if (budgetLockBadge) budgetLockBadge.style.display = "none";
    }

    document.getElementById(`settings-time`).value = settings.payout_time || "08:00";
    document.getElementById(`settings-phone`).value = settings.phone_number || "";
}

// Fetch historical payout transaction rows
async function fetchPayouts() {
    try {
        const res = await fetch("/api/payouts");
        if (res.status === 401) return showAuthScreen();
        const data = await res.json();
        currentPayouts = data;
        
        document.getElementById("payout-count-badge").innerText = `${data.length} total`;

        const body = document.getElementById("payout-history-body");
        const bodyRecent = document.getElementById("payout-history-body-recent");
        
        if (data.length === 0) {
            const emptyHTML = `<tr><td colspan="5" class="empty-state">No transactions recorded yet.</td></tr>`;
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
                    tooltip = `title="${payout.error_message || 'Transaction rejected'}"`;
                }

                return `
                    <tr>
                        <td data-label="Date"><strong>${payout.payout_date}</strong></td>
                        <td data-label="Amount">KES ${parseFloat(payout.amount).toFixed(2)}</td>
                        <td data-label="Recipient">${payout.phone_number}</td>
                        <td data-label="M-Pesa Ref" class="text-mono">${payout.transaction_id || payout.conversation_id || '—'}</td>
                        <td data-label="Status"><span class="badge ${statusClass}" ${tooltip}>${statusText}</span></td>
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
    fetchBudgetItems();
}

// Fetch user's custom budget categories
async function fetchBudgetItems() {
    try {
        const res = await fetch("/api/budget/items");
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
                    <button class="icon-link-btn cancel-btn" onclick="deleteCategory(${item.id})" title="Delete allocation category">
                        <i data-lucide="trash-2" style="width: 1.1rem; height: 1.1rem;"></i>
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
    const lockDatesSection = document.getElementById("designer-lock-dates-section");

    if (isLocked) {
        if (lockNotice) {
            lockNotice.style.display = "flex";
            if (lockNoticeText) {
                let text = `<strong>Locked:</strong> Allocations are locked until the end of the month to prevent overspending.`;
                if (currentSettings.start_date || currentSettings.end_date) {
                    text += `<br><span style="display:inline-block; margin-top:0.25rem; font-size:0.75rem;"><i data-lucide="calendar" style="width:0.85rem; height:0.85rem; vertical-align:middle; margin-right:0.15rem; display:inline-block;"></i> Payout schedule: <strong>${currentSettings.start_date || 'immediate'}</strong> to <strong>${currentSettings.end_date || 'indefinite'}</strong></span>`;
                }
                lockNoticeText.innerHTML = text;
                if (window.lucide) {
                    window.lucide.createIcons();
                }
            }
        }
        if (lockBtn) lockBtn.style.display = "none";
        if (lockDatesSection) lockDatesSection.style.display = "none";
        if (addForm) {
            const inputs = addForm.querySelectorAll("input, button");
            inputs.forEach(el => el.disabled = true);
        }
    } else {
        if (lockNotice) lockNotice.style.display = "none";
        if (addForm) {
            const inputs = addForm.querySelectorAll("input, button");
            inputs.forEach(el => el.disabled = false);
        }
        if (lockDatesSection) lockDatesSection.style.display = "flex";
        if (lockBtn) {
            // Only show lock button if we have items
            if (budgetItems.length > 0) {
                lockBtn.style.display = "block";
            } else {
                lockBtn.style.display = "none";
            }
        }
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
    
    if (!confirm("Are you sure you want to delete this category?")) return;
    
    try {
        const res = await fetch(`/api/budget/items/${itemId}`, { method: "DELETE" });
        if (res.status === 401) return showAuthScreen();
        if (!res.ok) throw new Error("Deletion failed");
        
        pollDashboardData();
    } catch (err) {
        console.error(err);
        alert("Failed to delete category.");
    }
}

// Attach to window so onclick attribute can bind successfully
window.deleteCategory = deleteCategory;

// Opens the Budget Creator modal and resets scroll positions & focus for optimal UX
function openBudgetDesignerModal() {
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

    const startDateInput = document.getElementById("lock-start-date");
    const endDateInput = document.getElementById("lock-end-date");
    if (startDateInput) startDateInput.value = currentSettings.start_date || "";
    if (endDateInput) endDateInput.value = currentSettings.end_date || "";
    
    // Reset collapsible schedule state to closed
    const collBody = document.getElementById("schedule-collapse-body");
    const collChevron = document.getElementById("schedule-chevron");
    if (collBody) collBody.style.display = "none";
    if (collChevron) collChevron.classList.remove("expanded");
    
    // Reset scroll positions of both the modal overlay and the inner designer body to 0
    budgetModal.scrollTop = 0;
    const designerBody = budgetModal.querySelector(".designer-body");
    if (designerBody) designerBody.scrollTop = 0;

    // Show modal
    budgetModal.classList.add("active");
    
    // Render latest data
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
                alert("New password PIN and confirm PIN do not match.");
                return;
            }
            if (new_password.length < 4) {
                alert("New password PIN must be at least 4 characters.");
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
                if (!res.ok) throw new Error(data.detail || "Failed to change password.");
                alert("Password PIN updated successfully!");
                passwordForm.reset();
            } catch (err) {
                alert(err.message || "Failed to change password.");
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
                : `<button type="button" class="btn btn-secondary btn-sm revoke-session-btn" data-session-id="${s.id}" style="padding: 0.35rem 0.6rem; font-size: 0.75rem; color: var(--color-accent-rose); border-color: rgba(239, 68, 68, 0.2);">Revoke</button>`;
                
            return `
                <tr>
                    <td data-label="Device"><strong>${s.device}</strong></td>
                    <td data-label="IP Address">${s.ip_address}</td>
                    <td data-label="Login Time">${s.created_at}</td>
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

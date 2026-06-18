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

    // Clean up chart
    if (balanceChartInstance) {
        balanceChartInstance.destroy();
        balanceChartInstance = null;
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
        } catch (err) {
            console.error(err);
            alert("Failed to deposit funds. Please check server logs.");
        }
    });

    // Settings Submit Form
    document.getElementById("settings-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const daily_budget = parseFloat(document.getElementById("settings-budget").value);
        const payout_time = document.getElementById("settings-time").value;
        const phone_number = document.getElementById("settings-phone").value;
        
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
            if (!res.ok) throw new Error("Saving settings failed.");
            
            settingsDrawer.classList.remove("active");
            pollDashboardData();
        } catch (err) {
            console.error(err);
            alert("Failed to save settings. Check inputs.");
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
        document.getElementById("new-category-name").value = "";
        document.getElementById("new-category-amount").value = "";
        const startDateInput = document.getElementById("lock-start-date");
        const endDateInput = document.getElementById("lock-end-date");
        if (startDateInput) startDateInput.value = currentSettings.start_date || "";
        if (endDateInput) endDateInput.value = currentSettings.end_date || "";
        budgetDesignerModal.classList.add("active");
        renderBudgetBreakdown();
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
        } catch (err) {
            console.error(err);
            alert(err.message || "Failed to save category.");
        }
    });

    // Lock Budget Button Handler
    const lockBudgetBtn = document.getElementById("lock-budget-btn");
    if (lockBudgetBtn) {
        lockBudgetBtn.addEventListener("click", async () => {
            if (!confirm("Are you sure you want to finalize and lock your budget? Once locked, you cannot add or delete allocation categories until the first day of next month.")) {
                return;
            }
            
            const start_date = document.getElementById("lock-start-date").value || "";
            const end_date = document.getElementById("lock-end-date").value || "";
            
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
                pollDashboardData();
            } catch (err) {
                console.error(err);
                alert(err.message || "Failed to lock budget.");
            }
        });
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
        document.getElementById("daily-budget-value").innerText = parseFloat(settings.daily_budget || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    
    document.getElementById("payout-time-info").innerText = `Payout at ${settings.payout_time || "08:00"} to ${settings.phone_number || "none"}`;

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
        if (data.length === 0) {
            body.innerHTML = `<tr><td colspan="5" class="empty-state">No payouts recorded yet.</td></tr>`;
            refreshChart();
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
        
        refreshChart();
    } catch (err) {
        console.error("Error fetching payouts:", err);
    }
}

// Calculate 7-day balance trend
function calculate7DayBalanceTrend(currentBalance, payouts) {
    const dates = [];
    const balances = new Array(7).fill(0);
    
    for (let i = 6; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        dates.push(`${yyyy}-${mm}-${dd}`);
    }
    
    const hasSuccessfulPayouts = payouts.some(p => p.status === "SUCCESS");
    
    if (!hasSuccessfulPayouts) {
        // Mock a pacing line based on daily budget
        const dailyBudget = currentSettings.daily_budget || 500;
        let runningBalance = currentBalance;
        if (currentBalance === 0) {
            runningBalance = dailyBudget * 3;
        }
        for (let i = 6; i >= 0; i--) {
            balances[i] = runningBalance;
            runningBalance += dailyBudget;
        }
    } else {
        // Group successful payouts by date
        const payoutsByDate = {};
        payouts.forEach(p => {
            if (p.status === "SUCCESS") {
                const dateKey = p.payout_date;
                payoutsByDate[dateKey] = (payoutsByDate[dateKey] || 0) + parseFloat(p.amount);
            }
        });
        
        let runningBalance = currentBalance;
        for (let i = 6; i >= 0; i--) {
            balances[i] = runningBalance;
            const dateStr = dates[i];
            if (payoutsByDate[dateStr]) {
                runningBalance += payoutsByDate[dateStr];
            }
        }
    }
    
    return { dates, balances };
}

// Render interactive Chart.js pacing area chart
function renderBalanceChart(payouts, settings) {
    const canvas = document.getElementById("balance-chart");
    if (!canvas) return;
    
    const { dates, balances } = calculate7DayBalanceTrend(settings.balance || 0, payouts);
    
    const formattedLabels = dates.map(dStr => {
        const parts = dStr.split('-');
        const d = new Date(parts[0], parts[1] - 1, parts[2]);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    
    const ctx = canvas.getContext("2d");
    
    if (balanceChartInstance) {
        balanceChartInstance.data.labels = formattedLabels;
        balanceChartInstance.data.datasets[0].data = balances;
        balanceChartInstance.update();
    } else {
        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, 'rgba(142, 68, 255, 0.25)'); // Violet accent glow
        gradient.addColorStop(1, 'rgba(59, 113, 254, 0.0)');   // Transparent indigo
        
        balanceChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: formattedLabels,
                datasets: [{
                    label: 'Wallet Balance',
                    data: balances,
                    borderColor: '#8e44ff',
                    borderWidth: 3,
                    pointBackgroundColor: '#3b71fe',
                    pointBorderColor: 'rgba(255, 255, 255, 0.8)',
                    pointHoverBackgroundColor: '#ffffff',
                    pointHoverBorderColor: '#8e44ff',
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    fill: true,
                    backgroundColor: gradient,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
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
                        displayColors: false,
                        callbacks: {
                            label: function(context) {
                                return 'Balance: KES ' + context.parsed.y.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.03)',
                            drawBorder: false
                        },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.5)',
                            font: {
                                family: 'Outfit',
                                size: 11
                            }
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.03)',
                            drawBorder: false
                        },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.5)',
                            font: {
                                family: 'Outfit',
                                size: 11
                            },
                            callback: function(value) {
                                return 'KES ' + value.toLocaleString();
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

// Render the breakdown pills in the Daily Budget card and inside the Budget Designer modal
function renderBudgetBreakdown() {
    const designerList = document.getElementById("designer-category-list");
    const designerTotal = document.getElementById("designer-total-budget");
    
    // Check lock states
    const isLocked = currentSettings && currentSettings.is_budget_locked;
    
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

/**
 * BURSAR 2.0 - ADMIN PORTAL SPA CLIENT
 * Core Architecture: SPA Hash Router, State Store, RBAC UI Guards, Inactivity Lifecycle, Chart.js Integrations
 */

(function () {
    "use strict";

    // Global State Store
    const state = {
        adminUser: null,
        currentRoute: "overview",
        sessionTimeoutSeconds: 15 * 60, // 15 minutes
        sessionRemainingSeconds: 15 * 60,
        sessionInterval: null,
        charts: {},
        pagination: {
            users: { page: 1, limit: 15, total: 0 },
            finances: { page: 1, limit: 15, total: 0 },
            deposits: { page: 1, limit: 15, total: 0 },
            payouts: { page: 1, limit: 15, total: 0 },
            audit: { page: 1, limit: 15, total: 0 }
        }
    };

    // =========================================================================
    // 1. API CLIENT & HTTP HELPERS
    // =========================================================================
    async function apiRequest(endpoint, options = {}) {
        const defaultHeaders = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        };

        const csrfToken = getCookie("csrf_token");
        if (csrfToken) {
            defaultHeaders["X-CSRF-Token"] = csrfToken;
        }

        const config = {
            ...options,
            headers: {
                ...defaultHeaders,
                ...(options.headers || {})
            },
            credentials: "include"
        };

        try {
            const response = await fetch(endpoint, config);

            // Handle 401 Unauthorized (session expired or unauthenticated)
            if (response.status === 401) {
                if (state.adminUser) {
                    showToast("Session expired. Please authenticate again.", "error");
                    handleLogout();
                }
                throw new Error("Unauthorized session");
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: "Network request failed" }));
                throw new Error(errorData.detail || `Request failed with status ${response.status}`);
            }

            return await response.json();
        } catch (err) {
            if (endpoint !== "/api/admin/auth/me" || state.adminUser) {
                console.error(`[API Error] ${endpoint}:`, err);
            }
            throw err;
        }
    }

    function getCookie(name) {
        const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
        return match ? decodeURIComponent(match[2]) : null;
    }

    // =========================================================================
    // 2. TOAST NOTIFICATIONS & UI HELPERS
    // =========================================================================
    function showToast(message, type = "info") {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        
        let iconName = "info";
        if (type === "success") iconName = "check-circle";
        if (type === "error") iconName = "alert-triangle";

        toast.innerHTML = `
            <i data-lucide="${iconName}"></i>
            <span>${escapeHtml(message)}</span>
        `;
        container.appendChild(toast);

        if (window.lucide) {
            window.lucide.createIcons({ root: toast });
        }

        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(20px)";
            toast.style.transition = "all 0.25s ease-in";
            setTimeout(() => toast.remove(), 250);
        }, 4000);
    }

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatCurrency(amount) {
        const val = parseFloat(amount) || 0;
        return "KES " + new Intl.NumberFormat("en-KE", { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(val);
    }

    function formatDate(dateStr) {
        if (!dateStr) return "-";
        try {
            const d = new Date(dateStr);
            return d.toLocaleString("en-KE", {
                year: "numeric",
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit"
            });
        } catch {
            return dateStr;
        }
    }

    // =========================================================================
    // 3. AUTHENTICATION & INACTIVITY SESSION MANAGER
    // =========================================================================
    async function checkAuthSession() {
        try {
            const data = await apiRequest("/api/admin/auth/me");
            const admin = data ? (data.admin || (data.email ? data : null)) : null;
            if (admin && admin.email) {
                state.adminUser = admin;
                onAuthenticated();
            } else {
                showLoginView();
            }
        } catch {
            showLoginView();
        }
    }

    function onAuthenticated() {
        document.getElementById("view-login").classList.add("hidden");
        document.getElementById("view-app").classList.remove("hidden");

        // Populate User Info
        document.getElementById("current-admin-email").textContent = state.adminUser.email;
        document.getElementById("current-admin-avatar").textContent = (state.adminUser.email[0] || "A").toUpperCase();
        
        const roleBadge = document.getElementById("current-admin-role");
        roleBadge.textContent = state.adminUser.role;
        roleBadge.className = `admin-role-badge badge-${state.adminUser.role.toLowerCase()}`;

        // Enforce RBAC UI Visibility
        applyRbacGuards();

        // Start Inactivity Timer
        startInactivityTimer();

        // Navigate to Initial Route
        handleRoute();

        if (window.lucide) {
            window.lucide.createIcons();
        }
    }

    function showLoginView() {
        state.adminUser = null;
        stopInactivityTimer();
        document.getElementById("view-app").classList.add("hidden");
        document.getElementById("view-login").classList.remove("hidden");
        if (window.lucide) window.lucide.createIcons();
    }

    function startInactivityTimer() {
        stopInactivityTimer();
        state.sessionRemainingSeconds = state.sessionTimeoutSeconds;
        updateTimerDisplay();

        state.sessionInterval = setInterval(() => {
            state.sessionRemainingSeconds--;
            updateTimerDisplay();

            if (state.sessionRemainingSeconds <= 0) {
                stopInactivityTimer();
                showToast("Session expired due to 15 minutes of inactivity.", "error");
                handleLogout();
            }
        }, 1000);

        // Reset timer on user interaction
        ["mousemove", "mousedown", "keypress", "touchstart", "scroll"].forEach(event => {
            window.addEventListener(event, resetInactivityTimer, { passive: true });
        });
    }

    function resetInactivityTimer() {
        state.sessionRemainingSeconds = state.sessionTimeoutSeconds;
    }

    function stopInactivityTimer() {
        if (state.sessionInterval) {
            clearInterval(state.sessionInterval);
            state.sessionInterval = null;
        }
    }

    function updateTimerDisplay() {
        const timerEl = document.getElementById("session-countdown-text");
        if (!timerEl) return;
        const mins = Math.floor(state.sessionRemainingSeconds / 60);
        const secs = state.sessionRemainingSeconds % 60;
        timerEl.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }

    async function handleLogout() {
        try {
            await apiRequest("/api/admin/auth/logout", { method: "POST" });
        } catch {
            // Ignore logout network error
        }
        showLoginView();
    }

    // =========================================================================
    // 4. RBAC UI GUARDS
    // =========================================================================
    function applyRbacGuards() {
        const role = state.adminUser ? state.adminUser.role : "";

        // SuperAdmin only elements
        document.querySelectorAll(".rbac-superadmin").forEach(el => {
            el.style.display = role === "superadmin" ? "" : "none";
        });

        // FinOps & SuperAdmin mutation elements
        document.querySelectorAll(".rbac-finops").forEach(el => {
            el.style.display = (role === "superadmin" || role === "finops") ? "" : "none";
        });

        // Support, FinOps & SuperAdmin mutation elements
        document.querySelectorAll(".rbac-support").forEach(el => {
            el.style.display = (role === "superadmin" || role === "support") ? "" : "none";
        });

        // If Auditor, hide mutation buttons
        if (role === "auditor") {
            document.querySelectorAll(".rbac-mutation").forEach(el => {
                el.style.display = "none";
            });
        }
    }

    // =========================================================================
    // 5. SPA HASH ROUTER
    // =========================================================================
    const routes = {
        "overview": { title: "Executive Overview", breadcrumb: "Dashboard / Overview", loader: loadOverviewData },
        "users": { title: "User 360 Explorer", breadcrumb: "Operations / Users", loader: loadUsersData },
        "finances": { title: "Finances & Wallets", breadcrumb: "Financial Control / Ledger", loader: loadWalletsData },
        "deposits": { title: "STK Push Deposits", breadcrumb: "Payment Pipeline / Deposits", loader: loadDepositsData },
        "payouts": { title: "B2C Disbursements", breadcrumb: "Payment Pipeline / Payouts", loader: loadPayoutsData },
        "audit": { title: "Audit Logs", breadcrumb: "Compliance / Audit Trail", loader: loadAuditLogsData },
        "system": { title: "System Health & Config", breadcrumb: "System / Runtime Health", loader: loadSystemHealthData }
    };

    function handleRoute() {
        if (!state.adminUser) return;

        let hash = window.location.hash.replace(/^#\/?/, "") || "overview";
        if (!routes[hash]) hash = "overview";

        state.currentRoute = hash;

        // Update Topbar
        const routeConfig = routes[hash];
        document.getElementById("topbar-page-title").textContent = routeConfig.title;
        document.getElementById("topbar-breadcrumb").textContent = routeConfig.breadcrumb;

        // Update Sidebar Active Links
        document.querySelectorAll(".sidebar-nav .nav-item").forEach(link => {
            link.classList.toggle("active", link.getAttribute("data-route") === hash);
        });

        // Update View Panes
        document.querySelectorAll(".view-pane").forEach(pane => {
            pane.classList.remove("active");
        });
        const activePane = document.getElementById(`pane-${hash}`);
        if (activePane) activePane.classList.add("active");

        // Execute Pane Loader
        routeConfig.loader();

        if (window.lucide) window.lucide.createIcons();
    }

    // =========================================================================
    // 6. VIEW DATA LOADERS & RENDERERS
    // =========================================================================

    // --- VIEW: OVERVIEW ---
    async function loadOverviewData() {
        try {
            const data = await apiRequest("/api/admin/overview");
            if (!data) return;

            const u = data.users || {};
            const fl = data.float || {};
            const q = data.queues || {};
            const pv = data.payout_velocity || {};

            // 1. KPIs
            const totalUsersCount = (u.total_registered_users || 0);
            document.getElementById("kpi-active-users").textContent = totalUsersCount.toLocaleString();
            document.getElementById("kpi-total-users").textContent = `${totalUsersCount.toLocaleString()} total registered (${u.active_locked_savers || 0} active savers)`;
            
            const platformFloat = fl.total_platform_float || fl.total_user_balance || 0;
            const lockedBalance = fl.total_locked_funds || 0;
            document.getElementById("kpi-platform-float").textContent = formatCurrency(platformFloat);
            document.getElementById("kpi-locked-deposits").textContent = `${formatCurrency(lockedBalance)} locked in active savings`;

            const todayDepAmount = fl.total_deposited_all_time || 0;
            document.getElementById("kpi-today-deposits").textContent = formatCurrency(todayDepAmount);
            document.getElementById("kpi-today-deposit-count").textContent = `${q.pending_deposits_count || 0} pending STK reconciliation`;

            const todayDisbAmount = pv.today_disbursed_amount || 0;
            document.getElementById("kpi-today-disbursed").textContent = formatCurrency(todayDisbAmount);
            document.getElementById("kpi-today-payout-count").textContent = `${pv.today_disbursed_count || 0} daily budget disbursements today`;

            // 2. Alerts
            const failedPayouts = q.failed_payouts_count || 0;
            const lockedUsers = u.locked_out_users || 0;
            document.getElementById("alert-failed-payouts-title").textContent = `Failed Payouts: ${failedPayouts}`;
            document.getElementById("alert-locked-users-title").textContent = `Locked Out Users: ${lockedUsers}`;

            // 3. Sidebar Badges
            document.getElementById("badge-users-count").textContent = totalUsersCount;
            const depBadge = document.getElementById("badge-pending-deposits");
            if (q.pending_deposits_count > 0) {
                depBadge.textContent = q.pending_deposits_count;
                depBadge.style.display = "";
            } else {
                depBadge.style.display = "none";
            }

            const payBadge = document.getElementById("badge-failed-payouts");
            if (failedPayouts > 0) {
                payBadge.textContent = failedPayouts;
                payBadge.style.display = "";
            } else {
                payBadge.style.display = "none";
            }

            // 4. Render Charts
            renderOverviewCharts(data);
        } catch (err) {
            console.error("Failed to load overview metrics:", err);
            showToast("Failed to load overview metrics", "error");
        }
    }

    function renderOverviewCharts(data) {
        if (!window.Chart) return;

        const fl = data.float || {};
        const q = data.queues || {};
        const pv = data.payout_velocity || {};

        // Chart 1: Platform Float Allocation (Donut Chart)
        const ctxFloat = document.getElementById("chart-float-distribution");
        if (ctxFloat) {
            if (state.charts.float) state.charts.float.destroy();
            const avail = fl.total_user_balance || 0;
            const locked = fl.total_locked_funds || 0;
            const hasData = (avail + locked) > 0;

            state.charts.float = new window.Chart(ctxFloat, {
                type: "doughnut",
                data: {
                    labels: hasData ? ["Available Liquidity", "Locked Savings"] : ["No Platform Float"],
                    datasets: [{
                        data: hasData ? [avail, locked] : [1],
                        backgroundColor: hasData ? ["#3b82f6", "#8b5cf6"] : ["rgba(255, 255, 255, 0.1)"],
                        borderWidth: 0,
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "bottom", labels: { color: "#9ca3af", font: { family: "Inter", size: 12 } } },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    if (!hasData) return " No platform float recorded yet";
                                    return ` ${context.label}: ${formatCurrency(context.raw)}`;
                                }
                            }
                        }
                    },
                    cutout: "68%"
                }
            });
        }

        // Chart 2: 7-Day Cashflow Velocity (Line Chart)
        const ctxVelocity = document.getElementById("chart-cashflow-velocity");
        if (ctxVelocity) {
            if (state.charts.velocity) state.charts.velocity.destroy();
            const todayDep = fl.total_deposited_all_time || 0;
            const todayDisb = pv.today_disbursed_amount || 0;
            const days = ["6d ago", "5d ago", "4d ago", "3d ago", "2d ago", "Yesterday", "Today"];

            state.charts.velocity = new window.Chart(ctxVelocity, {
                type: "line",
                data: {
                    labels: days,
                    datasets: [
                        {
                            label: "Deposits (Inflow)",
                            data: [0, 0, 0, 0, 0, 0, todayDep],
                            borderColor: "#10b981",
                            backgroundColor: "rgba(16, 185, 129, 0.12)",
                            fill: true,
                            tension: 0.35,
                            pointBackgroundColor: "#10b981",
                            pointRadius: 4
                        },
                        {
                            label: "Disbursements (Outflow)",
                            data: [0, 0, 0, 0, 0, 0, todayDisb],
                            borderColor: "#f59e0b",
                            backgroundColor: "rgba(245, 158, 11, 0.12)",
                            fill: true,
                            tension: 0.35,
                            pointBackgroundColor: "#f59e0b",
                            pointRadius: 4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "bottom", labels: { color: "#9ca3af", font: { family: "Inter", size: 12 } } },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return ` ${context.dataset.label}: ${formatCurrency(context.raw)}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: { ticks: { color: "#9ca3af" }, grid: { color: "rgba(255,255,255,0.05)" } },
                        y: { 
                            ticks: { 
                                color: "#9ca3af",
                                callback: function(val) { return "KES " + val; }
                            }, 
                            grid: { color: "rgba(255,255,255,0.05)" } 
                        }
                    }
                }
            });
        }
    }

    // --- VIEW: USERS 360 ---
    let usersSearchDebounceTimer = null;

    async function loadUsersData() {
        const tbody = document.getElementById("users-table-body");
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-8">Fetching customer records...</td></tr>`;

        const search = document.getElementById("users-search-input") ? document.getElementById("users-search-input").value.trim() : "";
        const status = document.getElementById("users-status-filter") ? document.getElementById("users-status-filter").value : "";
        const page = state.pagination.users.page;

        let query = `/api/admin/users?page=${page}&limit=${state.pagination.users.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;
        if (status) query += `&status_filter=${encodeURIComponent(status)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.users.total = data.total;

            if (!data.users || data.users.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-8">No customer accounts match your filter criteria.</td></tr>`;
                updatePaginationInfo("users");
                return;
            }

            tbody.innerHTML = data.users.map(u => {
                const displayName = (u.first_name || u.last_name) 
                    ? `${u.first_name || ''} ${u.last_name || ''}`.trim()
                    : (u.email || `User #${u.id}`);
                const isLockedOut = u.is_locked_out || (u.failed_login_attempts >= 5);
                const isDepositLocked = u.is_deposit_locked;
                const isBudgetLocked = u.is_budget_locked;

                return `
                <tr data-user-id="${u.id}">
                    <td>
                        <div class="user-cell">
                            <strong>${escapeHtml(displayName)}</strong>
                            <div class="text-dim text-xs">${escapeHtml(u.email || '')} <span class="badge-neutral text-xs">#${u.id}</span></div>
                        </div>
                    </td>
                    <td>
                        <span class="font-mono">${escapeHtml(u.phone_number || u.payout_phone_number || '-')}</span>
                        ${u.payout_phone_number && u.payout_phone_number !== u.phone_number ? `<div class="text-xs text-dim">Payout: ${escapeHtml(u.payout_phone_number)}</div>` : ''}
                    </td>
                    <td><strong class="text-emerald font-mono">${formatCurrency(u.balance || 0)}</strong></td>
                    <td><span class="font-mono">${formatCurrency(u.daily_budget || 0)}</span> <span class="text-xs text-muted">/day</span></td>
                    <td>
                        ${isLockedOut 
                            ? `<span class="status-pill pill-danger"><i data-lucide="lock"></i> Locked Out</span>` 
                            : `<span class="status-pill pill-success"><i data-lucide="check"></i> Active</span>`}
                        ${isBudgetLocked ? `<span class="status-pill pill-warning ml-1">Budget Lock</span>` : ''}
                        ${isDepositLocked ? `<span class="status-pill pill-warning ml-1">Deposit Lock</span>` : ''}
                        ${u.two_factor_enabled ? `<span class="status-pill pill-info ml-1">2FA</span>` : ''}
                    </td>
                    <td>
                        <div class="btn-group">
                            <button class="btn btn-secondary btn-sm btn-inspect-user" data-user-id="${u.id}">
                                <i data-lucide="eye"></i> Inspect 360°
                            </button>
                            <button class="btn btn-secondary btn-sm btn-notify-user" data-user-id="${u.id}" data-email="${escapeHtml(u.email || displayName)}" title="Send In-App Notification">
                                <i data-lucide="bell"></i>
                            </button>
                            ${isLockedOut ? `
                            <button class="btn btn-danger btn-sm btn-unlock-user rbac-support" data-user-id="${u.id}" title="Unlock Account">
                                <i data-lucide="unlock"></i> Unlock
                            </button>
                            ` : ''}
                        </div>
                    </td>
                </tr>
            `;
            }).join("");

            // Attach user table row action listeners
            tbody.querySelectorAll(".btn-inspect-user").forEach(btn => {
                btn.addEventListener("click", () => openUser360(btn.getAttribute("data-user-id")));
            });

            tbody.querySelectorAll(".btn-notify-user").forEach(btn => {
                btn.addEventListener("click", () => {
                    openSendNotificationModal(btn.getAttribute("data-user-id"), btn.getAttribute("data-email"));
                });
            });

            tbody.querySelectorAll(".btn-unlock-user").forEach(btn => {
                btn.addEventListener("click", () => handleQuickUnlock(btn.getAttribute("data-user-id")));
            });

            // Update Pagination UI
            updatePaginationInfo("users");
            if (window.lucide) window.lucide.createIcons();
        } catch (err) {
            console.error("loadUsersData error:", err);
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-8">Error loading customer directory.</td></tr>`;
        }
    }

    async function openUser360(userId) {
        const modal = document.getElementById("modal-user-360");
        const modalTitle = document.getElementById("u360-modal-title");
        const modalBody = document.getElementById("u360-modal-body");
        if (!modal || !modalBody) return;

        modalTitle.textContent = `Customer 360° Inspection — User #${userId}`;
        modalBody.innerHTML = `<div class="text-center text-muted py-8"><i data-lucide="loader" class="spin-animation"></i> Loading customer dossier...</div>`;
        modal.classList.remove("hidden");
        if (window.lucide) window.lucide.createIcons();

        try {
            const data = await apiRequest(`/api/admin/users/${userId}`);
            if (!data) throw new Error("Failed to load user 360 details");

            const prof = data.profile || {};
            const wallet = data.wallet || {};
            const deposits = data.deposits || [];
            const payouts = data.payouts || [];
            const sessionsCount = data.active_sessions_count || 0;

            const isLocked = wallet.is_budget_locked;
            const isDepLocked = wallet.is_deposit_locked;

            let budgetLockDisplay = '<span class="status-pill pill-success">Unlocked</span>';
            if (isLocked) {
                if (wallet.end_date) {
                    budgetLockDisplay = `<span class="status-pill pill-warning">Schedule active until ${escapeHtml(wallet.end_date)}</span>`;
                } else {
                    budgetLockDisplay = `<span class="status-pill pill-warning">Locked until ${escapeHtml(wallet.budget_locked_until || '')}</span>`;
                }
            }

            let depositLockDisplay = '<span class="status-pill pill-success">Unlocked</span>';
            if (isDepLocked) {
                if (wallet.end_date) {
                    depositLockDisplay = `<span class="status-pill pill-warning">Locked with schedule (ends ${escapeHtml(wallet.end_date)})</span>`;
                } else {
                    depositLockDisplay = `<span class="status-pill pill-warning">Locked until ${escapeHtml(wallet.deposit_locked_until || '')}</span>`;
                }
            }

            modalBody.innerHTML = `
                <!-- Identity & Status Cards -->
                <div class="u360-grid">
                    <div class="u360-data-card">
                        <div class="u360-section-title"><i data-lucide="user"></i> Account Identity</div>
                        <div class="space-y-2 text-sm">
                            <div><strong>Name:</strong> ${escapeHtml(prof.first_name || '')} ${escapeHtml(prof.last_name || '')}</div>
                            <div><strong>Email:</strong> ${escapeHtml(prof.email || 'N/A')}</div>
                            <div><strong>Phone:</strong> <span class="font-mono">${escapeHtml(prof.phone_number || 'N/A')}</span></div>
                            <div><strong>Payout Phone:</strong> <span class="font-mono">${escapeHtml(prof.payout_phone_number || prof.phone_number || 'N/A')}</span></div>
                            <div><strong>2FA Status:</strong> ${prof.two_factor_enabled ? '<span class="status-pill pill-success">Enabled</span>' : '<span class="status-pill pill-warning">Disabled</span>'}</div>
                            <div><strong>Active Sessions:</strong> ${sessionsCount} active</div>
                        </div>
                    </div>

                    <div class="u360-data-card">
                        <div class="u360-section-title"><i data-lucide="wallet"></i> Financial Float & Savings</div>
                        <div class="space-y-2 text-sm">
                            <div><strong>Available Balance:</strong> <span class="text-emerald font-bold font-mono">${formatCurrency(wallet.balance || 0)}</span></div>
                            <div><strong>Daily Budget:</strong> <span class="font-mono">${formatCurrency(wallet.daily_budget || 0)}</span> / day</div>
                            <div><strong>Payout Time:</strong> ${escapeHtml(wallet.payout_time || '12:00')}</div>
                            <div><strong>Budget Lock:</strong> ${budgetLockDisplay}</div>
                            <div><strong>Deposit Lock:</strong> ${depositLockDisplay}</div>
                        </div>
                    </div>
                </div>

                <!-- Support & Security Actions Bar -->
                <div class="u360-actions-bar mb-4">
                    <button class="btn btn-secondary btn-sm rbac-support" id="u360-btn-notify" data-user-id="${userId}" data-email="${escapeHtml(prof.email || '')}">
                        <i data-lucide="bell"></i> Send In-App Notice
                    </button>
                    <button class="btn btn-secondary btn-sm rbac-support" id="u360-btn-unlock" data-user-id="${userId}">
                        <i data-lucide="unlock"></i> Unlock Account
                    </button>
                    <button class="btn btn-secondary btn-sm rbac-support" id="u360-btn-toggle-2fa" data-user-id="${userId}">
                        <i data-lucide="shield"></i> ${prof.two_factor_enabled ? 'Disable 2FA' : 'Enable 2FA'}
                    </button>
                    <button class="btn btn-secondary btn-sm rbac-support" id="u360-btn-revoke-sessions" data-user-id="${userId}">
                        <i data-lucide="log-out"></i> Revoke All Sessions
                    </button>
                    <button class="btn btn-secondary btn-sm rbac-support" id="u360-btn-update-phone" data-user-id="${userId}">
                        <i data-lucide="phone"></i> Update Payout Phone
                    </button>
                </div>

                <!-- Recent Deposits & Payouts Lists -->
                <div class="grid-2col mb-4">
                    <div class="card p-3">
                        <h4 class="text-xs uppercase tracking-wider text-dim mb-2"><i data-lucide="arrow-down-circle"></i> Recent Deposits</h4>
                        ${deposits.length === 0 ? '<p class="text-dim text-xs">No deposits recorded yet.</p>' : `
                        <div class="table-responsive">
                            <table class="data-table text-xs">
                                <thead><tr><th>Receipt</th><th>Amount</th><th>Status</th></tr></thead>
                                <tbody>
                                    ${deposits.map(d => `
                                        <tr>
                                            <td><span class="font-mono">${escapeHtml(d.mpesa_receipt || d.checkout_request_id || '')}</span></td>
                                            <td class="text-emerald font-mono font-bold">${formatCurrency(d.amount)}</td>
                                            <td><span class="status-pill pill-${d.status === 'COMPLETED' ? 'success' : d.status === 'PENDING' ? 'warning' : 'danger'}">${d.status}</span></td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>`}
                    </div>

                    <div class="card p-3">
                        <h4 class="text-xs uppercase tracking-wider text-dim mb-2"><i data-lucide="send"></i> Recent Payouts</h4>
                        ${payouts.length === 0 ? '<p class="text-dim text-xs">No payouts recorded yet.</p>' : `
                        <div class="table-responsive">
                            <table class="data-table text-xs">
                                <thead><tr><th>Date</th><th>Amount</th><th>Status</th></tr></thead>
                                <tbody>
                                    ${payouts.map(p => `
                                        <tr>
                                            <td>${escapeHtml(p.payout_date || '')}</td>
                                            <td class="text-amber font-mono font-bold">${formatCurrency(p.amount)}</td>
                                            <td><span class="status-pill pill-${p.status === 'COMPLETED' ? 'success' : p.status === 'PENDING' ? 'warning' : 'danger'}">${p.status}</span></td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>`}
                    </div>
                </div>
            `;

            // Wire up actions inside modal
            const btnNotify = document.getElementById("u360-btn-notify");
            if (btnNotify) {
                btnNotify.addEventListener("click", () => {
                    openSendNotificationModal(userId, prof.email || `User #${userId}`);
                });
            }

            const btnUnlock = document.getElementById("u360-btn-unlock");
            if (btnUnlock) {
                btnUnlock.addEventListener("click", () => handleQuickUnlock(userId));
            }

            const btnToggle2fa = document.getElementById("u360-btn-toggle-2fa");
            if (btnToggle2fa) {
                btnToggle2fa.addEventListener("click", async () => {
                    const targetState = !prof.two_factor_enabled;
                    const reason = prompt(`Enter reason for ${targetState ? 'enabling' : 'disabling'} 2FA:`, "Customer support request");
                    if (reason === null) return;
                    try {
                        await apiRequest(`/api/admin/users/${userId}/toggle-2fa`, {
                            method: "POST",
                            body: JSON.stringify({ enabled: targetState, reason })
                        });
                        showToast(`2FA successfully ${targetState ? 'enabled' : 'disabled'} for User #${userId}`, "success");
                        openUser360(userId);
                    } catch (err) {
                        showToast(err.message || "Failed to toggle 2FA", "error");
                    }
                });
            }

            const btnRevoke = document.getElementById("u360-btn-revoke-sessions");
            if (btnRevoke) {
                btnRevoke.addEventListener("click", async () => {
                    if (!confirm(`Are you sure you want to invalidate all active login sessions for User #${userId}?`)) return;
                    const reason = prompt("Enter justification reason for session revocation:", "Security precaution");
                    if (reason === null) return;
                    try {
                        const res = await apiRequest(`/api/admin/users/${userId}/revoke-sessions`, {
                            method: "POST",
                            body: JSON.stringify({ reason })
                        });
                        showToast(res.message || "All sessions revoked", "success");
                        openUser360(userId);
                    } catch (err) {
                        showToast(err.message || "Failed to revoke sessions", "error");
                    }
                });
            }

            const btnPhone = document.getElementById("u360-btn-update-phone");
            if (btnPhone) {
                btnPhone.addEventListener("click", async () => {
                    const newPhone = prompt("Enter new Safaricom M-Pesa phone number (e.g. 254712345678):", prof.payout_phone_number || prof.phone_number || "");
                    if (!newPhone) return;
                    const reason = prompt("Enter reason for updating payout phone number:", "Customer verified request");
                    if (reason === null) return;
                    try {
                        const res = await apiRequest(`/api/admin/users/${userId}/update-payout-phone`, {
                            method: "POST",
                            body: JSON.stringify({ phone_number: newPhone, reason })
                        });
                        showToast(res.message || "Payout phone number updated", "success");
                        openUser360(userId);
                        loadUsersData();
                    } catch (err) {
                        showToast(err.message || "Failed to update phone number", "error");
                    }
                });
            }

            if (window.lucide) window.lucide.createIcons();
        } catch (err) {
            console.error("openUser360 error:", err);
            modalBody.innerHTML = `<div class="text-center text-danger py-8">Failed to load customer profile: ${escapeHtml(err.message || '')}</div>`;
        }
    }

    function openSendNotificationModal(userId, userDisplay) {
        const modal = document.getElementById("modal-send-notification");
        if (!modal) return;
        document.getElementById("notif-user-id").value = userId;
        document.getElementById("notif-user-display").value = `User #${userId} (${userDisplay})`;
        document.getElementById("notif-title").value = "";
        document.getElementById("notif-message").value = "";
        document.getElementById("notif-reason").value = "";
        modal.classList.remove("hidden");
        document.getElementById("notif-title").focus();
    }

    async function handleQuickUnlock(userId) {
        const reason = prompt(`Enter justification for unlocking User #${userId}:`, "Customer support assistance");
        if (reason === null) return;
        try {
            await apiRequest(`/api/admin/users/${userId}/unlock`, {
                method: "POST",
                body: JSON.stringify({ reason })
            });
            showToast(`User #${userId} account unlocked successfully`, "success");
            loadUsersData();
            const u360Modal = document.getElementById("modal-user-360");
            if (u360Modal && !u360Modal.classList.contains("hidden")) {
                openUser360(userId);
            }
        } catch (err) {
            showToast(err.message || "Failed to unlock account", "error");
        }
    }

    // --- VIEW: FINANCES & WALLETS ---
    async function loadWalletsData() {
        const tbody = document.getElementById("wallets-table-body");
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-8">Loading customer ledger...</td></tr>`;

        const searchInput = document.getElementById("wallets-search-input");
        const search = searchInput ? searchInput.value.trim() : "";
        const page = state.pagination.finances.page;

        let query = `/api/admin/finances/wallets?page=${page}&limit=${state.pagination.finances.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.finances.total = data.total || 0;

            const totalBalanceEl = document.getElementById("finances-total-balance");
            if (totalBalanceEl) {
                totalBalanceEl.textContent = formatCurrency(data.total_platform_balance || 0);
            }

            if (!data.wallets || data.wallets.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-8">No wallet records found.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.wallets.map(w => {
                const displayName = [w.first_name, w.last_name].filter(Boolean).join(" ") || w.email || `User #${w.user_id}`;
                const hasDepLock = !!w.is_deposit_locked;
                const hasBudLock = !!w.is_budget_locked;

                let lockBadges = "";
                if (hasDepLock) {
                    lockBadges += `<span class="badge badge-warning text-xs mr-1"><i data-lucide="lock"></i> Deposit Lock</span>`;
                }
                if (hasBudLock) {
                    lockBadges += `<span class="badge badge-purple text-xs"><i data-lucide="shield-alert"></i> Budget Lock</span>`;
                }
                if (!hasDepLock && !hasBudLock) {
                    lockBadges = `<span class="text-xs text-muted">No Locks</span>`;
                }

                let overrideButtons = "";
                if (hasDepLock) {
                    overrideButtons += `
                        <button class="btn btn-warning btn-xs btn-override-dep-lock mr-1" data-user-id="${w.user_id}" data-name="${escapeHtml(displayName)}">
                            Release Deposit
                        </button>
                    `;
                }
                if (hasBudLock) {
                    overrideButtons += `
                        <button class="btn btn-danger btn-xs btn-override-bud-lock" data-user-id="${w.user_id}" data-name="${escapeHtml(displayName)}">
                            Release Budget
                        </button>
                    `;
                }

                return `
                    <tr>
                        <td>
                            <strong>${escapeHtml(displayName)}</strong>
                            <div class="text-dim text-xs font-mono">${escapeHtml(w.phone_number || w.email)}</div>
                            <div class="mt-1">${lockBadges}</div>
                        </td>
                        <td class="text-emerald font-mono font-bold">${formatCurrency(w.balance)}</td>
                        <td class="text-purple font-mono">${formatCurrency(w.locked_balance)}</td>
                        <td>${formatCurrency(w.daily_budget)}</td>
                        <td><span class="badge-neutral">${escapeHtml(w.currency || 'KES')}</span></td>
                        <td>
                            <div class="btn-group rbac-finops">
                                <button class="btn btn-primary btn-sm btn-adjust-wallet mr-1" data-user-id="${w.user_id}" data-name="${escapeHtml(displayName)}" data-balance="${w.balance}">
                                    <i data-lucide="sliders"></i> Adjust
                                </button>
                                ${overrideButtons}
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");

            // Attach row button listeners
            tbody.querySelectorAll(".btn-adjust-wallet").forEach(btn => {
                btn.addEventListener("click", () => {
                    const userId = btn.getAttribute("data-user-id");
                    const name = btn.getAttribute("data-name");
                    openBalanceAdjustModal(userId, name);
                });
            });

            tbody.querySelectorAll(".btn-override-dep-lock").forEach(btn => {
                btn.addEventListener("click", () => {
                    const userId = btn.getAttribute("data-user-id");
                    const name = btn.getAttribute("data-name");
                    handleOverrideDepositLock(userId, name);
                });
            });

            tbody.querySelectorAll(".btn-override-bud-lock").forEach(btn => {
                btn.addEventListener("click", () => {
                    const userId = btn.getAttribute("data-user-id");
                    const name = btn.getAttribute("data-name");
                    handleOverrideBudgetLock(userId, name);
                });
            });

            updatePaginationInfo("finances");
            applyRbacGuards();
            if (window.lucide) window.lucide.createIcons();
        } catch (err) {
            console.error("loadWalletsData error:", err);
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-8">Error loading platform finances: ${escapeHtml(err.message || '')}</td></tr>`;
        }
    }

    function openBalanceAdjustModal(userId, userDisplay) {
        const modal = document.getElementById("modal-adjust-balance");
        if (!modal) return;
        document.getElementById("adj-user-id").value = userId || "";
        document.getElementById("adj-user-display").value = userId ? `User #${userId} (${userDisplay})` : "";
        document.getElementById("adj-type").value = "CREDIT";
        document.getElementById("adj-amount").value = "";
        document.getElementById("adj-reference").value = "";
        document.getElementById("adj-reason").value = "";
        modal.classList.remove("hidden");
        document.getElementById("adj-amount").focus();
    }

    async function handleOverrideDepositLock(userId, userDisplay) {
        const reason = prompt(`Enter compliance reason for releasing Deposit Lock for ${userDisplay}:`, "Customer emergency withdrawal request");
        if (reason === null || !reason.trim()) return;
        try {
            await apiRequest(`/api/admin/finances/${userId}/override-deposit-lock`, {
                method: "POST",
                body: JSON.stringify({ reason: reason.trim() })
            });
            showToast(`Deposit lock released for User #${userId}`, "success");
            loadWalletsData();
        } catch (err) {
            showToast(err.message || "Failed to release deposit lock", "error");
        }
    }

    async function handleOverrideBudgetLock(userId, userDisplay) {
        const reason = prompt(`Enter compliance reason for releasing Budget Lock for ${userDisplay}:`, "Customer requested savings plan restructuring");
        if (reason === null || !reason.trim()) return;
        try {
            await apiRequest(`/api/admin/finances/${userId}/override-budget-lock`, {
                method: "POST",
                body: JSON.stringify({ reason: reason.trim() })
            });
            showToast(`Budget lock released for User #${userId}`, "success");
            loadWalletsData();
        } catch (err) {
            showToast(err.message || "Failed to release budget lock", "error");
        }
    }

    // --- VIEW: DEPOSITS & STK ---
    // --- VIEW: DEPOSITS & STK ---
    async function loadDepositsData() {
        const tbody = document.getElementById("deposits-table-body");
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">Loading deposit records...</td></tr>`;

        const searchInput = document.getElementById("deposits-search-input");
        const search = searchInput ? searchInput.value.trim() : "";
        const statusFilter = document.getElementById("deposits-status-filter");
        const status = statusFilter ? statusFilter.value : "";
        const page = state.pagination.deposits.page;

        let query = `/api/admin/deposits?page=${page}&limit=${state.pagination.deposits.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;
        if (status) query += `&status=${encodeURIComponent(status)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.deposits.total = data.total || 0;

            const totalVolEl = document.getElementById("deposits-total-volume");
            if (totalVolEl) {
                totalVolEl.textContent = formatCurrency(data.total_amount || 0);
            }

            if (!data.deposits || data.deposits.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">No deposit transactions found.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.deposits.map(d => {
                let pillClass = "pill-neutral";
                if (d.status === "COMPLETED") pillClass = "pill-success";
                if (d.status === "FAILED") pillClass = "pill-danger";
                if (d.status === "PENDING") pillClass = "pill-warning";

                const customerDisplay = d.user_name || d.user_email || d.user_phone || `User #${d.user_id}`;

                return `
                    <tr>
                        <td class="font-mono text-xs font-bold">${escapeHtml(d.checkout_request_id)}</td>
                        <td>
                            <strong>${escapeHtml(customerDisplay)}</strong>
                            <div class="text-dim text-xs font-mono">${escapeHtml(d.user_phone || d.user_email)}</div>
                        </td>
                        <td class="font-mono font-bold text-emerald">${formatCurrency(d.amount)}</td>
                        <td><span class="status-pill ${pillClass}">${d.status}</span></td>
                        <td class="font-mono">${escapeHtml(d.mpesa_receipt || "-")}</td>
                        <td class="text-dim text-xs">${formatDate(d.created_at)}</td>
                        <td>
                            <div class="btn-group rbac-finops">
                                ${d.status === "PENDING" ? `
                                    <button class="btn btn-primary btn-xs btn-deposit-settle mr-1" data-checkout="${escapeHtml(d.checkout_request_id)}" data-customer="${escapeHtml(customerDisplay)}">
                                        <i data-lucide="check-circle-2"></i> Settle
                                    </button>
                                    <button class="btn btn-secondary btn-xs btn-deposit-requery" data-checkout="${escapeHtml(d.checkout_request_id)}">
                                        <i data-lucide="refresh-cw"></i> Requery
                                    </button>
                                ` : `<span class="text-dim text-xs">-</span>`}
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");

            // Wire row button events
            tbody.querySelectorAll(".btn-deposit-settle").forEach(btn => {
                btn.addEventListener("click", () => {
                    const checkout = btn.getAttribute("data-checkout");
                    const customer = btn.getAttribute("data-customer");
                    openManualSettleModal(checkout, customer);
                });
            });

            tbody.querySelectorAll(".btn-deposit-requery").forEach(btn => {
                btn.addEventListener("click", () => {
                    const checkout = btn.getAttribute("data-checkout");
                    handleRequeryDeposit(checkout);
                });
            });

            updatePaginationInfo("deposits");
            applyRbacGuards();
            if (window.lucide) window.lucide.createIcons();
        } catch (err) {
            console.error("loadDepositsData error:", err);
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-8">Error loading deposit pipeline: ${escapeHtml(err.message || '')}</td></tr>`;
        }
    }

    function openManualSettleModal(checkoutId, customerDisplay) {
        const modal = document.getElementById("modal-manual-settle-deposit");
        if (!modal) return;
        document.getElementById("settle-checkout-id").value = checkoutId;
        document.getElementById("settle-checkout-display").value = `${checkoutId} (${customerDisplay || 'Customer'})`;
        document.getElementById("settle-mpesa-receipt").value = "";
        document.getElementById("settle-reason").value = "";
        modal.classList.remove("hidden");
        document.getElementById("settle-mpesa-receipt").focus();
    }

    async function handleRequeryDeposit(checkoutId) {
        try {
            showToast(`Requerying gateway for ${checkoutId}...`, "info");
            const res = await apiRequest(`/api/admin/deposits/${checkoutId}/requery`, {
                method: "POST"
            });
            if (res.status === "COMPLETED") {
                showToast(`Deposit confirmed completed! Receipt: ${res.mpesa_receipt || 'VERIFIED'}`, "success");
            } else if (res.status === "FAILED") {
                showToast(`Deposit marked FAILED by gateway`, "warning");
            } else {
                showToast(`Deposit status is still ${res.status}`, "info");
            }
            loadDepositsData();
        } catch (err) {
            showToast(err.message || "Failed to requery gateway", "error");
        }
    }

    // --- VIEW: PAYOUTS & DISBURSEMENTS ---
    async function loadPayoutsData() {
        const tbody = document.getElementById("payouts-table-body");
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">Loading disbursement records...</td></tr>`;

        const searchInput = document.getElementById("payouts-search-input");
        const search = searchInput ? searchInput.value.trim() : "";
        const statusFilter = document.getElementById("payouts-status-filter");
        const status = statusFilter ? statusFilter.value : "";
        const page = state.pagination.payouts.page;

        let query = `/api/admin/payouts?page=${page}&limit=${state.pagination.payouts.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;
        if (status) query += `&status=${encodeURIComponent(status)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.payouts.total = data.total || 0;

            const totalDisbursedEl = document.getElementById("payouts-total-disbursed");
            if (totalDisbursedEl) {
                totalDisbursedEl.textContent = formatCurrency(data.total_disbursed || 0);
            }

            if (!data.payouts || data.payouts.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">No payout transactions found.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.payouts.map(p => {
                let pillClass = "pill-neutral";
                if (p.status === "COMPLETED" || p.status === "SUCCESS") pillClass = "pill-success";
                if (p.status === "FAILED") pillClass = "pill-danger";
                if (p.status === "PENDING") pillClass = "pill-warning";

                const customerDisplay = p.user_name || p.user_email || `User #${p.user_id}`;
                const trackingDisplay = p.transaction_id || p.conversation_id || "-";
                const errorSubtext = p.error_message ? `<div class="text-danger text-xs truncate max-w-xs" title="${escapeHtml(p.error_message)}">${escapeHtml(p.error_message)}</div>` : "";

                return `
                    <tr>
                        <td class="font-mono text-xs font-bold">${escapeHtml(p.payout_date || "-")}</td>
                        <td>
                            <strong>${escapeHtml(customerDisplay)}</strong>
                            <div class="text-dim text-xs">${escapeHtml(p.user_email || "")}</div>
                        </td>
                        <td class="font-mono">${escapeHtml(p.phone_number)}</td>
                        <td class="font-mono font-bold text-emerald">${formatCurrency(p.amount)}</td>
                        <td><span class="status-pill ${pillClass}">${p.status}</span></td>
                        <td>
                            <div class="font-mono text-xs">${escapeHtml(trackingDisplay)}</div>
                            ${errorSubtext}
                        </td>
                        <td>
                            <div class="btn-group rbac-finops">
                                ${p.status === "FAILED" ? `
                                    <button class="btn btn-primary btn-xs btn-payout-retry mr-1" data-id="${p.id}" data-customer="${escapeHtml(customerDisplay)}" data-amount="${p.amount}">
                                        <i data-lucide="refresh-cw"></i> Retry
                                    </button>
                                    <button class="btn btn-secondary btn-xs btn-payout-settle" data-id="${p.id}" data-customer="${escapeHtml(customerDisplay)}" data-amount="${p.amount}">
                                        <i data-lucide="check-circle-2"></i> Reconcile
                                    </button>
                                ` : (p.status === "PENDING" ? `
                                    <button class="btn btn-secondary btn-xs btn-payout-settle" data-id="${p.id}" data-customer="${escapeHtml(customerDisplay)}" data-amount="${p.amount}">
                                        <i data-lucide="check-circle-2"></i> Reconcile
                                    </button>
                                ` : `<span class="text-dim text-xs">-</span>`)}
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");

            // Wire row buttons
            tbody.querySelectorAll(".btn-payout-retry").forEach(btn => {
                btn.addEventListener("click", () => {
                    const id = btn.getAttribute("data-id");
                    const cust = btn.getAttribute("data-customer");
                    const amt = btn.getAttribute("data-amount");
                    openRetryPayoutModal(id, `Payout #${id} (${cust} - KES ${Number(amt).toLocaleString()})`);
                });
            });

            tbody.querySelectorAll(".btn-payout-settle").forEach(btn => {
                btn.addEventListener("click", () => {
                    const id = btn.getAttribute("data-id");
                    const cust = btn.getAttribute("data-customer");
                    const amt = btn.getAttribute("data-amount");
                    openManualSettlePayoutModal(id, `Payout #${id} (${cust} - KES ${Number(amt).toLocaleString()})`);
                });
            });

            updatePaginationInfo("payouts");
            applyRbacGuards();
            if (window.lucide) window.lucide.createIcons();
        } catch (err) {
            console.error("loadPayoutsData error:", err);
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-8">Error loading payouts pipeline: ${escapeHtml(err.message || '')}</td></tr>`;
        }
    }

    function openRetryPayoutModal(payoutId, payoutDisplay) {
        const modal = document.getElementById("modal-retry-payout");
        if (!modal) return;
        document.getElementById("retry-payout-id").value = payoutId;
        document.getElementById("retry-payout-display").value = payoutDisplay;
        document.getElementById("retry-payout-reason").value = "";
        modal.classList.remove("hidden");
        document.getElementById("retry-payout-reason").focus();
    }

    function openManualSettlePayoutModal(payoutId, payoutDisplay) {
        const modal = document.getElementById("modal-manual-settle-payout");
        if (!modal) return;
        document.getElementById("settle-payout-id").value = payoutId;
        document.getElementById("settle-payout-display").value = payoutDisplay;
        document.getElementById("settle-payout-tx").value = "";
        document.getElementById("settle-payout-reason").value = "";
        modal.classList.remove("hidden");
        document.getElementById("settle-payout-tx").focus();
    }

    // --- VIEW: AUDIT LOGS ---
    let currentAuditLogsCache = [];

    async function loadAuditLogsData() {
        const tbody = document.getElementById("audit-table-body");
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">Loading compliance audit logs...</td></tr>`;

        const searchInput = document.getElementById("audit-search-input");
        const search = searchInput ? searchInput.value.trim() : "";
        const actionFilter = document.getElementById("audit-action-filter");
        const action = actionFilter ? actionFilter.value : "";
        const page = state.pagination.audit.page;

        let query = `/api/admin/audit/logs?page=${page}&limit=${state.pagination.audit.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;
        if (action) query += `&action=${encodeURIComponent(action)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.audit.total = data.total || 0;
            currentAuditLogsCache = data.logs || [];

            if (!data.logs || data.logs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">No audit logs recorded for this criteria.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.logs.map(l => `
                <tr>
                    <td class="text-dim text-xs font-mono">${formatDate(l.created_at)}</td>
                    <td><strong>${escapeHtml(l.admin_email || "System/CLI")}</strong></td>
                    <td><span class="status-pill pill-neutral font-mono text-xs">${escapeHtml(l.action)}</span></td>
                    <td>${l.target_type ? `<strong>${escapeHtml(l.target_type)}</strong> #${l.target_id || ""}` : "-"}</td>
                    <td>${escapeHtml(l.reason || "-")}</td>
                    <td class="font-mono text-xs">${escapeHtml(l.ip_address || "-")}</td>
                    <td>
                        <button class="btn btn-secondary btn-xs btn-inspect-audit" data-id="${l.id}">
                            <i data-lucide="code"></i> Inspect
                        </button>
                    </td>
                </tr>
            `).join("");

            tbody.querySelectorAll(".btn-inspect-audit").forEach(btn => {
                btn.addEventListener("click", () => {
                    const id = parseInt(btn.getAttribute("data-id"), 10);
                    const log = currentAuditLogsCache.find(item => item.id === id);
                    if (log) {
                        openAuditPayloadModal(log);
                    }
                });
            });

            updatePaginationInfo("audit");
            applyRbacGuards();
            if (window.lucide) window.lucide.createIcons();
        } catch (err) {
            console.error("loadAuditLogsData error:", err);
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-8">Error loading compliance audit trail: ${escapeHtml(err.message || '')}</td></tr>`;
        }
    }

    function formatJsonPayload(str) {
        if (!str || !str.trim()) return "None";
        try {
            const parsed = JSON.parse(str);
            return JSON.stringify(parsed, null, 2);
        } catch {
            return str;
        }
    }

    function openAuditPayloadModal(log) {
        const modal = document.getElementById("modal-audit-payload");
        if (!modal) return;

        document.getElementById("audit-payload-title").textContent = `Audit Log #${log.id} (${log.action})`;
        document.getElementById("audit-before-state").textContent = formatJsonPayload(log.before_state);
        document.getElementById("audit-after-state").textContent = formatJsonPayload(log.after_state);
        document.getElementById("audit-payload-reason").textContent = log.reason
            ? `${log.reason} [Target: ${log.target_type || 'N/A'} #${log.target_id || 'N/A'} | IP: ${log.ip_address || 'N/A'}]`
            : "No justification reason recorded.";

        modal.classList.remove("hidden");
    }

    // --- VIEW: SYSTEM HEALTH ---
    async function loadSystemHealthData() {
        try {
            const data = await apiRequest("/api/admin/system/health");
            if (!data) return;

            document.getElementById("health-db-status").innerHTML = data.database === "connected"
                ? `<i data-lucide="check-circle"></i> Connected`
                : `<i data-lucide="alert-triangle"></i> Error`;
            
            document.getElementById("health-scheduler-status").innerHTML = data.scheduler && data.scheduler.running
                ? `<i data-lucide="check-circle"></i> Active (${data.scheduler.interval_seconds}s interval)`
                : `<i data-lucide="pause-circle"></i> Inactive`;

            document.getElementById("health-gateway-status").innerHTML = `<i data-lucide="radio"></i> ${data.payment_gateway.mode.toUpperCase()}`;
            document.getElementById("health-env-status").textContent = data.environment.toUpperCase();

            // If SuperAdmin, load admin user directory
            const superCard = document.getElementById("superadmin-management-card");
            if (state.adminUser && state.adminUser.role === "superadmin") {
                if (superCard) superCard.style.display = "";
                await loadAdminDirectory();
            } else {
                if (superCard) superCard.style.display = "none";
            }

            if (window.lucide) window.lucide.createIcons();
        } catch {
            showToast("Failed to load platform health status", "error");
        }
    }

    let currentAdminsCache = [];

    async function loadAdminDirectory() {
        const tbody = document.getElementById("admins-table-body");
        try {
            const data = await apiRequest("/api/admin/system/admins");
            currentAdminsCache = data.admins || [];

            if (!data.admins || data.admins.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-4">No staff administrators found.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.admins.map(a => `
                <tr>
                    <td><strong>${escapeHtml(a.email)}</strong></td>
                    <td><span class="admin-role-badge badge-${a.role.toLowerCase()}">${a.role}</span></td>
                    <td>
                        ${a.is_active 
                            ? `<span class="status-pill pill-success">Active</span>` 
                            : `<span class="status-pill pill-danger">Deactivated</span>`}
                    </td>
                    <td>
                        ${a.id !== (state.adminUser ? state.adminUser.id : null) ? `
                            <div class="btn-group">
                                <button class="btn btn-secondary btn-xs btn-edit-admin-role mr-1" data-admin-id="${a.id}">
                                    <i data-lucide="edit-3"></i> Role
                                </button>
                                <button class="btn btn-secondary btn-xs btn-toggle-admin-status" data-admin-id="${a.id}" data-active="${a.is_active}">
                                    ${a.is_active ? "Deactivate" : "Activate"}
                                </button>
                            </div>
                        ` : `<span class="text-dim text-xs">(Current Account)</span>`}
                    </td>
                </tr>
            `).join("");

            tbody.querySelectorAll(".btn-edit-admin-role").forEach(btn => {
                btn.addEventListener("click", () => {
                    const id = parseInt(btn.getAttribute("data-admin-id"), 10);
                    const admin = currentAdminsCache.find(item => item.id === id);
                    if (admin) openUpdateAdminRoleModal(admin);
                });
            });

            tbody.querySelectorAll(".btn-toggle-admin-status").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const id = parseInt(btn.getAttribute("data-admin-id"), 10);
                    const isActive = btn.getAttribute("data-active") === "true";
                    const newStatus = !isActive;
                    const actionName = newStatus ? "activate" : "deactivate";

                    const reason = prompt(`Please enter mandatory audit reason to ${actionName} this administrator account:`);
                    if (!reason || reason.trim().length < 3) {
                        showToast("Action cancelled. Audit reason required.", "warning");
                        return;
                    }

                    try {
                        const res = await apiRequest(`/api/admin/system/admins/${id}/toggle-active`, {
                            method: "POST",
                            body: JSON.stringify({ is_active: newStatus, reason: reason.trim() })
                        });
                        showToast(res.message || `Account ${actionName}d successfully`, "success");
                        loadAdminDirectory();
                    } catch (err) {
                        showToast(err.message || `Failed to ${actionName} account`, "error");
                    }
                });
            });

            if (window.lucide) window.lucide.createIcons();
        } catch {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center text-danger py-4">Failed to load admin directory.</td></tr>`;
        }
    }

    function openCreateAdminModal() {
        const modal = document.getElementById("modal-create-admin");
        if (!modal) return;
        document.getElementById("create-admin-email").value = "";
        document.getElementById("create-admin-password").value = "";
        document.getElementById("create-admin-role").value = "support";
        document.getElementById("create-admin-reason").value = "";
        modal.classList.remove("hidden");
        document.getElementById("create-admin-email").focus();
    }

    function openUpdateAdminRoleModal(admin) {
        const modal = document.getElementById("modal-update-admin-role");
        if (!modal) return;
        document.getElementById("edit-admin-id").value = admin.id;
        document.getElementById("edit-admin-email").value = admin.email;
        document.getElementById("edit-admin-role").value = admin.role.toLowerCase();
        document.getElementById("edit-admin-reason").value = "";
        modal.classList.remove("hidden");
        document.getElementById("edit-admin-reason").focus();
    }

    function updatePaginationInfo(section) {
        const p = state.pagination[section];
        const infoEl = document.getElementById(`${section}-pagination-info`);
        const prevBtn = document.getElementById(`btn-${section}-prev`);
        const nextBtn = document.getElementById(`btn-${section}-next`);

        if (!infoEl) return;
        const start = p.total === 0 ? 0 : (p.page - 1) * p.limit + 1;
        const end = Math.min(p.page * p.limit, p.total);
        infoEl.textContent = `Showing ${start}-${end} of ${p.total} records`;

        if (prevBtn) prevBtn.disabled = p.page <= 1;
        if (nextBtn) nextBtn.disabled = end >= p.total;
    }

    // =========================================================================
    // 7. EVENT LISTENERS & INITIALIZATION
    // =========================================================================
    document.addEventListener("DOMContentLoaded", () => {
        // 1. Check Initial Authentication
        checkAuthSession();

        // 2. Hash Router Listener
        window.addEventListener("hashchange", handleRoute);

        // 3. Login Form Submit
        const loginForm = document.getElementById("admin-login-form");
        if (loginForm) {
            loginForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                const email = document.getElementById("admin-email").value.trim();
                const password = document.getElementById("admin-password").value;
                const errBanner = document.getElementById("login-error-banner");
                const errText = document.getElementById("login-error-text");

                errBanner.classList.add("hidden");
                try {
                    const data = await apiRequest("/api/admin/auth/login", {
                        method: "POST",
                        body: JSON.stringify({ email, password })
                    });
                    if (data && data.admin) {
                        state.adminUser = data.admin;
                        onAuthenticated();
                        showToast(`Welcome back, ${data.admin.email}`, "success");
                    }
                } catch (err) {
                    errText.textContent = err.message || "Invalid administrator credentials.";
                    errBanner.classList.remove("hidden");
                }
            });
        }

        // 4. Logout Button
        const logoutBtn = document.getElementById("btn-admin-logout");
        if (logoutBtn) logoutBtn.addEventListener("click", handleLogout);

        // 5. Global Refresh Button
        const refreshBtn = document.getElementById("btn-global-refresh");
        if (refreshBtn) {
            refreshBtn.addEventListener("click", () => {
                const icon = document.getElementById("refresh-icon");
                if (icon) icon.classList.add("spin-animation");
                handleRoute();
                setTimeout(() => {
                    if (icon) icon.classList.remove("spin-animation");
                    showToast("Dashboard metrics refreshed", "info");
                }, 500);
            });
        }

        // 6. Theme Toggle Button
        const themeBtn = document.getElementById("btn-theme-toggle");
        if (themeBtn) {
            themeBtn.addEventListener("click", () => {
                const html = document.documentElement;
                const current = html.getAttribute("data-theme") || "dark";
                const target = current === "dark" ? "light" : "dark";
                html.setAttribute("data-theme", target);

                document.getElementById("theme-icon-sun").classList.toggle("hidden", target !== "dark");
                document.getElementById("theme-icon-moon").classList.toggle("hidden", target === "dark");
            });
        }

        // 7. Modals Dismiss Buttons
        document.querySelectorAll(".btn-close-modal").forEach(btn => {
            btn.addEventListener("click", () => {
                const modalId = btn.getAttribute("data-modal");
                if (modalId) {
                    const modal = document.getElementById(modalId);
                    if (modal) modal.classList.add("hidden");
                }
            });
        });

        // 8. Trigger Daily Batch Confirmation
        const btnBatch = document.getElementById("btn-qa-trigger-batch");
        if (btnBatch) {
            btnBatch.addEventListener("click", async () => {
                if (!confirm("Are you sure you want to trigger immediate daily payouts for all active eligible budgets?")) return;
                try {
                    const res = await apiRequest("/api/admin/payouts/trigger-daily-batch", { method: "POST" });
                    showToast(`Payout batch triggered: ${res.status}`, "success");
                    loadOverviewData();
                } catch (err) {
                    showToast(err.message || "Failed to trigger daily payout batch", "error");
                }
            });
        }

        // Quick Action: Adjust Balance Navigation
        const btnAdjustBalance = document.getElementById("btn-qa-adjust-balance");
        if (btnAdjustBalance) {
            btnAdjustBalance.addEventListener("click", () => {
                window.location.hash = "#/finances";
            });
        }

        // 9. Users Directory Search, Filters & Pagination
        const usersSearch = document.getElementById("users-search-input");
        if (usersSearch) {
            usersSearch.addEventListener("input", () => {
                clearTimeout(usersSearchDebounceTimer);
                usersSearchDebounceTimer = setTimeout(() => {
                    state.pagination.users.page = 1;
                    loadUsersData();
                }, 300);
            });
        }

        const usersStatus = document.getElementById("users-status-filter");
        if (usersStatus) {
            usersStatus.addEventListener("change", () => {
                state.pagination.users.page = 1;
                loadUsersData();
            });
        }

        const btnUsersPrev = document.getElementById("btn-users-prev");
        if (btnUsersPrev) {
            btnUsersPrev.addEventListener("click", () => {
                if (state.pagination.users.page > 1) {
                    state.pagination.users.page--;
                    loadUsersData();
                }
            });
        }

        const btnUsersNext = document.getElementById("btn-users-next");
        if (btnUsersNext) {
            btnUsersNext.addEventListener("click", () => {
                const p = state.pagination.users;
                if (p.page * p.limit < p.total) {
                    p.page++;
                    loadUsersData();
                }
            });
        }

        // 10. Finances & Wallets Table Search & Pagination
        let walletsSearchDebounceTimer = null;
        const walletsSearch = document.getElementById("wallets-search-input");
        if (walletsSearch) {
            walletsSearch.addEventListener("input", () => {
                clearTimeout(walletsSearchDebounceTimer);
                walletsSearchDebounceTimer = setTimeout(() => {
                    state.pagination.finances.page = 1;
                    loadWalletsData();
                }, 300);
            });
        }

        const btnWalletsPrev = document.getElementById("btn-wallets-prev");
        if (btnWalletsPrev) {
            btnWalletsPrev.addEventListener("click", () => {
                if (state.pagination.finances.page > 1) {
                    state.pagination.finances.page--;
                    loadWalletsData();
                }
            });
        }

        const btnWalletsNext = document.getElementById("btn-wallets-next");
        if (btnWalletsNext) {
            btnWalletsNext.addEventListener("click", () => {
                const p = state.pagination.finances;
                if (p.page * p.limit < p.total) {
                    p.page++;
                    loadWalletsData();
                }
            });
        }

        const btnOpenAdjust = document.getElementById("btn-open-balance-adjust");
        if (btnOpenAdjust) {
            btnOpenAdjust.addEventListener("click", () => {
                const promptUserId = prompt("Enter Target User ID for balance adjustment:");
                if (!promptUserId) return;
                const uid = parseInt(promptUserId, 10);
                if (isNaN(uid) || uid <= 0) {
                    showToast("Please enter a valid numeric User ID", "error");
                    return;
                }
                openBalanceAdjustModal(uid, `User #${uid}`);
            });
        }

        // 11. Balance Adjustment Form Submit
        const formAdjustBalance = document.getElementById("form-adjust-balance");
        if (formAdjustBalance) {
            formAdjustBalance.addEventListener("submit", async (e) => {
                e.preventDefault();
                const userId = parseInt(document.getElementById("adj-user-id").value, 10);
                const adjustment_type = document.getElementById("adj-type").value;
                const amount = parseInt(document.getElementById("adj-amount").value, 10);
                const reference_id = document.getElementById("adj-reference").value.trim() || undefined;
                const reason = document.getElementById("adj-reason").value.trim();
                const submitBtn = document.getElementById("btn-submit-adjust");

                if (isNaN(userId) || userId <= 0) {
                    showToast("Invalid User ID for adjustment", "error");
                    return;
                }
                if (isNaN(amount) || amount <= 0) {
                    showToast("Please enter a positive adjustment amount", "error");
                    return;
                }

                if (submitBtn) submitBtn.disabled = true;
                try {
                    const res = await apiRequest("/api/admin/finances/adjust-balance", {
                        method: "POST",
                        body: JSON.stringify({ user_id: userId, amount, adjustment_type, reference_id, reason })
                    });
                    showToast(res.message || `Successfully adjusted balance for User #${userId}`, "success");
                    const modal = document.getElementById("modal-adjust-balance");
                    if (modal) modal.classList.add("hidden");
                    formAdjustBalance.reset();
                    loadWalletsData();
                } catch (err) {
                    showToast(err.message || "Balance adjustment failed", "error");
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 12. Deposits & STK Push Table Search, Filter & Pagination
        let depositsSearchDebounceTimer = null;
        const depositsSearch = document.getElementById("deposits-search-input");
        if (depositsSearch) {
            depositsSearch.addEventListener("input", () => {
                clearTimeout(depositsSearchDebounceTimer);
                depositsSearchDebounceTimer = setTimeout(() => {
                    state.pagination.deposits.page = 1;
                    loadDepositsData();
                }, 300);
            });
        }

        const depositsFilter = document.getElementById("deposits-status-filter");
        if (depositsFilter) {
            depositsFilter.addEventListener("change", () => {
                state.pagination.deposits.page = 1;
                loadDepositsData();
            });
        }

        const btnDepositsPrev = document.getElementById("btn-deposits-prev");
        if (btnDepositsPrev) {
            btnDepositsPrev.addEventListener("click", () => {
                if (state.pagination.deposits.page > 1) {
                    state.pagination.deposits.page--;
                    loadDepositsData();
                }
            });
        }

        const btnDepositsNext = document.getElementById("btn-deposits-next");
        if (btnDepositsNext) {
            btnDepositsNext.addEventListener("click", () => {
                const p = state.pagination.deposits;
                if (p.page * p.limit < p.total) {
                    p.page++;
                    loadDepositsData();
                }
            });
        }

        // 13. Manual Settle Deposit Form Submit
        const formManualSettle = document.getElementById("form-manual-settle-deposit");
        if (formManualSettle) {
            formManualSettle.addEventListener("submit", async (e) => {
                e.preventDefault();
                const checkoutId = document.getElementById("settle-checkout-id").value;
                const mpesaReceipt = document.getElementById("settle-mpesa-receipt").value.trim().toUpperCase();
                const reason = document.getElementById("settle-reason").value.trim();
                const submitBtn = document.getElementById("btn-submit-settle-deposit");

                if (!checkoutId) {
                    showToast("Missing checkout transaction reference", "error");
                    return;
                }
                if (!mpesaReceipt || mpesaReceipt.length < 5) {
                    showToast("Please enter a valid M-Pesa receipt number", "error");
                    return;
                }
                if (!reason || reason.length < 3) {
                    showToast("Please provide mandatory audit justification", "error");
                    return;
                }

                if (submitBtn) submitBtn.disabled = true;
                try {
                    const res = await apiRequest(`/api/admin/deposits/${checkoutId}/manual-settle`, {
                        method: "POST",
                        body: JSON.stringify({ mpesa_receipt: mpesaReceipt, reason })
                    });
                    showToast(res.message || `Deposit ${checkoutId} settled successfully!`, "success");
                    const modal = document.getElementById("modal-manual-settle-deposit");
                    if (modal) modal.classList.add("hidden");
                    formManualSettle.reset();
                    loadDepositsData();
                } catch (err) {
                    showToast(err.message || "Manual settlement failed", "error");
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 14. Payouts & Disbursements Table Search, Filter & Pagination
        let payoutsSearchDebounceTimer = null;
        const payoutsSearch = document.getElementById("payouts-search-input");
        if (payoutsSearch) {
            payoutsSearch.addEventListener("input", () => {
                clearTimeout(payoutsSearchDebounceTimer);
                payoutsSearchDebounceTimer = setTimeout(() => {
                    state.pagination.payouts.page = 1;
                    loadPayoutsData();
                }, 300);
            });
        }

        const payoutsFilter = document.getElementById("payouts-status-filter");
        if (payoutsFilter) {
            payoutsFilter.addEventListener("change", () => {
                state.pagination.payouts.page = 1;
                loadPayoutsData();
            });
        }

        const btnPayoutsPrev = document.getElementById("btn-payouts-prev");
        if (btnPayoutsPrev) {
            btnPayoutsPrev.addEventListener("click", () => {
                if (state.pagination.payouts.page > 1) {
                    state.pagination.payouts.page--;
                    loadPayoutsData();
                }
            });
        }

        const btnPayoutsNext = document.getElementById("btn-payouts-next");
        if (btnPayoutsNext) {
            btnPayoutsNext.addEventListener("click", () => {
                const p = state.pagination.payouts;
                if (p.page * p.limit < p.total) {
                    p.page++;
                    loadPayoutsData();
                }
            });
        }

        // 15. Trigger Daily Payout Batch Button
        const btnTriggerBatch = document.getElementById("btn-open-trigger-batch");
        if (btnTriggerBatch) {
            btnTriggerBatch.addEventListener("click", async () => {
                if (!confirm("Are you sure you want to trigger today's daily payout disbursement batch now?")) {
                    return;
                }
                btnTriggerBatch.disabled = true;
                showToast("Executing daily payout scheduler batch...", "info");
                try {
                    const res = await apiRequest("/api/admin/payouts/trigger-daily-batch", { method: "POST" });
                    showToast(res.message || "Daily payout batch completed!", "success");
                    loadPayoutsData();
                } catch (err) {
                    showToast(err.message || "Failed to execute daily batch", "error");
                } finally {
                    btnTriggerBatch.disabled = false;
                }
            });
        }

        // 16. Retry Payout Form Submit
        const formRetryPayout = document.getElementById("form-retry-payout");
        if (formRetryPayout) {
            formRetryPayout.addEventListener("submit", async (e) => {
                e.preventDefault();
                const payoutId = document.getElementById("retry-payout-id").value;
                const reason = document.getElementById("retry-payout-reason").value.trim();
                const submitBtn = document.getElementById("btn-submit-retry-payout");

                if (!payoutId) {
                    showToast("Missing payout reference", "error");
                    return;
                }
                if (!reason || reason.length < 3) {
                    showToast("Please enter mandatory audit justification", "error");
                    return;
                }

                if (submitBtn) submitBtn.disabled = true;
                try {
                    const res = await apiRequest(`/api/admin/payouts/${payoutId}/retry`, {
                        method: "POST",
                        body: JSON.stringify({ reason })
                    });
                    showToast(res.message || `Payout #${payoutId} queued for retry successfully!`, "success");
                    const modal = document.getElementById("modal-retry-payout");
                    if (modal) modal.classList.add("hidden");
                    formRetryPayout.reset();
                    loadPayoutsData();
                } catch (err) {
                    showToast(err.message || "Retry payout failed", "error");
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 17. Manual Settle Payout Form Submit
        const formManualSettlePayout = document.getElementById("form-manual-settle-payout");
        if (formManualSettlePayout) {
            formManualSettlePayout.addEventListener("submit", async (e) => {
                e.preventDefault();
                const payoutId = document.getElementById("settle-payout-id").value;
                const txId = document.getElementById("settle-payout-tx").value.trim().toUpperCase();
                const reason = document.getElementById("settle-payout-reason").value.trim();
                const submitBtn = document.getElementById("btn-submit-settle-payout");

                if (!payoutId) {
                    showToast("Missing payout reference", "error");
                    return;
                }
                if (!txId || txId.length < 4) {
                    showToast("Please enter a valid external transaction ID", "error");
                    return;
                }
                if (!reason || reason.length < 3) {
                    showToast("Please provide mandatory audit justification", "error");
                    return;
                }

                if (submitBtn) submitBtn.disabled = true;
                try {
                    const res = await apiRequest(`/api/admin/payouts/${payoutId}/mark-settled`, {
                        method: "POST",
                        body: JSON.stringify({ transaction_id: txId, reason })
                    });
                    showToast(res.message || `Payout #${payoutId} reconciled successfully!`, "success");
                    const modal = document.getElementById("modal-manual-settle-payout");
                    if (modal) modal.classList.add("hidden");
                    formManualSettlePayout.reset();
                    loadPayoutsData();
                } catch (err) {
                    showToast(err.message || "Manual settlement failed", "error");
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 18. Send In-App Notification Form Submit
        const formSendNotif = document.getElementById("form-send-notification");
        if (formSendNotif) {
            formSendNotif.addEventListener("submit", async (e) => {
                e.preventDefault();
                const userId = document.getElementById("notif-user-id").value;
                const title = document.getElementById("notif-title").value.trim();
                const type = document.getElementById("notif-type").value;
                const message = document.getElementById("notif-message").value.trim();
                const reason = document.getElementById("notif-reason").value.trim();
                const submitBtn = document.getElementById("btn-submit-send-notif");

                if (submitBtn) submitBtn.disabled = true;
                try {
                    const res = await apiRequest(`/api/admin/users/${userId}/notify`, {
                        method: "POST",
                        body: JSON.stringify({ title, message, type, reason })
                    });
                    showToast(res.message || "Notification dispatched to customer successfully", "success");
                    const modal = document.getElementById("modal-send-notification");
                    if (modal) modal.classList.add("hidden");
                    formSendNotif.reset();
                } catch (err) {
                    showToast(err.message || "Failed to dispatch notification", "error");
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 19. Export CSV Download Button
        const btnExportCsv = document.getElementById("btn-export-audit-csv");
        if (btnExportCsv) {
            btnExportCsv.addEventListener("click", () => {
                window.location.href = "/api/admin/audit/export";
            });
        }

        // 20. Compliance Audit Logs Search, Filter & Pagination
        let auditSearchDebounceTimer = null;
        const auditSearch = document.getElementById("audit-search-input");
        if (auditSearch) {
            auditSearch.addEventListener("input", () => {
                clearTimeout(auditSearchDebounceTimer);
                auditSearchDebounceTimer = setTimeout(() => {
                    state.pagination.audit.page = 1;
                    loadAuditLogsData();
                }, 300);
            });
        }

        const auditFilter = document.getElementById("audit-action-filter");
        if (auditFilter) {
            auditFilter.addEventListener("change", () => {
                state.pagination.audit.page = 1;
                loadAuditLogsData();
            });
        }

        const btnAuditPrev = document.getElementById("btn-audit-prev");
        if (btnAuditPrev) {
            btnAuditPrev.addEventListener("click", () => {
                if (state.pagination.audit.page > 1) {
                    state.pagination.audit.page--;
                    loadAuditLogsData();
                }
            });
        }

        const btnAuditNext = document.getElementById("btn-audit-next");
        if (btnAuditNext) {
            btnAuditNext.addEventListener("click", () => {
                const p = state.pagination.audit;
                if (p.page * p.limit < p.total) {
                    p.page++;
                    loadAuditLogsData();
                }
            });
        }

        // 21. Staff Admin Provisioning Button & Modal Form
        const btnOpenCreateAdmin = document.getElementById("btn-open-create-admin");
        if (btnOpenCreateAdmin) {
            btnOpenCreateAdmin.addEventListener("click", () => {
                openCreateAdminModal();
            });
        }

        const formCreateAdmin = document.getElementById("form-create-admin");
        if (formCreateAdmin) {
            formCreateAdmin.addEventListener("submit", async (e) => {
                e.preventDefault();
                const email = document.getElementById("create-admin-email").value.trim().toLowerCase();
                const password = document.getElementById("create-admin-password").value;
                const role = document.getElementById("create-admin-role").value;
                const reason = document.getElementById("create-admin-reason").value.trim();
                const submitBtn = document.getElementById("btn-submit-create-admin");

                if (!email || !password || password.length < 8) {
                    showToast("Please provide valid corporate email and minimum 8-character password", "error");
                    return;
                }

                if (submitBtn) submitBtn.disabled = true;
                try {
                    const res = await apiRequest("/api/admin/system/admins", {
                        method: "POST",
                        body: JSON.stringify({ email, password, role, reason })
                    });
                    showToast(`Administrator account for ${email} provisioned successfully!`, "success");
                    const modal = document.getElementById("modal-create-admin");
                    if (modal) modal.classList.add("hidden");
                    formCreateAdmin.reset();
                    loadAdminDirectory();
                } catch (err) {
                    showToast(err.message || "Failed to provision administrator account", "error");
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 22. Update Staff Admin Role Modal Form
        const formUpdateAdminRole = document.getElementById("form-update-admin-role");
        if (formUpdateAdminRole) {
            formUpdateAdminRole.addEventListener("submit", async (e) => {
                e.preventDefault();
                const adminId = document.getElementById("edit-admin-id").value;
                const role = document.getElementById("edit-admin-role").value;
                const reason = document.getElementById("edit-admin-reason").value.trim();
                const submitBtn = document.getElementById("btn-submit-update-admin-role");

                if (!adminId || !role) {
                    showToast("Missing administrator reference or role", "error");
                    return;
                }
                if (!reason || reason.length < 3) {
                    showToast("Please provide mandatory audit justification", "error");
                    return;
                }

                if (submitBtn) submitBtn.disabled = true;
                try {
                    const res = await apiRequest(`/api/admin/system/admins/${adminId}/role`, {
                        method: "PUT",
                        body: JSON.stringify({ role, reason })
                    });
                    showToast(`Administrator role updated to ${role.toUpperCase()} successfully!`, "success");
                    const modal = document.getElementById("modal-update-admin-role");
                    if (modal) modal.classList.add("hidden");
                    formUpdateAdminRole.reset();
                    loadAdminDirectory();
                } catch (err) {
                    showToast(err.message || "Failed to update administrator role", "error");
                } finally {
                    if (submitBtn) submitBtn.disabled = false;
                }
            });
        }

        // 23. Lucide Icons Initial Call
        if (window.lucide) {
            window.lucide.createIcons();
        }
    });

})();

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
            console.error(`[API Error] ${endpoint}:`, err);
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
        return new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", minimumFractionDigits: 0 }).format(val);
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

            // KPIs
            document.getElementById("kpi-active-users").textContent = data.users.active_users.toLocaleString();
            document.getElementById("kpi-total-users").textContent = `${data.users.total_users.toLocaleString()} total registered`;
            
            document.getElementById("kpi-platform-float").textContent = formatCurrency(data.finances.platform_float);
            document.getElementById("kpi-locked-deposits").textContent = `${formatCurrency(data.finances.total_locked_balance)} in savings locks`;

            document.getElementById("kpi-today-deposits").textContent = formatCurrency(data.deposits.today_amount);
            document.getElementById("kpi-today-deposit-count").textContent = `${data.deposits.today_count} successful STK pushes`;

            document.getElementById("kpi-today-disbursed").textContent = formatCurrency(data.payouts.today_disbursed);
            document.getElementById("kpi-today-payout-count").textContent = `${data.payouts.today_count} daily budget payouts`;

            // Alerts
            document.getElementById("alert-failed-payouts-title").textContent = `Failed Payouts: ${data.payouts.failed_count}`;
            document.getElementById("alert-locked-users-title").textContent = `Locked Out Users: ${data.users.locked_users_count}`;

            // Sidebar Badges
            document.getElementById("badge-users-count").textContent = data.users.total_users;
            const depBadge = document.getElementById("badge-pending-deposits");
            if (data.deposits.pending_count > 0) {
                depBadge.textContent = data.deposits.pending_count;
                depBadge.style.display = "";
            } else {
                depBadge.style.display = "none";
            }

            const payBadge = document.getElementById("badge-failed-payouts");
            if (data.payouts.failed_count > 0) {
                payBadge.textContent = data.payouts.failed_count;
                payBadge.style.display = "";
            } else {
                payBadge.style.display = "none";
            }

            // Render Charts
            renderOverviewCharts(data);
        } catch (err) {
            showToast("Failed to load overview metrics", "error");
        }
    }

    function renderOverviewCharts(data) {
        if (!window.Chart) return;

        // Chart 1: Platform Float Allocation
        const ctxFloat = document.getElementById("chart-float-distribution");
        if (ctxFloat) {
            if (state.charts.float) state.charts.float.destroy();
            state.charts.float = new window.Chart(ctxFloat, {
                type: "doughnut",
                data: {
                    labels: ["Available Liquidity", "Locked Savings"],
                    datasets: [{
                        data: [data.finances.total_available_balance, data.finances.total_locked_balance],
                        backgroundColor: ["#3b82f6", "#8b5cf6"],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "bottom", labels: { color: "#9ca3af" } }
                    }
                }
            });
        }

        // Chart 2: 7-Day Cashflow Velocity (Line Chart)
        const ctxVelocity = document.getElementById("chart-cashflow-velocity");
        if (ctxVelocity) {
            if (state.charts.velocity) state.charts.velocity.destroy();
            const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
            state.charts.velocity = new window.Chart(ctxVelocity, {
                type: "line",
                data: {
                    labels: days,
                    datasets: [
                        {
                            label: "Deposits (Inflow)",
                            data: [12000, 19000, 15000, 25000, 22000, 30000, data.deposits.today_amount || 28000],
                            borderColor: "#10b981",
                            backgroundColor: "rgba(16, 185, 129, 0.1)",
                            fill: true,
                            tension: 0.3
                        },
                        {
                            label: "Disbursements (Outflow)",
                            data: [8000, 11000, 10000, 14000, 16000, 18000, data.payouts.today_disbursed || 15000],
                            borderColor: "#f59e0b",
                            backgroundColor: "rgba(245, 158, 11, 0.1)",
                            fill: true,
                            tension: 0.3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "bottom", labels: { color: "#9ca3af" } }
                    },
                    scales: {
                        x: { ticks: { color: "#9ca3af" }, grid: { color: "rgba(255,255,255,0.05)" } },
                        y: { ticks: { color: "#9ca3af" }, grid: { color: "rgba(255,255,255,0.05)" } }
                    }
                }
            });
        }
    }

    // --- VIEW: USERS 360 ---
    async function loadUsersData() {
        const tbody = document.getElementById("users-table-body");
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-8">Fetching customer records...</td></tr>`;

        const search = document.getElementById("users-search-input").value.trim();
        const status = document.getElementById("users-status-filter").value;
        const page = state.pagination.users.page;

        let query = `/api/admin/users?page=${page}&limit=${state.pagination.users.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;
        if (status) query += `&status=${encodeURIComponent(status)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.users.total = data.total;

            if (!data.users || data.users.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-8">No customer accounts match your filter criteria.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.users.map(u => `
                <tr>
                    <td>
                        <div class="user-cell">
                            <strong>${escapeHtml(u.name || u.email)}</strong>
                            <div class="text-dim text-xs">${escapeHtml(u.email)}</div>
                        </div>
                    </td>
                    <td><span class="font-mono">${escapeHtml(u.phone_number)}</span></td>
                    <td><strong>${formatCurrency(u.wallet.available_balance)}</strong></td>
                    <td>${formatCurrency(u.settings.daily_budget)} / day</td>
                    <td>
                        ${u.security.is_account_locked 
                            ? `<span class="status-pill pill-danger"><i data-lucide="lock"></i> Locked Out</span>` 
                            : `<span class="status-pill pill-success"><i data-lucide="check"></i> Normal</span>`}
                        ${u.security.is_deposit_locked ? `<span class="status-pill pill-warning ml-1">Deposit Lock</span>` : ""}
                    </td>
                    <td>
                        <button class="btn btn-secondary btn-sm btn-inspect-user" data-user-id="${u.id}">
                            <i data-lucide="eye"></i> Inspect 360°
                        </button>
                    </td>
                </tr>
            `).join("");

            // Update Pagination UI
            updatePaginationInfo("users");
            if (window.lucide) window.lucide.createIcons();
        } catch {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-8">Error loading customer directory.</td></tr>`;
        }
    }

    // --- VIEW: FINANCES & WALLETS ---
    async function loadWalletsData() {
        const tbody = document.getElementById("wallets-table-body");
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-8">Loading customer ledger...</td></tr>`;

        const search = document.getElementById("wallets-search-input").value.trim();
        const page = state.pagination.finances.page;

        let query = `/api/admin/finances/wallets?page=${page}&limit=${state.pagination.finances.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.finances.total = data.total;

            if (!data.wallets || data.wallets.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-8">No wallet records found.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.wallets.map(w => `
                <tr>
                    <td>
                        <strong>${escapeHtml(w.name || w.email)}</strong>
                        <div class="text-dim text-xs">${escapeHtml(w.phone_number)}</div>
                    </td>
                    <td class="text-emerald font-mono font-bold">${formatCurrency(w.wallet.available_balance)}</td>
                    <td class="text-purple font-mono">${formatCurrency(w.wallet.locked_balance)}</td>
                    <td>${formatCurrency(w.settings.daily_budget)}</td>
                    <td><span class="badge-neutral">${w.wallet.currency}</span></td>
                    <td>
                        <div class="btn-group rbac-finops">
                            <button class="btn btn-secondary btn-sm btn-action-adjust" data-user-id="${w.user_id}" data-name="${escapeHtml(w.email)}">
                                Adjust
                            </button>
                        </div>
                    </td>
                </tr>
            `).join("");

            updatePaginationInfo("finances");
            if (window.lucide) window.lucide.createIcons();
        } catch {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-8">Error loading platform finances.</td></tr>`;
        }
    }

    // --- VIEW: DEPOSITS & STK ---
    async function loadDepositsData() {
        const tbody = document.getElementById("deposits-table-body");
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">Loading deposit records...</td></tr>`;

        const search = document.getElementById("deposits-search-input").value.trim();
        const status = document.getElementById("deposits-status-filter").value;
        const page = state.pagination.deposits.page;

        let query = `/api/admin/deposits?page=${page}&limit=${state.pagination.deposits.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;
        if (status) query += `&status=${encodeURIComponent(status)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.deposits.total = data.total;

            if (!data.deposits || data.deposits.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">No deposit transactions found.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.deposits.map(d => {
                let pillClass = "pill-neutral";
                if (d.status === "COMPLETED") pillClass = "pill-success";
                if (d.status === "FAILED") pillClass = "pill-danger";
                if (d.status === "PENDING") pillClass = "pill-warning";

                return `
                    <tr>
                        <td class="font-mono text-xs">${escapeHtml(d.checkout_request_id)}</td>
                        <td>
                            <div>${escapeHtml(d.user_email || d.phone_number)}</div>
                        </td>
                        <td class="font-mono font-bold">${formatCurrency(d.amount)}</td>
                        <td><span class="status-pill ${pillClass}">${d.status}</span></td>
                        <td class="font-mono">${escapeHtml(d.mpesa_receipt || "-")}</td>
                        <td class="text-dim text-xs">${formatDate(d.created_at)}</td>
                        <td>
                            <div class="btn-group rbac-finops">
                                ${d.status === "PENDING" ? `
                                    <button class="btn btn-secondary btn-sm btn-deposit-requery" data-checkout="${d.checkout_request_id}">Requery</button>
                                    <button class="btn btn-secondary btn-sm btn-deposit-settle" data-checkout="${d.checkout_request_id}">Manual Settle</button>
                                ` : `<span class="text-dim text-xs">-</span>`}
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");

            updatePaginationInfo("deposits");
            if (window.lucide) window.lucide.createIcons();
        } catch {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-8">Error loading deposit pipeline.</td></tr>`;
        }
    }

    // --- VIEW: PAYOUTS & DISBURSEMENTS ---
    async function loadPayoutsData() {
        const tbody = document.getElementById("payouts-table-body");
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">Loading disbursement records...</td></tr>`;

        const search = document.getElementById("payouts-search-input").value.trim();
        const status = document.getElementById("payouts-status-filter").value;
        const page = state.pagination.payouts.page;

        let query = `/api/admin/payouts?page=${page}&limit=${state.pagination.payouts.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;
        if (status) query += `&status=${encodeURIComponent(status)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.payouts.total = data.total;

            if (!data.payouts || data.payouts.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">No payout transactions found.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.payouts.map(p => {
                let pillClass = "pill-neutral";
                if (p.status === "COMPLETED" || p.status === "SUCCESS") pillClass = "pill-success";
                if (p.status === "FAILED") pillClass = "pill-danger";
                if (p.status === "PENDING") pillClass = "pill-warning";

                return `
                    <tr>
                        <td class="font-mono text-xs">${escapeHtml(p.payout_date || "-")}</td>
                        <td>${escapeHtml(p.user_email || "-")}</td>
                        <td class="font-mono">${escapeHtml(p.phone_number)}</td>
                        <td class="font-mono font-bold">${formatCurrency(p.amount)}</td>
                        <td><span class="status-pill ${pillClass}">${p.status}</span></td>
                        <td class="font-mono text-xs">${escapeHtml(p.transaction_id || p.conversation_id || "-")}</td>
                        <td>
                            <div class="btn-group rbac-finops">
                                ${p.status === "FAILED" ? `
                                    <button class="btn btn-secondary btn-sm btn-payout-retry" data-id="${p.id}">Retry</button>
                                    <button class="btn btn-secondary btn-sm btn-payout-settle" data-id="${p.id}">Mark Settled</button>
                                ` : `<span class="text-dim text-xs">-</span>`}
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");

            updatePaginationInfo("payouts");
            if (window.lucide) window.lucide.createIcons();
        } catch {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-8">Error loading payouts pipeline.</td></tr>`;
        }
    }

    // --- VIEW: AUDIT LOGS ---
    async function loadAuditLogsData() {
        const tbody = document.getElementById("audit-table-body");
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">Loading compliance audit logs...</td></tr>`;

        const search = document.getElementById("audit-search-input").value.trim();
        const action = document.getElementById("audit-action-filter").value;
        const page = state.pagination.audit.page;

        let query = `/api/admin/audit/logs?page=${page}&limit=${state.pagination.audit.limit}`;
        if (search) query += `&search=${encodeURIComponent(search)}`;
        if (action) query += `&action=${encodeURIComponent(action)}`;

        try {
            const data = await apiRequest(query);
            state.pagination.audit.total = data.total;

            if (!data.logs || data.logs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-8">No audit logs recorded for this criteria.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.logs.map(l => `
                <tr>
                    <td class="text-dim text-xs font-mono">${formatDate(l.created_at)}</td>
                    <td><strong>${escapeHtml(l.admin_email || "System/CLI")}</strong></td>
                    <td><span class="badge-neutral font-mono text-xs">${escapeHtml(l.action)}</span></td>
                    <td>${l.target_type ? `${l.target_type} #${l.target_id || ""}` : "-"}</td>
                    <td>${escapeHtml(l.reason || "-")}</td>
                    <td class="font-mono text-xs">${escapeHtml(l.ip_address || "-")}</td>
                    <td>
                        <span class="text-dim text-xs" title="${escapeHtml(l.after_state || "")}">
                            ${l.after_state ? "View Details" : "-"}
                        </span>
                    </td>
                </tr>
            `).join("");

            updatePaginationInfo("audit");
            if (window.lucide) window.lucide.createIcons();
        } catch {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-8">Error loading compliance audit trail.</td></tr>`;
        }
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
            if (state.adminUser && state.adminUser.role === "superadmin") {
                loadAdminDirectory();
            } else {
                const superCard = document.getElementById("superadmin-management-card");
                if (superCard) superCard.style.display = "none";
            }

            if (window.lucide) window.lucide.createIcons();
        } catch {
            showToast("Failed to load platform health status", "error");
        }
    }

    async function loadAdminDirectory() {
        const tbody = document.getElementById("admins-table-body");
        try {
            const data = await apiRequest("/api/admin/system/admins");
            if (!data.admins || data.admins.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-4">No other administrators found.</td></tr>`;
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
                        ${a.id !== state.adminUser.id ? `
                            <button class="btn btn-secondary btn-sm btn-toggle-admin-status" data-admin-id="${a.id}" data-active="${a.is_active}">
                                ${a.is_active ? "Deactivate" : "Activate"}
                            </button>
                        ` : `<span class="text-dim text-xs">(Current Account)</span>`}
                    </td>
                </tr>
            `).join("");
        } catch {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center text-danger py-4">Failed to load admin directory.</td></tr>`;
        }
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

        // 9. Export CSV Download Button
        const btnExportCsv = document.getElementById("btn-export-audit-csv");
        if (btnExportCsv) {
            btnExportCsv.addEventListener("click", () => {
                window.location.href = "/api/admin/audit/export";
            });
        }

        // 10. Lucide Icons Initial Call
        if (window.lucide) {
            window.lucide.createIcons();
        }
    });

})();

/**
 * Bursar 2.0 Landing Page JavaScript
 * Handles icon rendering, FAQ accordion, simulation charts, auth modal, and reCAPTCHA integration.
 */
document.addEventListener("DOMContentLoaded", () => {
    // 1. Initialize Lucide Icons
    if (window.lucide) {
        window.lucide.createIcons();
    }

    // 2. Auth Status Check (Redirect to dashboard if already authenticated)
    fetch("/api/auth/me")
        .then(res => {
            if (res.status === 200) {
                window.location.replace("/dashboard");
            }
        })
        .catch(err => console.error("Auth check failed:", err));

    // 3. FAQ Accordion (Clean Event Delegation — No inline onclick handlers)
    const faqAccordion = document.getElementById("faq-accordion");
    if (faqAccordion) {
        faqAccordion.addEventListener("click", (e) => {
            const btn = e.target.closest(".faq-question-btn");
            if (!btn) return;
            const targetItem = btn.closest(".faq-item");
            const allItems = faqAccordion.querySelectorAll(".faq-item");

            allItems.forEach(item => {
                if (item === targetItem) {
                    item.classList.toggle("active");
                } else {
                    item.classList.remove("active");
                }
            });
        });
    }

    // 4. Simulation Charts (7-Day Spending Trend)
    const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const balanceData = [7500, 6800, 6000, 5200, 4700, 4200, 3500];

    // Large Pacing Chart Widget
    const canvasLarge = document.getElementById("pacing-sim-chart");
    if (canvasLarge && window.Chart) {
        const ctx = canvasLarge.getContext("2d");
        const gradient = ctx.createLinearGradient(0, 0, 0, 160);
        gradient.addColorStop(0, "rgba(245, 158, 11, 0.4)");
        gradient.addColorStop(1, "rgba(245, 158, 11, 0.0)");

        new window.Chart(ctx, {
            type: "line",
            data: {
                labels: days,
                datasets: [{
                    label: "Wallet Balance (KES)",
                    data: balanceData,
                    fill: true,
                    backgroundColor: gradient,
                    borderColor: "rgba(245, 158, 11, 0.85)",
                    borderWidth: 2.5,
                    tension: 0.35,
                    pointRadius: 4,
                    pointBackgroundColor: "rgba(245, 158, 11, 1)",
                    pointBorderColor: "rgba(255, 255, 255, 0.2)",
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "rgba(18, 22, 37, 0.95)",
                        titleFont: { family: "Outfit", size: 11, weight: "600" },
                        bodyFont: { family: "Outfit", size: 10 },
                        borderColor: "rgba(255, 255, 255, 0.08)",
                        borderWidth: 1,
                        padding: 6,
                        callbacks: {
                            label: function (context) {
                                return ` Wallet: KES ${context.raw.toLocaleString()}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            color: "rgba(255, 255, 255, 0.5)",
                            font: { family: "Outfit", size: 9 }
                        }
                    },
                    y: {
                        grid: { color: "rgba(255, 255, 255, 0.04)" },
                        min: 2500,
                        max: 7500,
                        ticks: {
                            stepSize: 1000,
                            color: "rgba(255, 255, 255, 0.5)",
                            font: { family: "Outfit", size: 9 },
                            callback: function (value) {
                                return "KES " + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });
    }

    // Small Phone Mockup Chart
    const canvasPhone = document.getElementById("phone-sim-chart");
    if (canvasPhone && window.Chart) {
        const ctx = canvasPhone.getContext("2d");
        const gradientPhone = ctx.createLinearGradient(0, 0, 0, 90);
        gradientPhone.addColorStop(0, "rgba(245, 158, 11, 0.3)");
        gradientPhone.addColorStop(1, "rgba(245, 158, 11, 0.0)");

        new window.Chart(ctx, {
            type: "line",
            data: {
                labels: days,
                datasets: [{
                    data: balanceData,
                    fill: true,
                    backgroundColor: gradientPhone,
                    borderColor: "rgba(245, 158, 11, 0.85)",
                    borderWidth: 1.5,
                    tension: 0.35,
                    pointRadius: 2,
                    pointBackgroundColor: "rgba(245, 158, 11, 1)"
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            color: "rgba(255, 255, 255, 0.3)",
                            font: { family: "Outfit", size: 7 }
                        }
                    },
                    y: {
                        grid: { color: "rgba(255, 255, 255, 0.03)" },
                        ticks: {
                            stepSize: 2000,
                            color: "rgba(255, 255, 255, 0.3)",
                            font: { family: "Outfit", size: 7 }
                        }
                    }
                }
            }
        });
    }

    // 5. Authentication Overlay & Modal Logic
    const authOverlay = document.getElementById("auth-overlay");
    const tabLogin = document.getElementById("tab-login");
    const tabSignup = document.getElementById("tab-signup");
    const authSubmitBtn = document.getElementById("auth-submit-btn");
    const authSubtitle = document.getElementById("auth-subtitle");
    const passwordLabel = document.getElementById("password-label");
    const authPassword = document.getElementById("auth-password");
    const errorMsg = document.getElementById("auth-error-msg");
    const authForm = document.getElementById("auth-form");
    const closeBtn = document.getElementById("close-auth-btn");

    let currentAuthAction = "login";

    function showAuthOverlay(action) {
        if (!authOverlay) return;
        currentAuthAction = action;
        authOverlay.classList.add("active");
        if (errorMsg) errorMsg.style.display = "none";

        if (action === "login") {
            if (tabLogin) tabLogin.classList.add("active");
            if (tabSignup) tabSignup.classList.remove("active");
            if (authSubmitBtn) authSubmitBtn.innerText = "Log In";
            if (authSubtitle) authSubtitle.innerText = "Log in to manage your daily allowances";
            if (passwordLabel) passwordLabel.innerText = "Password PIN";
            if (authPassword) authPassword.placeholder = "Enter password (min 4 chars)";
        } else {
            if (tabSignup) tabSignup.classList.add("active");
            if (tabLogin) tabLogin.classList.remove("active");
            if (authSubmitBtn) authSubmitBtn.innerText = "Register";
            if (authSubtitle) authSubtitle.innerText = "Create an account with your Safaricom number";
            if (passwordLabel) passwordLabel.innerText = "Create Password PIN";
            if (authPassword) authPassword.placeholder = "Choose password (min 4 chars)";
        }
    }

    function closeAuthOverlay() {
        if (!authOverlay) return;
        authOverlay.classList.remove("active");
        history.replaceState(null, null, window.location.pathname);
    }

    if (tabLogin) tabLogin.addEventListener("click", () => showAuthOverlay("login"));
    if (tabSignup) tabSignup.addEventListener("click", () => showAuthOverlay("signup"));
    if (closeBtn) closeBtn.addEventListener("click", closeAuthOverlay);
    if (authOverlay) {
        authOverlay.addEventListener("click", (e) => {
            if (e.target === authOverlay) closeAuthOverlay();
        });
    }

    function handleHash() {
        const hash = window.location.hash;
        if (hash === "#login") {
            showAuthOverlay("login");
        } else if (hash === "#signup") {
            showAuthOverlay("signup");
        } else {
            if (authOverlay) authOverlay.classList.remove("active");
        }
    }
    window.addEventListener("hashchange", handleHash);
    handleHash();

    // 6. reCAPTCHA Dynamic Configuration
    let recaptchaConfig = { enabled: false, siteKey: "" };
    fetch("/api/auth/config")
        .then(res => res.json())
        .then(data => {
            if (data.recaptcha_enabled && data.recaptcha_site_key) {
                recaptchaConfig.enabled = true;
                recaptchaConfig.siteKey = data.recaptcha_site_key;
                const script = document.createElement("script");
                script.src = `https://www.google.com/recaptcha/api.js?render=${encodeURIComponent(data.recaptcha_site_key)}`;
                script.async = true;
                document.head.appendChild(script);
            }
        })
        .catch(err => console.error("Failed to load auth config:", err));

    // 7. Form Submission Handler
    if (authForm) {
        authForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (errorMsg) errorMsg.style.display = "none";

            const phone_number = document.getElementById("auth-phone").value.trim();
            const password = authPassword.value;

            let recaptcha_token = null;
            if (recaptchaConfig.enabled && window.grecaptcha && recaptchaConfig.siteKey) {
                try {
                    await new Promise(resolve => window.grecaptcha.ready(resolve));
                    recaptcha_token = await window.grecaptcha.execute(recaptchaConfig.siteKey, { action: currentAuthAction });
                } catch (gErr) {
                    console.warn("Google reCAPTCHA execution error:", gErr);
                }
            }

            const url = currentAuthAction === "login" ? "/api/auth/login" : "/api/auth/signup";

            try {
                const res = await fetch(url, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ phone_number, password, recaptcha_token })
                });

                if (res.status === 429) {
                    const submitBtn = document.getElementById("auth-submit-btn");
                    if (submitBtn) {
                        submitBtn.disabled = true;
                        let secondsLeft = parseInt(res.headers.get("Retry-After") || "60", 10);
                        const originalText = submitBtn.innerText;
                        submitBtn.innerText = `Try again in ${secondsLeft}s`;
                        const countdownTimer = setInterval(() => {
                            secondsLeft--;
                            if (secondsLeft <= 0) {
                                clearInterval(countdownTimer);
                                submitBtn.disabled = false;
                                submitBtn.innerText = originalText;
                            } else {
                                submitBtn.innerText = `Try again in ${secondsLeft}s`;
                            }
                        }, 1000);
                    }
                    throw new Error("Too many attempts. Please wait 60 seconds before trying again.");
                }

                const data = await res.json();

                if (!res.ok) {
                    throw new Error(data.detail || "Authentication request failed.");
                }

                if (currentAuthAction === "signup") {
                    currentAuthAction = "login";
                    showAuthOverlay("login");
                    authPassword.value = password;
                    authForm.dispatchEvent(new Event("submit"));
                } else {
                    window.location.replace("/dashboard");
                }
            } catch (err) {
                if (errorMsg) {
                    errorMsg.innerText = err.message;
                    errorMsg.style.display = "block";
                }
            }
        });
    }
});

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

        const confirmGroup = document.getElementById("auth-confirm-password-group");
        const confirmInput = document.getElementById("auth-confirm-password");

        if (action === "login") {
            if (tabLogin) tabLogin.classList.add("active");
            if (tabSignup) tabSignup.classList.remove("active");
            if (authSubmitBtn) authSubmitBtn.innerText = "Log In";
            if (authSubtitle) authSubtitle.innerText = "Log in to manage your daily allowances";
            if (passwordLabel) passwordLabel.innerText = "Password";
            if (authPassword) authPassword.placeholder = "Enter password (min 8 chars)";
            if (confirmGroup) confirmGroup.style.display = "none";
            if (confirmInput) confirmInput.required = false;
        } else {
            if (tabSignup) tabSignup.classList.add("active");
            if (tabLogin) tabLogin.classList.remove("active");
            if (authSubmitBtn) authSubmitBtn.innerText = "Register";
            if (authSubtitle) authSubtitle.innerText = "Create an account with your email address";
            if (passwordLabel) passwordLabel.innerText = "Create Strong Password";
            if (authPassword) authPassword.placeholder = "Password (min 8 chars, A-Z, a-z, 0-9, symbol)";
            if (confirmGroup) confirmGroup.style.display = "block";
            if (confirmInput) confirmInput.required = true;
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

    // 2FA OTP Modal Logic
    const otpOverlay = document.getElementById("otp-overlay");
    const closeOtpBtn = document.getElementById("close-otp-btn");
    const otpForm = document.getElementById("otp-form");
    const otpInput = document.getElementById("otp-input");
    const otpTimerEl = document.getElementById("otp-timer");
    const otpErrorMsg = document.getElementById("otp-error-msg");
    const otpResendBtn = document.getElementById("otp-resend-btn");
    let currentOtpEmail = "";
    let currentOtpPurpose = "login_2fa";
    let timerInterval = null;

    function openOtpOverlay(email, purpose) {
        currentOtpEmail = email;
        currentOtpPurpose = purpose;
        if (authOverlay) authOverlay.classList.remove("active");
        if (otpOverlay) otpOverlay.classList.add("active");
        if (otpErrorMsg) otpErrorMsg.style.display = "none";
        if (otpInput) {
            otpInput.value = "";
            otpInput.focus();
        }
        startOtpCountdown(300);
    }

    function closeOtpOverlay() {
        if (otpOverlay) otpOverlay.classList.remove("active");
        if (timerInterval) clearInterval(timerInterval);
    }

    if (closeOtpBtn) closeOtpBtn.addEventListener("click", closeOtpOverlay);
    if (otpOverlay) {
        otpOverlay.addEventListener("click", (e) => {
            if (e.target === otpOverlay) closeOtpOverlay();
        });
    }

    function startOtpCountdown(seconds) {
        if (timerInterval) clearInterval(timerInterval);
        let left = seconds;

        function updateDisplay() {
            const mins = Math.floor(left / 60);
            const secs = left % 60;
            if (otpTimerEl) {
                otpTimerEl.innerText = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
            }
            if (left <= 0) {
                clearInterval(timerInterval);
                if (otpTimerEl) otpTimerEl.innerText = "Expired";
            }
            left--;
        }
        updateDisplay();
        timerInterval = setInterval(updateDisplay, 1000);
    }

    if (otpResendBtn) {
        otpResendBtn.addEventListener("click", async () => {
            if (!currentOtpEmail) return;
            otpResendBtn.disabled = true;
            otpResendBtn.innerText = "Sending...";

            try {
                const res = await fetch("/api/auth/resend-otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: currentOtpEmail, purpose: currentOtpPurpose })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Resend OTP failed.");

                startOtpCountdown(300);
                if (otpErrorMsg) {
                    otpErrorMsg.innerText = "New verification code sent!";
                    otpErrorMsg.style.display = "block";
                    otpErrorMsg.style.color = "#34d399";
                }
            } catch (err) {
                if (otpErrorMsg) {
                    otpErrorMsg.innerText = err.message;
                    otpErrorMsg.style.display = "block";
                    otpErrorMsg.style.color = "#f87171";
                }
            } finally {
                setTimeout(() => {
                    if (otpResendBtn) {
                        otpResendBtn.disabled = false;
                        otpResendBtn.innerText = "Resend Code";
                    }
                }, 60000);
            }
        });
    }

    if (otpForm) {
        otpForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const otpCode = otpInput ? otpInput.value.trim() : "";
            const otpSubmitBtn = document.getElementById("otp-submit-btn");
            if (otpErrorMsg) otpErrorMsg.style.display = "none";

            if (otpSubmitBtn) {
                otpSubmitBtn.disabled = true;
                otpSubmitBtn.innerText = "Verifying...";
            }

            try {
                const csrfToken = (function getCsrfToken() {
                    const match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
                    return match ? decodeURIComponent(match[1]) : "";
                })();

                const headers = { "Content-Type": "application/json" };
                if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

                const res = await fetch("/api/auth/verify-otp", {
                    method: "POST",
                    headers: headers,
                    body: JSON.stringify({
                        email: currentOtpEmail,
                        otp_code: otpCode,
                        purpose: currentOtpPurpose
                    })
                });

                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Invalid or expired verification code.");

                closeOtpOverlay();
                window.location.replace("/dashboard");
            } catch (err) {
                if (otpSubmitBtn) {
                    otpSubmitBtn.disabled = false;
                    otpSubmitBtn.innerText = "Verify Code";
                }
                if (otpErrorMsg) {
                    otpErrorMsg.innerText = err.message;
                    otpErrorMsg.style.display = "block";
                    otpErrorMsg.style.color = "#f87171";
                }
            }
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
            const submitBtn = document.getElementById("auth-submit-btn");
            const targetErrorElement = document.getElementById("auth-error-msg");
            if (targetErrorElement) targetErrorElement.style.display = "none";

            const emailInput = document.getElementById("auth-email");
            const phoneInput = document.getElementById("auth-phone");

            let rawVal = "";
            if (emailInput && emailInput.value.trim()) {
                rawVal = emailInput.value.trim();
            } else if (phoneInput && phoneInput.value.trim()) {
                rawVal = phoneInput.value.trim();
            }

            const isEmail = rawVal.includes("@");
            const password = authPassword.value;

            if (currentAuthAction === "signup") {
                const confirmEl = document.getElementById("auth-confirm-password");
                const confirmPassword = confirmEl ? confirmEl.value : "";
                if (password !== confirmPassword) {
                    if (targetErrorElement) {
                        targetErrorElement.innerText = "Passwords do not match.";
                        targetErrorElement.style.display = "block";
                    }
                    return;
                }
            }

            const originalBtnText = submitBtn ? submitBtn.innerText : "Log In";
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerText = "Verifying...";
            }

            let recaptcha_token = null;
            if (recaptchaConfig.enabled && window.grecaptcha && recaptchaConfig.siteKey) {
                try {
                    await new Promise(resolve => window.grecaptcha.ready(resolve));
                    recaptcha_token = await window.grecaptcha.execute(recaptchaConfig.siteKey, { action: currentAuthAction });
                } catch (gErr) {
                    console.warn("Google reCAPTCHA execution error:", gErr);
                }
            }

            const csrfToken = (function getCsrfToken() {
                const match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
                return match ? decodeURIComponent(match[1]) : "";
            })();

            const url = currentAuthAction === "login" ? "/api/auth/login" : "/api/auth/signup";
            const payload = { password, recaptcha_token };
            if (isEmail) {
                payload.email = rawVal.toLowerCase();
            } else {
                payload.phone_number = rawVal;
            }

            try {
                const headers = { "Content-Type": "application/json" };
                if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

                const res = await fetch(url, {
                    method: "POST",
                    headers: headers,
                    body: JSON.stringify(payload)
                });

                const data = await res.json();

                if (res.status === 429) {
                    if (submitBtn) {
                        submitBtn.disabled = true;
                        let secondsLeft = parseInt(res.headers.get("Retry-After") || "60", 10);
                        submitBtn.innerText = `Try again in ${secondsLeft}s`;
                        const countdownTimer = setInterval(() => {
                            secondsLeft--;
                            if (secondsLeft <= 0) {
                                clearInterval(countdownTimer);
                                submitBtn.disabled = false;
                                submitBtn.innerText = originalBtnText;
                            } else {
                                submitBtn.innerText = `Try again in ${secondsLeft}s`;
                            }
                        }, 1000);
                    }
                    throw new Error(data.detail || "Too many attempts. Please try again later.");
                }

                if (!res.ok) {
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerText = originalBtnText;
                    }
                    throw new Error(data.detail || "Authentication request failed.");
                }

                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerText = originalBtnText;
                }

                if (data.status === "2fa_required" || isEmail) {
                    const purpose = currentAuthAction === "signup" ? "signup_2fa" : "login_2fa";
                    openOtpOverlay(payload.email || rawVal, purpose);
                } else {
                    if (currentAuthAction === "signup") {
                        currentAuthAction = "login";
                        showAuthOverlay("login");
                        authPassword.value = password;
                        authForm.dispatchEvent(new Event("submit"));
                    } else {
                        window.location.replace("/dashboard");
                    }
                }
            } catch (err) {
                if (submitBtn && submitBtn.innerText === "Verifying...") {
                    submitBtn.disabled = false;
                    submitBtn.innerText = originalBtnText;
                }
                if (targetErrorElement) {
                    targetErrorElement.innerText = err.message;
                    targetErrorElement.style.display = "block";
                }
            }
        });
    }

    // 8. Global Password Visibility Toggle Event Delegation
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
});

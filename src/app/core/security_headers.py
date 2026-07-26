from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Production-grade Security Headers Middleware enforcing modern OWASP security controls.
    
    1. Content-Security-Policy (CSP): Restricts origins for scripts, styles, fonts, images, frames, and connections.
       Strictly omits 'unsafe-inline' from script-src as all application code resides in bundled JS files.
       Includes frame-ancestors 'none' for modern clickjacking defense.
    2. X-Frame-Options: DENY (Legacy clickjacking defense).
    3. X-Content-Type-Options: nosniff (MIME-type sniffing prevention).
    4. Strict-Transport-Security (HSTS): Enforces HTTPS connections.
    5. Referrer-Policy: Prevents credential/session token leakage in HTTP Referer headers.
    6. Permissions-Policy: Disables unused hardware/browser features (camera, mic, geo, payment).
    7. Cross-Origin Isolation: Enforces Cross-Origin-Opener-Policy and Cross-Origin-Resource-Policy.
    8. X-XSS-Protection: 0 (Modern browsers rely on CSP; legacy XSS auditor disabled per OWASP guidance).
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # 1. Content Security Policy (CSP)
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob: https://www.google.com/recaptcha/ https://www.gstatic.com/",
            "connect-src 'self' https://www.google.com/recaptcha/ https://api.intasend.com",
            "frame-src 'self' https://www.google.com/recaptcha/ https://recaptcha.google.com/",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # 2. Frame Protection (Clickjacking Defense)
        response.headers["X-Frame-Options"] = "DENY"
        
        # 3. MIME-Sniffing Defense
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # 4. HTTPS Enforcer (HSTS)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # 5. Referrer Credential Protection
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # 6. Hardware & Feature Hijacking Protection
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        
        # 7. Cross-Origin Isolation
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        
        # 8. Legacy XSS Auditor (Disabled per OWASP guidance in favor of CSP)
        response.headers["X-XSS-Protection"] = "0"
        
        return response

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self' https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob: https://www.google.com/recaptcha/ https://www.gstatic.com/; connect-src 'self' https://www.google.com/recaptcha/ https://api.intasend.com; frame-src 'self' https://www.google.com/recaptcha/ https://recaptcha.google.com/; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-XSS-Protection": "0"
}

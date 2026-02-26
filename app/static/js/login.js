/**
 * Zero-Trust Authentication Handler.
 * Intercepts the login form to securely transmit credentials and MFA tokens via JSON.
 * On success, it securely stores the cryptographic JWT for session management.
 */
document.addEventListener("DOMContentLoaded", function() {
    const form = document.getElementById('login-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault(); // Prevent standard form submission to avoid page reloads
        
        const payload = {
            username: document.getElementById('username').value,
            password: document.getElementById('password').value,
            mfa_code: document.getElementById('mfa_code').value,
            remember_me: document.getElementById('remember_me').checked
        };

        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                const data = await res.json();
                // Securely store the JWT badge in the browser's local storage
                localStorage.setItem('bci_token', data.access_token);
                // Redirect to the main BCI dashboard
                window.location.href = '/';
            } else {
                // Display the specific security error (e.g., "Invalid MFA", "Incorrect credentials")
                const err = await res.json();
                const errorDiv = document.getElementById('login-error');
                errorDiv.innerText = err.detail;
                errorDiv.classList.remove('d-none');
            }
        } catch (error) {
            console.error("Login request failed:", error);
            const errorDiv = document.getElementById('login-error');
            errorDiv.innerText = "Network Error. Could not reach the BCI server.";
            errorDiv.classList.remove('d-none');
        }
    });
});
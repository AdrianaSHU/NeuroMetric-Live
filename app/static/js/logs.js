/**
 * Secure Vault Manager.
 * Handles the retrieval of live session logs and strictly authenticated CSV exports.
 */

// --- Secure Vault Updating ---
function updateVault() {
    const token = localStorage.getItem('bci_token');

    // 1. Client-Side Gatekeeper: Redirect to login if the badge is missing
    if (!token) {
        window.location.href = '/login';
        return;
    }

    // 2. Fetch with Cryptographic Authorisation headers
    fetch('/api/history', {
        method: 'GET',
        headers: {
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json'
        }
    })
    .then(res => {
        // 3. Handle expired or forged tokens
        if (res.status === 401 || res.status === 403) {
            localStorage.removeItem('bci_token');
            window.location.href = '/login';
            throw new Error("Session expired. Please log in again."); // Fixed Promise chain bug
        }
        return res.json();
    })
    .then(data => {
        const tbody = document.getElementById('log-body');
        if (!tbody) return; 
        
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-muted">No logs recorded yet. Waiting for active sensors...</td></tr>';
            return;
        }
        
        // 4. Optimised DOM Injection
        let newHtml = '';
        data.forEach(row => {
            newHtml += `
                <tr>
                    <td class="text-secondary small">${row.time}</td>
                    <td class="purple fw-bold">${row.fusion}</td>
                    <td>${row.details.eeg.emotion}</td>
                    <td>${row.details.face.emotion}</td>
                </tr>
            `;
        });
        
        tbody.innerHTML = newHtml;
    })
    .catch(err => {
        console.error("Vault fetch error:", err);
        const tbody = document.getElementById('log-body');
        if (tbody && err.message !== "Session expired. Please log in again.") {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-danger">Encryption Error: Unable to reach secure vault.</td></tr>';
        }
    });
}

// --- Secure CSV Export ---
async function downloadCSV() {
    const token = localStorage.getItem('bci_token');
    if (!token) {
        window.location.href = '/login';
        return;
    }

    try {
        Toastify({
            text: "Decrypting and compiling CSV...",
            duration: 2000,
            gravity: "top",
            style: { background: "#17a2b8" }
        }).showToast();

        // Fetch the file securely using the JWT token
        const response = await fetch('/api/export', {
            method: 'GET',
            headers: {
                'Authorization': 'Bearer ' + token
            }
        });

        if (!response.ok) {
            throw new Error("Unauthorized or server error");
        }

        // Convert the secure binary response into a downloadable Blob in browser memory
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        
        // Create a temporary hidden link to force the browser download
        const a = document.createElement('a');
        a.href = url;
        a.download = `bci_session_${Math.floor(Date.now() / 1000)}.csv`;
        document.body.appendChild(a);
        a.click();
        
        // Cleanup volatile memory
        a.remove();
        window.URL.revokeObjectURL(url);

    } catch (err) {
        console.error("CSV Download failed:", err);
        Toastify({
            text: "Export Failed: Secure Vault Error",
            duration: 3000,
            style: { background: "#d93025" }
        }).showToast();
    }
}

// --- Initialization ---
document.addEventListener("DOMContentLoaded", function() {
    updateVault(); // Run once immediately on page load
    
    // Auto-refresh the Vault every 2 seconds. 
    // This slow polling rate saves the Raspberry Pi's CPU from being overloaded.
    setInterval(updateVault, 2000);
});
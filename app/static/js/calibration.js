/**
 * Core BCI Calibration System.
 * Manages the UI state, dynamic stimuli injection, and strict Zero-Trust 
 * data validation before dispatching the Human-in-the-Loop (HITL) payload to the backend.
 */
const CalibrationSystem = {
    isActive: false,
    progress: 0,
    targetPoints: 150, 
    imagePool: { focus: [], neutral: [], relax: [] }, 
    
    elements: {
        guide: () => document.getElementById('calibration-guide'),
        bar: () => document.getElementById('calib-progress'),
        timer: () => document.getElementById('calib-timer'),
        status: () => document.getElementById('calib-status-text'),
        image: () => document.getElementById('calib-image-display'),
        activeId: () => document.getElementById('display-id')
    },

    /**
     * Initializes the dynamic stimuli pool.
     * Securely fetches localized image paths from the MariaDB Vault using a Bearer token.
     */
    init: async function() {
        const token = localStorage.getItem('bci_token');
        try {
            const response = await fetch('/api/calibration-images', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                this.imagePool = await response.json();
                console.log("Calibration stimuli loaded:", this.imagePool);
            }
        } catch (e) {
            console.error("Failed to load calibration images from DB:", e);
        }
    },

    /**
     * Triggers the calibration sequence.
     * Enforces strict workflow rules: A subject MUST be selected first.
     */
    start: function() {
        if (this.isActive) return;

        const activeSubject = this.elements.activeId().innerText;
        if (activeSubject === "STANDBY") {
            Toastify({
                text: "Notice: Please SELECT a subject from the database first!",
                backgroundColor: "#d93025"
            }).showToast();
            return;
        }

        this.isActive = true;
        this.progress = 0;
        
        const guide = this.elements.guide();
        if (guide) guide.classList.remove('d-none');
        
        this.updateStimuli(0);
        this.updateUI("Waiting for Neutral Face...", "#17a2b8", 0);
    },

    /**
     * Core processing loop tied to the camera's frame rate.
     * Implements an attention "Penalty Timer" to guarantee continuous high-quality baselines.
     * * @param {string} faceEmotion - The current highest-probability emotion.
     * @param {number} faceConf - The confidence score (0.0 to 1.0) of the prediction.
     */
    processFrame: function(faceEmotion, faceConf) {
        if (!this.isActive) return;

        const calibImg = this.elements.image();
        if (!calibImg) return;

        // Logic Gate: User is 'neutral' and AI is highly confident
        if (faceEmotion && faceEmotion.toLowerCase() === "neutral" && faceConf > 0.5) {
            this.progress++;
            const percent = (this.progress / this.targetPoints) * 100;

            this.updateStimuli(percent);

            const bar = this.elements.bar();
            if (bar) {
                bar.classList.remove('bg-warning', 'bg-danger');
                bar.classList.add('bg-info');
            }

            if (this.progress >= this.targetPoints) {
                this.complete();
            }
        } else {
            // --- THE PENALTY TIMER ---
            // Drains the progress bar to penalize loss of focus or micro-expressions
            if (this.progress > 0) {
                this.progress -= 0.5; 
            }
            const percent = Math.max(0, (this.progress / this.targetPoints) * 100);

            this.updateUI("Paused: Keep Face Neutral!", "#dc3545", percent);
            
            const bar = this.elements.bar();
            if (bar) {
                bar.classList.remove('bg-info');
                bar.classList.add('bg-danger');
            }
        }
    },



    /**
     * Psychological Pacing.
     * Cycles through the three distinct phases of cognitive baseline generation.
     */
    updateStimuli: function(percent) {
        const calibImg = this.elements.image();
        if (!calibImg) return;

        let phase = 'focus';
        let label = "Phase 1: Focus on the Target";

        if (percent >= 33 && percent < 66) {
            phase = 'neutral';
            label = "Phase 2: Maintain Empty Mind";
        } else if (percent >= 66) {
            phase = 'relax';
            label = "Phase 3: Deep Relaxation";
        }

        const pool = this.imagePool[phase];
        if (pool && pool.length > 0) {
            const currentSrc = calibImg.getAttribute('src');
            if (!pool.includes(currentSrc)) {
                calibImg.src = pool[Math.floor(Math.random() * pool.length)];
            }
        }

        this.updateUI(label, "#28a745", percent);
    },

    updateUI: function(text, color, percent) {
        const timer = this.elements.timer();
        if (timer) {
            timer.innerText = text;
            timer.style.color = color;
        }
        
        if (percent !== null) {
            const bar = this.elements.bar();
            if (bar) bar.style.width = percent + "%";
        }
    },

    /**
     * Completion Phase & Backend Sync.
     * Prompts the researcher for confirmation, then dispatches the signal to FastAPI.
     * Notice: The raw data is NOT sent here. The backend pulls it directly from RAM (Zero-Trust).
     */
    complete: function() {
        this.isActive = false;
        
        const guide = this.elements.guide();
        if (guide) guide.classList.add('d-none');
        
        const activeSubject = this.elements.activeId().innerText;

        // --- HUMAN-IN-THE-LOOP (HITL) DIALOG ---
        const confirmMsg = `Calibration Complete for ${activeSubject}.\n\nApply a 0.001 adaptive update to the neural baseline?`;
        const shouldUpdate = confirm(confirmMsg);

        const token = localStorage.getItem('bci_token');
        


        // Dispatches the boolean validation payload to the backend
        fetch('/api/calibrate-done', { 
            method: 'POST', 
            headers: { 
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                subject_id: activeSubject,
                apply_update: shouldUpdate,
                learning_rate: 0.001
            })
        })
        .then(response => response.json())
        .then(data => {
            Toastify({
                text: shouldUpdate ? "MODEL ADAPTED (+0.001)" : "BASELINE SAVED (NO UPDATE)",
                duration: 4000,
                backgroundColor: shouldUpdate ? "#6f42c1" : "#00b09b"
            }).showToast();
        })
        .catch(err => console.error("Calibration sync failed:", err));
    },

    stop: function() {
        this.isActive = false;
        const guide = this.elements.guide();
        if (guide) guide.classList.add('d-none');
    }
};

document.addEventListener('DOMContentLoaded', () => CalibrationSystem.init());
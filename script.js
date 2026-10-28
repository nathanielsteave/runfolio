// Data Resmi Race Nathaniel
const racesData = [
    {
        name: "Amaze Glow Run The Park",
        category: "5K",
        date: "November 2024",
        time: "31m 52s",
        pace: "6:22 /km",
        location: "Solo",
        badge: "Night Run",
        description: "Race malam hari yang seru sebagai fondasi awal konsistensi lari."
    },
    {
        name: "Mangkunegaran Run",
        category: "5K",
        date: "April 2025",
        time: "28m 56s",
        pace: "5:47 /km",
        location: "Pura Mangkunegaran, Solo",
        badge: "Sub-30 5K",
        description: "Berhasil menembus target sub-30 untuk jarak 5 kilometer."
    },
    {
        name: "Soekarno Run SOC",
        category: "5K",
        date: "June 2025",
        time: "25m 36s",
        pace: "5:07 /km",
        location: "Solo",
        badge: "Personal Best (5K)",
        description: "Peningkatan performa kecepatan yang signifikan dengan cadence stabil."
    },
    {
        name: "Solo Run Fest",
        category: "10K",
        date: "September 2025",
        time: "57m 14s",
        pace: "5:43 /km",
        location: "Solo",
        badge: "Sub-1 Hour 10K",
        description: "Debut jarak 10K resmi pertama yang sukses finis di bawah 1 jam."
    },
    {
        name: "Gapuro to Gapuro",
        category: "17K",
        date: "January 2026",
        time: "1h 52m",
        pace: "6:35 /km",
        location: "Solo / Sekitarnya",
        badge: "Long Endurance",
        description: "Latihan jarak jauh yang menguji ketahanan mental dan fisik sebelum masuk fase HM."
    },
    {
        name: "Mangkunegaran Run",
        category: "HM (21.1K)",
        date: "May 2026",
        time: "2h 19m",
        pace: "6:35 /km",
        location: "Pura Mangkunegaran, Solo",
        badge: "Major Milestone (PB HM)",
        description: "Pencapaian puncak menaklukkan rute Half Marathon dengan strategi fueling dan pacing matang."
    }
];

// Render Race Cards ke DOM
const renderRaces = () => {
    const grid = document.getElementById('race-grid');
    if (!grid) return;

    grid.innerHTML = racesData.map(race => `
        <div class="race-card">
            <div>
                <div class="race-header">
                    <span class="race-badge">${race.category} • ${race.badge}</span>
                    <span class="race-date">${race.date}</span>
                </div>
                <h3 class="race-title">${race.name}</h3>
                <p class="race-desc"><i class="fa-solid fa-location-dot" style="color: var(--accent);"></i> ${race.location}</p>
                <div class="race-metrics">
                    <div class="metric-item">
                        <span class="metric-value">${race.time}</span>
                        <span class="metric-label">Finish Time</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-value">${race.pace}</span>
                        <span class="metric-label">Avg Pace</span>
                    </div>
                </div>
                <p class="race-desc">${race.description}</p>
            </div>
        </div>
    `).join('');
};

document.addEventListener('DOMContentLoaded', () => {
    renderRaces();
    console.log("🏃‍♂️ Runfolio successfully initialized!");
});
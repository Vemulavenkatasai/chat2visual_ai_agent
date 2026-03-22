async function send() {
    const input = document.getElementById("query");
    const query = input.value.trim();

    if (!query) return;

    addMessage(query, "user");
    input.value = "";

    try {
        const res = await fetch("http://127.0.0.1:8000/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ query })
        });

        const data = await res.json();

        // 🔥 ERROR HANDLE
        if (data.error) {
            addMessage("Error: " + data.error, "bot");
            return;
        }

        // ✅ Create bot message container
        const botMsg = addMessage(data.title, "bot");

        // ✅ Create chart box
        const chartBox = document.createElement("div");
        chartBox.className = "chart-box";

        const canvas = document.createElement("canvas");

        chartBox.appendChild(canvas);
        botMsg.appendChild(chartBox);

        // ✅ Draw chart (no destroy)
        drawChart(canvas, data);

    } catch (error) {
        addMessage("Backend connection failed ❌", "bot");
        console.error(error);
    }
}

// ✅ FIXED: No global chart instance
function drawChart(canvas, data) {
    new Chart(canvas, {
        type: data.chart,
        data: {
            labels: data.labels,
            datasets: [{
                label: data.title,
                data: data.values,
                borderWidth: 2,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });
}

// ✅ Improved message UI
function addMessage(text, type) {
    const chat = document.getElementById("chat");

    const div = document.createElement("div");
    div.className = "message " + type;

    const content = document.createElement("div");
    content.innerText = text;

    div.appendChild(content);
    chat.appendChild(div);

    chat.scrollTop = chat.scrollHeight;

    return div;
}

// ✅ BONUS: Enter key support
document.getElementById("query").addEventListener("keypress", function(e) {
    if (e.key === "Enter") {
        send();
    }
});
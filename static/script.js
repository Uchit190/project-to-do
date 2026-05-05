document.addEventListener("DOMContentLoaded", function () {

    const taskInput  = document.getElementById("taskInput");
    const addBtn     = document.getElementById("addBtn");
    const taskList   = document.getElementById("taskList");
    const emptyState = document.getElementById("emptyState");
    const footer     = document.getElementById("footer");
    const taskCount  = document.getElementById("taskCount");
    const clearBtn   = document.getElementById("clearBtn");
    const filterBtns = document.querySelectorAll(".filter-btn");

    let currentFilter = "all";

    // ── Load tasks on page load ──
    loadTasks();

    // ── Add task on button click ──
    addBtn.addEventListener("click", addTask);

    // ── Add task on Enter key ──
    taskInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") addTask();
    });

    // ── Filter buttons ──
    filterBtns.forEach(btn => {
        btn.addEventListener("click", function () {
            filterBtns.forEach(b => b.classList.remove("active"));
            this.classList.add("active");
            currentFilter = this.dataset.filter;
            loadTasks();
        });
    });

    // ── Clear completed ──
    clearBtn.addEventListener("click", function () {
        fetch("/tasks/clear-completed", { method: "DELETE" })
            .then(r => r.json())
            .then(() => loadTasks())
            .catch(console.error);
    });

    // ── Functions ──

    function loadTasks() {
        fetch("/tasks")
            .then(r => r.json())
            .then(data => renderTasks(data.tasks))
            .catch(console.error);
    }

    function addTask() {
        const text = taskInput.value.trim();
        if (!text) {
            taskInput.focus();
            taskInput.style.borderColor = "#e06c75";
            setTimeout(() => { taskInput.style.borderColor = ""; }, 1000);
            return;
        }

        fetch("/tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text })
        })
        .then(r => r.json())
        .then(() => {
            taskInput.value = "";
            taskInput.focus();
            loadTasks();
        })
        .catch(console.error);
    }

    function toggleTask(id, completed) {
        fetch(`/tasks/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ completed })
        })
        .then(r => r.json())
        .then(() => loadTasks())
        .catch(console.error);
    }

    function deleteTask(id) {
        fetch(`/tasks/${id}`, { method: "DELETE" })
            .then(r => r.json())
            .then(() => loadTasks())
            .catch(console.error);
    }

    function renderTasks(tasks) {
        // Filter
        let filtered = tasks;
        if (currentFilter === "active")    filtered = tasks.filter(t => !t.completed);
        if (currentFilter === "completed") filtered = tasks.filter(t => t.completed);

        taskList.innerHTML = "";

        if (filtered.length === 0) {
            const li = document.createElement("li");
            li.className = "empty-state";
            li.id = "emptyState";
            li.innerHTML = `<span class="empty-icon">✦</span><span>${
                tasks.length === 0
                    ? "No tasks yet. Add one above!"
                    : "No " + currentFilter + " tasks."
            }</span>`;
            taskList.appendChild(li);
        } else {
            filtered.forEach(task => {
                const li = document.createElement("li");
                li.className = "task-item" + (task.completed ? " completed" : "");
                li.dataset.id = task.id;
                li.innerHTML = `
                    <input type="checkbox" class="task-check" ${task.completed ? "checked" : ""} aria-label="Mark done" />
                    <span class="task-text">${escapeHTML(task.text)}</span>
                    <button class="delete-btn" aria-label="Delete task">✕</button>
                `;

                li.querySelector(".task-check").addEventListener("change", function () {
                    toggleTask(task.id, this.checked);
                });
                li.querySelector(".delete-btn").addEventListener("click", function () {
                    li.style.opacity = "0";
                    li.style.transform = "translateX(30px)";
                    li.style.transition = "opacity 0.25s, transform 0.25s";
                    setTimeout(() => deleteTask(task.id), 250);
                });

                taskList.appendChild(li);
            });
        }

        // Footer
        const activeCount = tasks.filter(t => !t.completed).length;
        const hasCompleted = tasks.some(t => t.completed);
        footer.style.display = tasks.length > 0 ? "flex" : "none";
        taskCount.textContent = activeCount === 1 ? "1 task left" : `${activeCount} tasks left`;
        clearBtn.style.display = hasCompleted ? "inline" : "none";
    }

    function escapeHTML(str) {
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

});

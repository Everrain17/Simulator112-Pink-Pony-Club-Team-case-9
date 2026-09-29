let localCreatedIncidents = JSON.parse(localStorage.getItem("arm_saved_incidents")) || [];
let CURRENT_STUDENT_ID = "";
let CURRENT_STUDENT_DB_ID = null;
let CURRENT_STUDENT_NAME = "";
let CURRENT_ARM = "";

const PYTHON_API_BASE =
    window.SYSTEM112_PYTHON_API_BASE ||
    `${window.location.protocol}//${window.location.hostname}:8010/api/v1`;

let accessToken =
    localStorage.getItem("system112_access_token") || "";

const urlParams =
    new URLSearchParams(window.location.search);

const launcherToken =
    urlParams.get("token");

const launcherStudentId =
    urlParams.get("studentId");

const launcherStudentName =
    urlParams.get("studentName");

const launcherArm =
    urlParams.get("arm");

if (launcherToken) {
    accessToken = launcherToken;

    localStorage.setItem(
        "system112_access_token",
        accessToken
    );
}

const ACTIVE_SESSION_ID = (() => {
    const fromUrl = new URLSearchParams(window.location.search).get("sessionId");
    const raw = fromUrl ?? localStorage.getItem("arm112_active_session_id");
    const value = raw ? Number(raw) : NaN;
    return Number.isFinite(value) && value > 0 ? value : null;
})();
let allData = [];
const activeCallMeta = new Map();
function generateIncidentNumber(callId) {
    const timestamp = Date.now().toString().slice(-8);
    const callPart = String(callId || "")
        .replace(/\D/g, "")
        .slice(-4)
        .padStart(4, "0");
    return `${timestamp}-${callPart}`;
}
async function loadCurrentStudent() {
    if (
        launcherStudentId &&
        launcherStudentName
    ) {
        CURRENT_STUDENT_DB_ID =
            Number(launcherStudentId) || null;

        CURRENT_STUDENT_NAME =
            launcherStudentName;

        CURRENT_STUDENT_ID =
            launcherStudentName;

        CURRENT_ARM =
            launcherArm || "";

        updateStudentIdentity();
        return;
    }

    const response = await fetch(
        `${PYTHON_API_BASE}/auth/me`,
        {
            method: "GET",
            cache: "no-store",
            headers: accessToken
                ? {
                    "Authorization":
                        `Bearer ${accessToken}`
                }
                : {}
        }
    );

    if (!response.ok) {
        throw new Error(
            `Не удалось получить данные студента: HTTP ${response.status}`
        );
    }

    const me = await response.json();

    CURRENT_STUDENT_DB_ID =
        me.id ?? null;

    CURRENT_STUDENT_NAME =
        me.username || "";

    CURRENT_STUDENT_ID =
        me.username ||
        String(me.id || "");

    CURRENT_ARM =
        me.arm || "";

    updateStudentIdentity();
}

function updateStudentIdentity() {
    const studentId =
        document.getElementById("student-id");

    const studentName =
        document.getElementById("student-name");

    const armNumber =
        document.getElementById("arm-number");

    if (studentId) {
        studentId.textContent =
            (CURRENT_STUDENT_DB_ID ?? CURRENT_STUDENT_ID) || "—";
    }

    if (studentName) {
        studentName.textContent =
            CURRENT_STUDENT_NAME || "—";
    }

    if (armNumber) {
        armNumber.textContent =
            CURRENT_ARM || "АРМ —";
    }
}

function getCallMeta(call) {
    const callId = call.id;
    const callerPhone =
        call.caller?.phoneNumber ||
        call.caller?.PhoneNumber ||
        "";
    if (!activeCallMeta.has(callId)) {
        activeCallMeta.set(callId, {
            startedAt: new Date(),
            incidentNumber: generateIncidentNumber(callId),
            callerPhone: callerPhone
        });
    } else if (callerPhone) {
        activeCallMeta.get(callId).callerPhone = callerPhone;
    }
    return activeCallMeta.get(callId);
}
let filtered = [];
let opened = new Set();
let selectedId = null;
let currentPage = 1;
let pageSize = 10;
let sortAsc = false;
let currentCallSecondsCounter = 0;
let callTimerInterval = null;
let visibleColumns = {
    connection: true, emergency: true, operator: true, arm: true, number: true,
    date: true, time: true, type: true, post: true, status: true, address: true, check: true
};
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, m => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[m]));
function formatDate(d) {
    return d && d.length >= 5 ? d.slice(0, 5).replaceAll("-", ".") : d;
}
function openModal(id) {
    $(id).classList.add("show");
}
function closeModal(id) {
    $(id).classList.remove("show");
}
// ==========================================================================
// РЕНДЕРИНГ ТАБЛИЦЫ И ЕЁ ДВУХЪЯРУСНЫХ ПОДСТРОК
// ==========================================================================
function render() {
    const body = $("rows");
    if (!body) return;
    body.innerHTML = "";
    const total = filtered.length;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > pages) currentPage = pages;
    const start = (currentPage - 1) * pageSize;
    const items = filtered.slice(start, start + pageSize);
    if (!items.length) {
        body.innerHTML = '<tr><td colspan="13"><div class="empty">По заданным условиям происшествия не найдены</div></td></tr>';
    }
    items.forEach((r) => {
        const tr = document.createElement("tr");
        tr.className = "main" + (r.critical ? " critical" : "") + (selectedId === r.id ? " selected" : "");
        tr.dataset.id = r.id;
        tr.innerHTML =
            `<td>${opened.has(r.id) ? "⌃" : "⌄"}</td>` +
            `<td>${r.critical ? '<span class="link">↗</span>' : '<span class="phone">♧</span>'}</td>` +
            `<td>${esc(r.emergency)}</td>` +
            `<td>${esc(r.operator)}</td>` +
            `<td>${esc(r.arm)}</td>` +
            `<td class="num">${esc(r.id)}</td>` +
            `<td>${esc(formatDate(r.date))}</td>` +
            `<td class="time">${esc(r.time)}</td>` +
            `<td>${esc(r.type)}</td>` +
            `<td>${r.description ? "Да" : "Нет"}</td>` +
            `<td class="${r.status === "Завершена" ? "done" : ""}">${esc(r.status)}</td>` +
            `<td class="address">${esc(r.address)}</td>` +
            `<td><span class="doc">${r.check ? "▣" : ""}</span><span class="check">${r.check ? "✓" : ""}</span></td>`;
        tr.onclick = e => {
            if (e.target.closest("td") && e.detail === 2) {
                selectedId = r.id;
                openIncident(r.id);
                return;
            }
            selectedId = r.id;
            opened.has(r.id) ? opened.delete(r.id) : opened.add(r.id);
            render();
        };
        tr.oncontextmenu = e => {
            e.preventDefault();
            selectedId = r.id;
            openIncident(r.id);
        };
        body.appendChild(tr);
        const d = document.createElement("tr");
        d.className = "desc";
        const desc = (r.date + " " + r.time + " Опер. " + r.operator + (r.applicant ? " Заявитель " + r.applicant : "") + " - " + r.description).trim();
        d.innerHTML = `<td></td><td colspan="12">${esc(desc)}</td>`;
        body.appendChild(d);
        if (opened.has(r.id)) {
            const x = document.createElement("tr");
            x.className = "details";
            x.innerHTML = `<td colspan="13"><div class="details-flex">
                <div><b>Адрес происшествия:</b> ${esc(r.address || "не указан")}<br><b>Тип происшествия:</b> ${esc(r.type)}<br><b>Учётный № ЕКП:</b> 38260${esc(r.id)}</div>
                <div><b>Оператор:</b> ${esc(r.operator)}<br><b>АРМ:</b> ${esc(r.arm)}<br><b>Состояние:</b> ${esc(r.status)}</div>
                <div><b>Телефон:</b> ${esc(r.phone)}<br><b>Заявитель:</b> ${esc(r.applicant || "не указан")}<br><b>Описание:</b> ${esc(r.description || "нет")}</div>
            </div></td>`;
            body.appendChild(x);
        }
    });
    $("page").textContent = currentPage;
    $("range").textContent = total ? `${start + 1}-${Math.min(start + pageSize, total)} из ${total}` : "0-0 из 0";
    $("resultInfo").textContent = `${total} записей`;
    $("prev").classList.toggle("disabled", currentPage <= 1);
    $("next").classList.toggle("disabled", currentPage >= pages);
}
function populateTypes() {
    const types = [...new Set(allData.map(x => x.type))];
    ["fType", "nType"].forEach(id => {
        const el = $(id);
        if (!el) return;
        const first = id === "fType" ? '<option>Все типы</option>' : '';
        el.innerHTML = first + types.map(t => `<option>${esc(t)}</option>`).join("");
    });
}
function applyFilters() {
    const v = id => $(id).value.trim().toLowerCase();
    filtered = allData.filter(r => {
        if (v("fNumber") && !r.id.toLowerCase().includes(v("fNumber"))) return false;
        if (v("fPhone") && !r.phone.toLowerCase().includes(v("fPhone"))) return false;
        if (v("fType") && r.type !== $("fType").value) return false;
        if (v("fStatus") && r.status !== $("fStatus").value) return false;
        if (v("fOperator") && !r.operator.toLowerCase().includes(v("fOperator"))) return false;
        if (v("fAddress") && !r.address.toLowerCase().includes(v("fAddress"))) return false;
        const text = v("fText");
        if (text && !(r.applicant + " " + r.description + " " + r.type).toLowerCase().includes(text)) return false;
        if ($("fDateFrom").value && r.date.split(".").reverse().join("-") < $("fDateFrom").value) return false;
        if ($("fDateTo").value && r.date.split(".").reverse().join("-") > $("fDateTo").value) return false;
        if ($("fTimeFrom").value && r.time < $("fTimeFrom").value) return false;
        if ($("fTimeTo").value && r.time > $("fTimeTo").value) return false;
        return true;
    });
    currentPage = 1;
    closeModal("searchModal");
    render();
}
function clearFilters() {
    ["fNumber", "fPhone", "fDateFrom", "fDateTo", "fTimeFrom", "fTimeTo", "fOperator", "fAddress", "fText"].forEach(id => {
        if ($(id)) $(id).value = "";
    });
    if ($("fType")) $("fType").value = "";
    if ($("fStatus")) $("fStatus").value = "";
    filtered = [...allData];
    currentPage = 1;
    render();
}
function openIncident(id) {
    const r = allData.find(x => x.id === id);
    if (!r) return;
    selectedId = id;
    $("incidentTitle").textContent = `Карточка происшествия № ${r.id}`;
    $("incidentBody").innerHTML = `<div class="form-grid">
        <div class="field"><label>Номер</label><input id="eId" value="${esc(r.id)}" readonly></div>
        <div class="field"><label>Статус</label><select id="eStatus">${["Отработана", "Завершена", "Проверена", "В работе"].map(s => `<option ${s === r.status ? "selected" : ""}>${s}</option>`).join("")}</select></div>
        <div class="field"><label>Тип происшествия</label><select id="eType">${[...new Set(allData.map(x => x.type))].map(s => `<option ${s === r.type ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>
        <div class="field"><label>Оператор</label><input id="eOperator" value="${esc(r.operator)}"></div>
        <div class="field"><label>Телефон</label><input id="ePhone" value="${esc(r.phone)}"></div>
        <div class="field"><label>Заявитель</label><input id="eApplicant" value="${esc(r.applicant)}"></div>
        <div class="field full"><label>Адрес</label><input id="eAddress" value="${esc(r.address)}"></div>
        <div class="field full"><label>Описание</label><textarea id="eDescription">${esc(r.description)}</textarea></div>
    </div>`;
    openModal("incidentModal");
}
function saveIncident() {
    const r = allData.find(x => x.id === selectedId);
    if (!r) return;
    r.status = $("eStatus").value;
    r.type = $("eType").value;
    r.operator = $("eOperator").value;
    r.phone = $("ePhone").value;
    r.applicant = $("eApplicant").value;
    r.address = $("eAddress").value;
    r.description = $("eDescription").value;
    localCreatedIncidents = localCreatedIncidents.map(x => x.id === r.id ? r : x);
    localStorage.setItem("arm_saved_incidents", JSON.stringify(localCreatedIncidents)); // Пишем в localStorage
    filtered = filtered.map(x => x.id === r.id ? r : x);
    closeModal("incidentModal");
    render();
}
function createIncident() {
    const now = new Date();
    const pad = n => String(n).padStart(2, "0");
    const id = String(Math.floor(100 + Math.random() * 899));
    const r = {
        id,
        phone: $("nPhone").value || "",
        operator: CURRENT_STUDENT_ID,
        time: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
        type: $("nType").value,
        emergency: "Нет",
        status: "В работе",
        address: $("nAddress").value,
        applicant: $("nApplicant").value,
        description: $("nDescription").value,
        date: `${pad(now.getDate())}.${pad(now.getMonth() + 1)}.${now.getFullYear()}`,
        arm: CURRENT_ARM,
        check: false
    };
    localCreatedIncidents.unshift(r);
    localStorage.setItem("arm_saved_incidents", JSON.stringify(localCreatedIncidents));
    allData = [...localCreatedIncidents];
    filtered = [...allData];
    currentPage = 1;
    closeModal("newModal");
    render();
    $("nPhone").value = $("nAddress").value = $("nApplicant").value = $("nDescription").value = "";
}
function updateClock() {
    const now = new Date();
    const months = ["ЯНВАРЯ", "ФЕВРАЛЯ", "МАРТА", "АПРЕЛЯ", "МАЯ", "ИЮНЯ", "ИЮЛЯ", "АВГУСТА", "СЕНТЯБРЯ", "ОКТЯБРЯ", "НОЯБРЯ", "ДЕКАБРЯ"];
    const days = ["ВОСКРЕСЕНЬЕ", "ПОНЕДЕЛЬНИК", "ВТОРНИК", "СРЕДА", "ЧЕТВЕРГ", "ПЯТНИЦА", "СУББОТА"];
    if ($("date")) {
        $("date").textContent = `${days[now.getDay()]}, ${now.getDate()} ${months[now.getMonth()]} ${now.getFullYear()}`;
    }
    if ($("clock")) {
        $("clock").textContent = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    }
    if ($("seconds")) {
        $("seconds").textContent = String(now.getSeconds()).padStart(2, "0");
    }
}
// ==========================================================================
// УПРАВЛЯЮЩИЕ ТРИГГЕРЫ И ОБРАБОТЧИКИ СОБЫТИЙ
// ==========================================================================
document.querySelectorAll("[data-close]").forEach(b => b.onclick = () => closeModal(b.dataset.close));
document.querySelectorAll(".overlay").forEach(o => o.addEventListener("mousedown", e => {
    if (e.target === o) o.classList.remove("show");
}));
if ($("advanced")) $("advanced").onclick = () => openModal("searchModal");
if ($("topSearch")) $("topSearch").onclick = () => openModal("searchModal");
if ($("miniSearch")) $("miniSearch").onclick = () => openModal("searchModal");
if ($("applyFilters")) $("applyFilters").onclick = applyFilters;
if ($("clearFilters")) $("clearFilters").onclick = clearFilters;
if ($("reset")) {
    $("reset").onclick = () => {
        clearFilters();
        $("searchModal").classList.remove("show");
    };
}
if ($("createIncident")) $("createIncident").onclick = createIncident;
if ($("saveIncident")) $("saveIncident").onclick = saveIncident;
if ($("autoToggle")) {
    $("autoToggle").onclick = function() { this.classList.toggle("on"); };
}
if ($("queueToggle")) {
    $("queueToggle").onclick = function() { this.classList.toggle("on"); };
}
if ($("newCard")) {
    // 🔥 ТРЕБОВАНИЕ 3: Кнопка «Создать новую карточку» изначально отключена стилями
    $("newCard").style.opacity = "0.4";
    $("newCard").style.cursor = "not-allowed";
	$("newCard").disabled = true;
    $("newCard").onclick = (e) => {
        e.preventDefault();
        if ($("newCard").style.cursor === "not-allowed") {
            alert("Кнопка заблокирована! Дождитесь входящего вызова Avaya и снимите трубку.");
            return;
        }
    };
}
if ($("prev")) {
    $("prev").onclick = () => {
        if (currentPage > 1) {
            currentPage--;
            render();
        }
    };
}
if ($("next")) {
    $("next").onclick = () => {
        if (currentPage < Math.ceil(filtered.length / pageSize)) {
            currentPage++;
            render();
        }
    };
}
if ($("pageSize")) {
    $("pageSize").onchange = e => {
        pageSize = +e.target.value;
        currentPage = 1;
        render();
    };
}
if ($("groupBtn")) {
    $("groupBtn").onclick = () => alert("Группы записей: текущая смена, новые, в работе, проверенные");
}
if ($("columns")) {
    $("columns").onclick = () => {
        const names = {
            connection: "Связь", emergency: "ЧС", operator: "Опер.", arm: "АРМ", number: "Номер",
            date: "Дата", time: "Время", type: "Тип происшествия", post: "Постр.", status: "Статус", address: "Адрес", check: "Проверка"
        };
        $("columnBody").innerHTML = Object.entries(names).map(([k, n]) =>
            `<label style="display:flex;align-items:center;gap:8px;height:28px;font-size:10px"><input type="checkbox" data-col="${k}" ${visibleColumns[k] ? "checked" : ""}>${n}</label>`
        ).join("");
        document.querySelectorAll("[data-col]").forEach(c => c.onchange = () => {
            visibleColumns[c.dataset.col] = c.checked;
            applyColumnVisibility();
        });
        openModal("columnModal");
    };
}
function applyColumnVisibility() {
    const map = ["connection", "emergency", "operator", "arm", "number", "date", "time", "type", "post", "status", "address", "check"];
    document.querySelectorAll(".table tr").forEach(tr =>
        map.forEach((name, i) => {
            const cell = tr.children[i + 1];
            if (cell) cell.style.display = visibleColumns[name] ? "" : "none";
        })
    );
}
if (document.querySelector(".sortable")) {
    document.querySelector(".sortable").onclick = () => {
        sortAsc = !sortAsc;
        filtered.sort((a, b) => {
            const x = a.time.localeCompare(b.time);
            return sortAsc ? x : -x;
        });
        render();
    };
}
document.querySelectorAll(".module").forEach(m => m.onclick = () => {
    document.querySelectorAll(".module").forEach(x => x.classList.remove("active"));
    m.classList.add("active");
    if (m.dataset.module !== "Журнал") {
        alert(`Модуль «${m.dataset.module}» открыт в режиме фронтенда.`);
    }
});
// ==========================================================================
// ИНТЕГРАЦИЯ С КАРТОЧКОЙ И WEBSOCKET
// ==========================================================================
// 🔥 ТРЕБОВАНИЕ 2: Больше никаких случайных ID! Передаем точный C# id звонка во вкладку
function openIncidentCard(callId) {
    const callMeta = activeCallMeta.get(callId);

    const incidentNumber =
        callMeta?.incidentNumber || "";

    const startedAt =
        callMeta?.startedAt
            ? callMeta.startedAt.toISOString()
            : "";

    const callerPhone =
        callMeta?.callerPhone || "";

    const url =
        `card.html` +
        `?callId=${encodeURIComponent(callId)}` +
        `&studentId=${encodeURIComponent(CURRENT_STUDENT_ID)}` +
        `&incidentNumber=${encodeURIComponent(incidentNumber)}` +
        `&startedAt=${encodeURIComponent(startedAt)}` +
        `&callerPhone=${encodeURIComponent(callerPhone)}` +
        `${ACTIVE_SESSION_ID
            ? `&sessionId=${encodeURIComponent(ACTIVE_SESSION_ID)}`
            : ""}`;

    console.log(
        "[CARD] Открытие карточки:",
        callId
    );

    currentCardWindow = window.open(
        url,
        "incident-card",
        "width=1000,height=650,resizable=yes,scrollbars=yes"
    );

    if (!currentCardWindow) {
        alert(
            "Разрешите всплывающие окна в браузере"
        );
    }
}
window.addEventListener("message", (event) => {
    if (!event.data) return;
	if (event.data.type === "CARD_SAVED") {
		const callId =
			event.data.data?.callId;
			
			if (callId === activeSocketCallId) {
				currentCallCardSaved = true;
			}

		if ($("newCard")) {
			$("newCard").style.opacity = "0.4";
			$("newCard").disabled = true;
			$("newCard").style.cursor = "not-allowed";

			$("newCard").onclick = (e) => {
				e.preventDefault();

				alert(
					"Карточка этого звонка уже сохранена."
				);
			};
		}

		fetchSystemState();

		console.log(
			`[АРМ] Карточка ${callId || "UNKNOWN"} сохранена. Звонок продолжается, повторное открытие карточки запрещено.`
		);
}
});
let activeSocketCallId = null;
let currentCardWindow = null;
let currentCallCardSaved = false;

function showCurrentCallWidget(callId, callerPhone) {
    const widget = $("avayaWidget");
    const number = $("avayaWidgetNumber");
    const hangup = $("btnHangupCall");

    if (!widget) return;

    if (number) {
        number.textContent =
            callerPhone || "Неизвестно";
    }

    if (hangup) {
        hangup.disabled = false;
        hangup.textContent = "Завершить звонок";
        hangup.onclick = () => hangupCurrentCall();
    }

    widget.style.display = "block";

    console.log(
        "[AVAYA] Показано окно текущего звонка:",
        callId,
        callerPhone
    );
}

async function hangupCurrentCall() {
    const callId = activeSocketCallId;

    if (!callId) {
        return;
    }

    try {
        const response = await fetch(
            `${PYTHON_API_BASE}/runtime/calls/${encodeURIComponent(callId)}/finish`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                }
            }
        );

        if (!response.ok) {
            const text = await response.text();

            throw new Error(
                text || `HTTP ${response.status}`
            );
        }

        if (
            currentCardWindow &&
            !currentCardWindow.closed
        ) {
            currentCardWindow.close();
        }

        activeSocketCallId = null;
		currentCallCardSaved = false;
        stopVoiceStreaming();
        hideCurrentCallWidget();

        if ($("newCard")) {
            $("newCard").style.opacity = "0.4";
			$("newCard").disabled = true;
            $("newCard").style.cursor = "not-allowed";
        }

        await fetchSystemState();

        console.log(
            `[АРМ] Звонок ${callId} завершён.`
        );

    } catch (error) {
        console.error(
            "[АРМ] Ошибка завершения звонка:",
            error
        );

        alert(
            `Не удалось завершить звонок.\n\n${error.message}`
        );
    }
}

function hideCurrentCallWidget() {
    const widget = $("avayaWidget");

    if (widget) {
        widget.style.display = "none";
    }
}

function initAvayaWidgetDrag() {
    const widget = $("avayaWidget");
    const header = $("avayaWidgetHeader");

    if (!widget || !header) return;

    let dragging = false;
    let offsetX = 0;
    let offsetY = 0;

    header.addEventListener("mousedown", e => {
        dragging = true;

        const rect =
            widget.getBoundingClientRect();

        offsetX = e.clientX - rect.left;
        offsetY = e.clientY - rect.top;

        widget.style.left = `${rect.left}px`;
        widget.style.top = `${rect.top}px`;

        e.preventDefault();
    });

    document.addEventListener("mousemove", e => {
        if (!dragging) return;

        let left = e.clientX - offsetX;
        let top = e.clientY - offsetY;

        left = Math.max(
            0,
            Math.min(
                left,
                window.innerWidth - widget.offsetWidth
            )
        );

        top = Math.max(
            0,
            Math.min(
                top,
                window.innerHeight - widget.offsetHeight
            )
        );

        widget.style.left = `${left}px`;
        widget.style.top = `${top}px`;
    });

    document.addEventListener("mouseup", () => {
        dragging = false;
    });
}
async function fetchSystemState() {
    try {
        const response = await fetch(`${PYTHON_API_BASE}/runtime/state`, { cache: "no-store" });
        if (!response.ok) return;
        const data = await response.json();
        const container = document.getElementById("rows");
        if (!container) return;
        if (!data.isRunning) {
            container.innerHTML = '<tr><td colspan="13" class="text-center p-4">Симуляция ожидает запуска преподавателем.</td></tr>';
            return;
        }

        const savedResponse = await fetch(
            `${PYTHON_API_BASE}/runtime/calls/saved?studentId=${encodeURIComponent(CURRENT_STUDENT_ID)}`,
            { cache: "no-store" }
        );
		let serverSavedCards = [];
		if (savedResponse.ok) {
			const savedData = await savedResponse.json();
			serverSavedCards = (savedData.items || [])
				.filter(x => x.cardReceived === true && x.operatorCard)
				.map(x => x.operatorCard);
		}

        const serverCalls = (data.activeCalls || []).map(c => {
            const callMeta = getCallMeta(c);
            const pad = n => String(n).padStart(2, "0");
            const callDate =
                `${pad(callMeta.startedAt.getDate())}.` +
                `${pad(callMeta.startedAt.getMonth() + 1)}.` +
                `${callMeta.startedAt.getFullYear()}`;
            const callTime =
                `${pad(callMeta.startedAt.getHours())}:` +
                `${pad(callMeta.startedAt.getMinutes())}:` +
                `${pad(callMeta.startedAt.getSeconds())}`;
			const operator =
				c.studentId === "Свободен"
					? ""
					: (c.studentId || CURRENT_STUDENT_ID || "");

			const arm =
				c.arm ||
				c.armNumber ||
				c.operatorArm ||
				c.Arm ||
				CURRENT_ARM ||
				"";
            const fileSave = serverSavedCards.find(card =>
                (card.callId && card.callId === c.id) ||
                (card.CallId && card.CallId === c.id)
            );
            if (fileSave) {
                const cls = fileSave.classifier || fileSave.Classifier;
                const addr = fileSave.address || fileSave.Address;
                const savedType = cls?.selectedType || cls?.SelectedType || "Экстренный вызов";
                const savedNotes = fileSave.operatorNotes || fileSave.OperatorNotes || "Карточка сохранена";
                const savedRole = fileSave.applicantRole || fileSave.ApplicantRole || "Заявитель";
                const street = addr?.street || addr?.Street || "";
                const house = addr?.house || addr?.House || "";
                const savedAddress = street || house
                    ? `${street ? `ул. ${street}` : ""}${street && house ? ", " : ""}${house ? `д. ${house}` : ""}`
                    : "";
                return {
                    id: c.id,
                    incidentNumber: fileSave.incidentNumber || fileSave.IncidentNumber || callMeta.incidentNumber,
                    emergency: "Нет",
                    operator,
                    arm,
                    phone: c.caller?.phoneNumber || c.caller?.PhoneNumber || "Неизвестно",
                    date: fileSave.date || fileSave.Date || callDate,
                    time: fileSave.time || fileSave.Time || callTime,
                    type: savedType,
                    description: savedNotes,
                    status: "Отработана",
                    address: savedAddress,
                    applicant: savedRole,
                    check: true,
                    critical: false
                };
            }
            return {
                id: c.id,
                incidentNumber: callMeta.incidentNumber,
                emergency: "Нет",
                operator,
                arm,
                phone: c.caller?.phoneNumber || c.caller?.PhoneNumber || "Неизвестно",
                date: callDate,
                time: callTime,
                type: "Экстренный вызов",
                description: "",
                status: "В работе",
                address: "",
                applicant: "Заявитель",
                check: false,
                critical: c.caller ? (c.caller.panicLevel > 75 || c.caller.PanicLevel > 75) : false
            };
        });

        const serverCallsFiltered = serverCalls.filter(serverCall =>
            !localCreatedIncidents.some(localCall => localCall.id === serverCall.id) &&
            !serverSavedCards.some(fileCard =>
                (fileCard.callId && fileCard.callId === serverCall.id) ||
                (fileCard.CallId && fileCard.CallId === serverCall.id)
            )
        );

        allData = [...localCreatedIncidents, ...serverCallsFiltered];
        serverSavedCards.forEach(fileCard => {
            const cId = fileCard.callId || fileCard.CallId;
            if (!cId || allData.some(x => x.id === cId)) return;
            const cls = fileCard.classifier || fileCard.Classifier;
            const addr = fileCard.address || fileCard.Address;
            const savedType = cls?.selectedType || cls?.SelectedType || "Экстренный вызов";
            const savedNotes = fileCard.operatorNotes || fileCard.OperatorNotes || "Карточка сохранена";
            const savedRole = fileCard.applicantRole || fileCard.ApplicantRole || "Заявитель";
            const street = addr?.street || addr?.Street || "";
            const house = addr?.house || addr?.House || "";
            allData.push({
                id: cId,
                emergency: "Нет",
                operator: CURRENT_STUDENT_ID,
                arm: CURRENT_ARM,
                phone: "Сохранено",
                date: fileCard.savedAt ? fileCard.savedAt.slice(0, 10).split("-").reverse().join(".") : "",
                time: fileCard.savedAt ? fileCard.savedAt.slice(11, 19) : "",
                type: savedType,
                description: savedNotes,
                status: "Отработана",
                address: street || house ? `${street ? `ул. ${street}` : ""}${street && house ? ", " : ""}${house ? `д. ${house}` : ""}` : "",
                applicant: savedRole,
                check: true,
                critical: false
            });
        });

        const searchInput = $("fText") || { value: "" };
        if (searchInput.value) applyFilters();
        else {
            filtered = [...allData];
            render();
        }

        const freeCall = (data.activeCalls || []).find(c => c.studentId === "Свободен");
        if (
            freeCall &&
            !activeSocketCallId &&
            !document.getElementById("avayaModal")?.classList.contains("show")
        ) {
            showAvayaIncomingCall(
                freeCall.id,
                freeCall.caller?.phoneNumber || freeCall.caller?.PhoneNumber || ""
            );
        }
    } catch (error) {
        console.error("Ошибка связи с Python runtime backend:", error);
    }
}
let voiceWebSocket = null;
let audioContext = null;
let mediaStreamSource = null;
let processorNode = null;
function showAvayaIncomingCall(callId, callerPhone) {
    activeSocketCallId = callId;
	currentCallCardSaved = false;
    console.log("[AVAYA] Входящий звонок:", callId);
    console.log("[AVAYA] Номер заявителя:", callerPhone);
    // ==========================================================
    // СОХРАНЯЕМ МЕТАДАННЫЕ ЗВОНКА
    // ==========================================================
    let meta = activeCallMeta.get(callId);
    // Если метаданных ещё нет — создаём их прямо сейчас
    if (!meta) {
        meta = {
            startedAt: new Date(),
            incidentNumber: generateIncidentNumber(callId),
            callerPhone: callerPhone || ""
        };
        activeCallMeta.set(callId, meta);
    } else {
        // Если метаданные уже есть — обязательно обновляем номер
        meta.callerPhone = callerPhone || meta.callerPhone || "";
    }
    console.log("[AVAYA] META:", meta);
    console.log("[AVAYA] Сохранённый телефон:", activeCallMeta.get(callId)?.callerPhone);
    // ==========================================================
    // ПОКАЗЫВАЕМ НОМЕР В AVAYA
    // ==========================================================
    const avayaNumber = $("avayaNumber");
    if (avayaNumber) {
        avayaNumber.textContent = callerPhone || "Неизвестно";
    }
    const avayaModal = $("avayaModal");
    if (avayaModal) {
        avayaModal.classList.add("show");
    }
    const acceptButton = $("btnAcceptCall");
    if (acceptButton) {
        acceptButton.onclick = async () => {
            try {
                const res = await fetch(`${PYTHON_API_BASE}/runtime/calls/${encodeURIComponent(callId)}/accept`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        callId: callId,
                        studentId: CURRENT_STUDENT_ID,
                        sessionId: ACTIVE_SESSION_ID,
                        phoneNumber: callerPhone
                    })
                });
				if (res.ok) {
					const acceptedCall = await res.json();

					CURRENT_STUDENT_ID =
						acceptedCall.studentId ||
						acceptedCall.StudentId ||
						CURRENT_STUDENT_ID;

					updateStudentIdentity();

					closeAvayaModal();
					showCurrentCallWidget(
						callId,
						callerPhone
					);
					clearInterval(callTimerInterval);

					window.currentCallSecondsCounter = 0;

					callTimerInterval = setInterval(() => {
						window.currentCallSecondsCounter++;
					}, 1000);

					if ($("newCard")) {
						$("newCard").style.opacity = "1";
						$("newCard").style.cursor = "pointer";
						$("newCard").disabled = false;
						$("newCard").onclick = () => {
							openIncidentCard(callId);
						};
					}

					startVoiceStreaming(callId);
				}
            } catch (e) {
                console.error("Ошибка фиксации вызова:", e);
                activeSocketCallId = null;
            }
        };
    }
}
function closeAvayaModal() {
    if (document.getElementById("avayaModal")) {
        document.getElementById("avayaModal").classList.remove("show");
    }
}
let sttWebSocket = null;
let csharpWebSocket = null;
let audioCtx = null;
let micStream = null;
let micSource = null;
let scriptProcessor = null;
async function startVoiceStreaming(callId) {
    console.log(`[АРМ ЗВУК] Инициализация речевого контура для звонка: ${callId}`);
    try {
        sttWebSocket = new WebSocket(
    `wss://${window.location.hostname}:8000/stt`
);
        sttWebSocket.binaryType = "arraybuffer";
        sttWebSocket.onopen = () => console.log("[АРМ STT] Успешное подключение к сокету Vosk Python");
        sttWebSocket.onerror = (e) => console.error("[АРМ STT] Ошибка сокета Vosk:", e);
        sttWebSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.text) {
                const typeToSend = data.final ? "final" : "interim";
                sendOperatorTextToCsharp(callId, data.text, typeToSend);
            }
        };
        csharpWebSocket = new WebSocket(
    `wss://${window.location.hostname}:5000/api/stream-call?callId=${callId}`
);
        csharpWebSocket.binaryType = "arraybuffer";
        csharpWebSocket.onopen = () => console.log("[АРМ C#] Успешное подключение к потоку диалога C#");
        csharpWebSocket.onerror = (e) => console.error("[АРМ C#] Ошибка сокета C# диалога:", e);
        csharpWebSocket.onmessage = async (event) => {
            if (event.data instanceof ArrayBuffer) {
                await playIncomingAudioBuffer(event.data);
            } else {
                try {
                    const msg = JSON.parse(event.data);
					if (msg.type === "response") {
						console.log(`[ИИ ЗАЯВИТЕЛЬ]: ${msg.text}`);
					}
                } catch(pErr) {
                }
            }
        };
        micStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                channelCount: 1
            }
        });
        audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        micSource = audioCtx.createMediaStreamSource(micStream);
        scriptProcessor = audioCtx.createScriptProcessor(4096, 1, 1);
        scriptProcessor.onaudioprocess = (audioProcessingEvent) => {
            if (!sttWebSocket || sttWebSocket.readyState !== WebSocket.OPEN) return;
            const inputBuffer = audioProcessingEvent.inputBuffer;
            const inputData = inputBuffer.getChannelData(0);
            const pcmBuffer = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                let s = Math.max(-1, Math.min(1, inputData[i]));
                pcmBuffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            sttWebSocket.send(pcmBuffer.buffer);
        };
		micSource.connect(scriptProcessor);

		const silentGain = audioCtx.createGain();
		silentGain.gain.value = 0;

		scriptProcessor.connect(silentGain);
		silentGain.connect(audioCtx.destination);
    } catch (err) {
        console.error("❌ КРИТИЧЕСКАЯ ОШИБКА ЗАПУСКА МИКРОФОНА АРМ:", err);
        alert("Не удалось активировать микрофон! Проверьте разрешения в браузере.");
    }
}
function sendOperatorTextToCsharp(callId, recognizedText, msgType) {
    if (csharpWebSocket && csharpWebSocket.readyState === WebSocket.OPEN) {
        const payload = {
            type: msgType,
            text: recognizedText
        };
        csharpWebSocket.send(JSON.stringify(payload));
    }
}
let activeAudioSource = null;
let incomingAudioQueue = [];
let isPlayingIncomingAudio = false;
let audioPlaybackGeneration = 0;

async function playIncomingAudioBuffer(arrayBuffer) {
    if (!audioCtx) return;

    const generation = audioPlaybackGeneration;

    try {
        const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer.slice(0));

        if (generation !== audioPlaybackGeneration)
            return;

        incomingAudioQueue.push(audioBuffer);
        playNextIncomingAudio();

    } catch (e) {
        console.error(
            "[АРМ ПЛЕЕР] Ошибка декодирования входящего WAV чанка:",
            e
        );
    }
}

function playNextIncomingAudio() {
    if (!audioCtx ||
        isPlayingIncomingAudio ||
        incomingAudioQueue.length === 0)
        return;

    const audioBuffer = incomingAudioQueue.shift();

    isPlayingIncomingAudio = true;

    activeAudioSource = audioCtx.createBufferSource();
    activeAudioSource.buffer = audioBuffer;
    activeAudioSource.connect(audioCtx.destination);

    activeAudioSource.onended = () => {
        isPlayingIncomingAudio = false;
        activeAudioSource = null;
        playNextIncomingAudio();
    };

    activeAudioSource.start(0);
}

function stopAllIncomingAudio() {
    audioPlaybackGeneration++;

    incomingAudioQueue = [];

    if (activeAudioSource) {
        try {
            activeAudioSource.stop();
        } catch (e) {}

        activeAudioSource = null;
    }

    isPlayingIncomingAudio = false;
}
function stopVoiceStreaming() {
    console.log("[АРМ ЗВУК] Деактивация речевого контура и освобождение микрофона.");
	stopAllIncomingAudio();
    clearInterval(callTimerInterval);
    window.currentCallSecondsCounter = 0;
    if (scriptProcessor) { scriptProcessor.disconnect(); scriptProcessor = null; }
    if (micSource) { micSource.disconnect(); micSource = null; }
    if (micStream) { micStream.getTracks().forEach(track => track.stop()); micStream = null; }
    if (sttWebSocket) { sttWebSocket.close(); sttWebSocket = null; }
    if (csharpWebSocket) { csharpWebSocket.close(); csharpWebSocket = null; }
}
async function checkAudioAccess() {
    const audioStatus = document.getElementById("audioStatus");

    if (!audioStatus) return;

    audioStatus.classList.remove("audio-ok");
    audioStatus.title = "Нет доступа к микрофону";

    try {
        if (!navigator.mediaDevices) {
            audioStatus.title = "Аудио недоступно";
            return;
        }

        const devices = await navigator.mediaDevices.enumerateDevices();
        const hasMicrophone = devices.some(
            device => device.kind === "audioinput"
        );

        if (!hasMicrophone) {
            audioStatus.title = "Микрофон не найден";
            return;
        }

        const stream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });

        const hasActiveTrack = stream.getAudioTracks().some(
            track => track.readyState === "live"
        );

        if (hasActiveTrack) {
            audioStatus.classList.add("audio-ok");
            audioStatus.title = "Микрофон доступен";
        }

        stream.getTracks().forEach(track => track.stop());

    } catch (error) {
        console.error("Audio access error:", error);

        audioStatus.classList.remove("audio-ok");
        audioStatus.title = "Нет доступа к микрофону";
    }
}

checkAudioAccess();

setInterval(() => {
    if (!accessToken) return;

    fetch(`${PYTHON_API_BASE}/auth/heartbeat`, {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${accessToken}`
        }
    }).catch(() => {});
}, 10000);



(async () => {
    try {
        await loadCurrentStudent();

        console.log(
            "[АРМ] Студент:",
            CURRENT_STUDENT_DB_ID,
            CURRENT_STUDENT_ID,
            CURRENT_STUDENT_NAME
        );

    } catch (error) {
        console.error(
            "[АРМ] Не удалось определить студента:",
            error
        );

        const studentId =
            localStorage.getItem(
                "system112_student_id"
            );

        if (studentId) {
            CURRENT_STUDENT_ID = studentId;
        }
    }

    populateTypes();
    render();
    updateClock();
	initAvayaWidgetDrag();
    fetchSystemState();

    setInterval(updateClock, 1000);
    setInterval(fetchSystemState, 3000);
})();


const MAX_POINTS = 360;
const POLL_MS = 5000;
const ATTENDANCE_COLOR = "#4ade80";
const STATUS_COLORS = [
  "#7caf2d",
  "#ffd166",
  "#55c0e0",
  "#2fa8c8",
  "#ffb45f",
  "#9ecae1",
  "#ff5d5d",
  "#f28e2b",
  "#ff9f1c",
  "#f4a261",
  "#f77f00",
  "#fb7185",
  "#7dd3fc",
  "#ef4444",
  "#94a3b8",
];

const statusPill = document.getElementById("statusPill");
const lastRead = document.getElementById("lastRead");
const totalCalls = document.getElementById("totalCalls");
const attendanceRate = document.getElementById("attendanceRate");
const lunchBanner = document.getElementById("lunchBanner");
const breakBannerTitle = document.getElementById("breakBannerTitle");
const lunchBannerText = document.getElementById("lunchBannerText");
const statusGrid = document.getElementById("statusGrid");
const groupGrid = document.getElementById("groupGrid");
let displayedTotal = 0;
let displayedAttendanceRate = 0;
let lunchBannerVisible = false;

const chartContext = document.getElementById("callsChart");
const chart = new Chart(chartContext, {
  type: "line",
  data: {
    labels: [],
    datasets: [
      {
        label: "ATENDIMENTO",
        data: [],
        borderColor: ATTENDANCE_COLOR,
        backgroundColor: ATTENDANCE_COLOR,
        borderWidth: 3,
        pointRadius: 0,
        pointHoverRadius: 4,
        cubicInterpolationMode: "monotone",
        tension: 0.42,
        fill: false,
      },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
      duration: 900,
      easing: "easeOutQuart",
    },
    transitions: {
      active: {
        animation: {
          duration: 900,
        },
      },
      resize: {
        animation: {
          duration: 250,
        },
      },
      show: {
        animations: {
          x: { from: 0 },
          y: { from: 0 },
        },
      },
    },
    interaction: {
      intersect: false,
      mode: "index",
    },
    plugins: {
      legend: {
        display: false,
        position: "bottom",
        labels: {
          color: "#8fa0b3",
          boxWidth: 10,
          boxHeight: 10,
          usePointStyle: true,
          pointStyle: "circle",
          padding: 14,
        },
      },
      tooltip: {
        backgroundColor: "#ffffff",
        titleColor: "#0f172a",
        bodyColor: "#0f172a",
        borderColor: "rgba(15, 23, 42, 0.12)",
        borderWidth: 1,
        displayColors: false,
      },
    },
    scales: {
      x: {
        grid: {
          color: "rgba(15, 23, 42, 0.08)",
        },
        ticks: {
          color: "#64748b",
          maxTicksLimit: 12,
        },
      },
      y: {
        beginAtZero: true,
        grid: {
          color: "rgba(15, 23, 42, 0.08)",
        },
        ticks: {
          color: "#64748b",
          precision: 0,
        },
        title: {
          display: true,
          text: "Atendimentos",
          color: "#64748b",
        },
      },
    },
  },
});

function setStatus(kind, text) {
  statusPill.className = `status-pill ${kind}`;
  statusPill.textContent = text;
}

function formatTime(date) {
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function pushPoint(label, value) {
  chart.data.labels.push(label);
  chart.data.datasets[0].data.push(value);

  if (chart.data.labels.length > MAX_POINTS) {
    chart.data.labels.shift();
    chart.data.datasets[0].data.shift();
  }

  chart.update("active");
}

function renderStatuses(items) {
  if (!items || items.length === 0) {
    statusGrid.innerHTML = "";
    return;
  }

  const total = items.reduce((sum, item) => sum + item.count, 0);

  statusGrid.innerHTML = items
    .map((item, index) => {
      const percent = total ? (item.count / total) * 100 : 0;
      const swatch =
        normalizeStatus(item.status) === "ATENDIMENTO"
          ? ATTENDANCE_COLOR
          : STATUS_COLORS[index % STATUS_COLORS.length];

      return `
        <div class="status-item" title="${escapeHtml(item.status)}">
          <span class="status-swatch" style="--swatch: ${swatch}"></span>
          <span class="status-name">${escapeHtml(item.status)}</span>
          <span class="status-count">${percent.toLocaleString("pt-BR", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}%</span>
        </div>
      `;
    })
    .join("");

  if (window.gsap) {
    gsap.fromTo(
      ".status-item",
      { opacity: 0.42, y: 8 },
      { opacity: 1, y: 0, duration: 0.55, stagger: 0.025, ease: "power2.out" },
    );
  }
}

function animateTotal(nextValue) {
  if (!window.gsap) {
    totalCalls.textContent = nextValue.toLocaleString("pt-BR");
    displayedTotal = nextValue;
    return;
  }

  const state = { value: displayedTotal };
  gsap.to(state, {
    value: nextValue,
    duration: 0.75,
    ease: "power2.out",
    onUpdate: () => {
      totalCalls.textContent = Math.round(state.value).toLocaleString("pt-BR");
    },
    onComplete: () => {
      displayedTotal = nextValue;
      totalCalls.textContent = nextValue.toLocaleString("pt-BR");
    },
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeStatus(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .trim();
}

function getAttendanceRate(items, total) {
  if (!items || !total) {
    return 0;
  }

  const attendance = items.find((item) => normalizeStatus(item.status) === "ATENDIMENTO");
  return ((attendance?.count || 0) / total) * 100;
}

function getAttendanceCount(items) {
  const attendance = (items || []).find((item) => normalizeStatus(item.status) === "ATENDIMENTO");
  return attendance?.count || 0;
}

function attendanceClass(value) {
  if (value >= 2.5) {
    return "good";
  }
  if (value >= 2) {
    return "warn";
  }
  return "bad";
}

function setLunchBanner(active, message, type) {
  if (!lunchBanner) {
    return;
  }

  const shouldShow = Boolean(active);
  const text = message || "";
  const title = type === "pausa" ? "Período de pausa" : "Período de almoço";

  if (breakBannerTitle) {
    breakBannerTitle.textContent = title;
  }
  if (lunchBannerText) {
    lunchBannerText.textContent = text;
  }

  if (shouldShow) {
    lunchBanner.hidden = false;
    lunchBanner.classList.add("is-visible");

    if (window.gsap && !lunchBannerVisible) {
      gsap.fromTo(
        lunchBanner,
        { opacity: 0, y: -18, scale: 0.985 },
        { opacity: 1, y: 0, scale: 1, duration: 0.7, ease: "power3.out" },
      );

      gsap.to(".lunch-banner-icon span", {
        scale: 1.08,
        opacity: 0.7,
        duration: 1.35,
        repeat: -1,
        yoyo: true,
        ease: "sine.inOut",
      });
    }
  } else {
    lunchBanner.classList.remove("is-visible");

    if (window.gsap && lunchBannerVisible) {
      gsap.killTweensOf(".lunch-banner-icon span");
      gsap.to(lunchBanner, {
        opacity: 0,
        y: -12,
        scale: 0.99,
        duration: 0.35,
        ease: "power2.out",
        onComplete: () => {
          lunchBanner.hidden = true;
        },
      });
    } else {
      lunchBanner.hidden = true;
    }
  }

  lunchBannerVisible = shouldShow;
}

function upsertGroupCard(group) {
  const id = `group-${group.idGrupoUsuario}`;
  let card = document.getElementById(id);

  if (!card) {
    card = document.createElement("article");
    card.className = "group-card";
    card.id = id;
    card.innerHTML = `
      <div class="group-card-head">
        <div>
          <div class="group-title"></div>
          <div class="group-meta"></div>
        </div>
        <div class="group-rate neutral"></div>
      </div>
      <div class="group-bar"><div class="group-bar-fill"></div></div>
      <div class="group-foot">
        <span class="group-attendance"></span>
        <span>Meta 2,50%</span>
      </div>
    `;
    groupGrid.appendChild(card);
  }

  card.querySelector(".group-title").textContent = group.grupo;
  card.querySelector(".group-meta").textContent = `${group.total.toLocaleString("pt-BR")} ligações`;

  const rate = card.querySelector(".group-rate");
  rate.className = `group-rate ${attendanceClass(group.attendanceRate)}`;
  rate.textContent = `${group.attendanceRate.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;

  const fill = card.querySelector(".group-bar-fill");
  fill.className = `group-bar-fill ${attendanceClass(group.attendanceRate)}`;
  fill.style.width = `${Math.min((group.attendanceRate / 2.5) * 100, 100)}%`;

  card.querySelector(".group-attendance").textContent = `${group.attendance.toLocaleString("pt-BR")} atendimentos`;
}

function renderGroupCharts(groups, label) {
  const visibleGroups = (groups || []).filter((group) => {
    const normalized = normalizeStatus(group.grupo);
    return (
      group.total > 0 &&
      normalized !== "ACEITE - GIOVANA" &&
      normalized !== "EUROPA 5" &&
      normalized !== "INATIVO"
    );
  });

  if (visibleGroups.length === 0) {
    groupGrid.innerHTML = "";
    return;
  }

  const seen = new Set();
  visibleGroups.forEach((group) => {
    const key = String(group.idGrupoUsuario);
    seen.add(key);
    upsertGroupCard(group);
  });

  Array.from(groupGrid.children).forEach((card) => {
    if (!seen.has(card.id.replace("group-", ""))) {
      card.remove();
    }
  });
}

function animateAttendanceRate(nextValue) {
  const nextClass = attendanceClass(nextValue);
  attendanceRate.className = `rate-value ${nextClass}`;

  if (!window.gsap) {
    attendanceRate.textContent = `${nextValue.toLocaleString("pt-BR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}%`;
    displayedAttendanceRate = nextValue;
    return;
  }

  const state = { value: displayedAttendanceRate };
  gsap.to(state, {
    value: nextValue,
    duration: 0.75,
    ease: "power2.out",
    onUpdate: () => {
      attendanceRate.textContent = `${state.value.toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}%`;
    },
    onComplete: () => {
      displayedAttendanceRate = nextValue;
      attendanceRate.textContent = `${nextValue.toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}%`;
    },
  });
}

async function loadMetrics() {
  try {
    const response = await fetch("/api/metrics", { cache: "no-store" });
    const body = await response.json();

    if (!response.ok || !body.ok) {
      throw new Error(body.error || "Falha ao consultar a API");
    }

    const now = new Date();
    const label = formatTime(now);
    const total = body.data.total;

    pushPoint(label, getAttendanceCount(body.data.byStatus));
    animateTotal(total);
    animateAttendanceRate(getAttendanceRate(body.data.byStatus, total));
    lastRead.textContent = formatTime(now);
    renderStatuses(body.data.byStatus);
    renderGroupCharts(body.data.byGroup, label);
    setLunchBanner(
      body.data.periodoAviso?.ativo,
      body.data.periodoAviso?.mensagem,
      body.data.periodoAviso?.tipo,
    );
    setStatus("ok", "Online");
  } catch (error) {
    setStatus("error", "Erro");
    lastRead.textContent = error.message;
  }
}

loadMetrics();
setInterval(loadMetrics, POLL_MS);

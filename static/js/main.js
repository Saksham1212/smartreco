/* SmartReco general UI interactions: nav dropdown, flash messages, and the
 * recommendation widget (fetch, render, auto-refresh polling). */

document.addEventListener("DOMContentLoaded", function () {
  // ---- user menu dropdown ----
  var menuBtn = document.getElementById("userMenuBtn");
  var dropdown = document.getElementById("userMenuDropdown");
  if (menuBtn && dropdown) {
    menuBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      dropdown.classList.toggle("open");
    });
    document.addEventListener("click", function () {
      dropdown.classList.remove("open");
    });
  }

  // ---- flash message auto-dismiss ----
  var flashes = document.querySelectorAll(".flash");
  flashes.forEach(function (el) {
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 4000);
  });

  // ---- navbar shadow on scroll ----
  var navbar = document.querySelector(".navbar");
  if (navbar) {
    var onScroll = function () {
      navbar.classList.toggle("scrolled", window.scrollY > 10);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // ---- scroll-reveal for sections/cards ----
  initScrollReveal();

  // ---- animated stat counters (admin dashboard) ----
  animateStatCounters();

  // ---- entrance stagger index for product cards rendered server-side ----
  document.querySelectorAll(".product-grid .product-card").forEach(function (card, i) {
    card.style.setProperty("--i", i);
  });

  // ---- loading state on POST form submits ----
  document.addEventListener("submit", function (e) {
    if (e.defaultPrevented) return;
    var form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if ((form.method || "get").toLowerCase() !== "post") return;
    var btn = form.querySelector('button[type="submit"]');
    if (btn && !btn.disabled) {
      btn.disabled = true;
      btn.classList.add("btn-loading");
    }
  });
});

function initScrollReveal() {
  var targets = document.querySelectorAll(
    ".section, .auth-card, .stat-card, .table-wrap, .product-detail-header, .product-detail-body"
  );
  if (!targets.length) return;

  if (!("IntersectionObserver" in window)) {
    targets.forEach(function (el) {
      el.classList.add("reveal", "revealed");
    });
    return;
  }

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("revealed");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.08 }
  );

  targets.forEach(function (el) {
    el.classList.add("reveal");
    observer.observe(el);
  });
}

function animateStatCounters() {
  var counters = document.querySelectorAll(".stat-value[data-value]");
  if (!counters.length) return;

  counters.forEach(function (el) {
    var target = parseInt(el.dataset.value, 10) || 0;
    var duration = 900;
    var startTime = null;

    function step(ts) {
      if (!startTime) startTime = ts;
      var progress = Math.min((ts - startTime) / duration, 1);
      el.textContent = Math.floor(progress * target);
      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        el.textContent = target;
      }
    }
    requestAnimationFrame(step);
  });
}

var CATEGORY_COLORS = {
  "AI/ML": "#a78bfa",
  "Web Development": "#38bdf8",
  "Data Science": "#4ade80",
  DevOps: "#fb923c",
  "Mobile Development": "#f472b6",
};

function categoryColor(category) {
  return CATEGORY_COLORS[category] || "#94a3b8";
}

function escapeHtml(str) {
  var div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

function renderProductCard(p, index) {
  var color = categoryColor(p.category);
  var thumb = p.thumbnail_url
    ? '<img src="' + escapeHtml(p.thumbnail_url) + '" alt="" loading="lazy">'
    : "";
  var thumbStyle = p.thumbnail_url ? "" : "background: linear-gradient(135deg, " + color + ", #0f172a);";
  var cardStyle = "--glow:" + color + "66; --i:" + (index || 0) + ";";
  return (
    '<a href="/products/' +
    p.id +
    '" class="product-card" data-product-id="' +
    p.id +
    '" style="' +
    cardStyle +
    '">' +
    '<div class="product-thumb" style="' +
    thumbStyle +
    '">' +
    thumb +
    '<span class="badge badge-difficulty badge-' +
    escapeHtml(p.difficulty_level) +
    '">' +
    escapeHtml(p.difficulty_level) +
    "</span>" +
    "</div>" +
    '<div class="product-card-body">' +
    '<span class="badge badge-category" style="background-color:' +
    color +
    '22; color:' +
    color +
    "; border-color:" +
    color +
    '55;">' +
    escapeHtml(p.category) +
    "</span>" +
    '<h3 class="product-title">' +
    escapeHtml(p.title) +
    "</h3>" +
    '<div class="product-card-footer">' +
    '<span class="product-price">$' +
    Number(p.price).toFixed(2) +
    "</span>" +
    '<span class="btn btn-sm btn-accent">View Course</span>' +
    "</div>" +
    "</div>" +
    "</a>"
  );
}

function formatUpdatedAt(iso) {
  var d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderRecommendationHtml(data) {
  var cardsHtml = data.products.map(function (p, i) { return renderProductCard(p, i); }).join("");
  return (
    '<div class="recommendation-narrative">' +
    escapeHtml(data.narrative) +
    '<div class="recommendation-meta">Last updated ' +
    formatUpdatedAt(data.updated_at) +
    "</div>" +
    "</div>" +
    '<div class="product-grid">' +
    cardsHtml +
    "</div>"
  );
}

function initRecommendationWidget() {
  var widget = document.getElementById("recommendation-widget");
  if (!widget) return;

  var lastUpdatedAt = null;
  var pollHandle = null;

  function showEmpty() {
    widget.innerHTML =
      '<div class="recommendation-empty">' +
      "<p>We're still learning what you're interested in. Keep browsing courses and searching " +
      "for topics — your personalized recommendations will appear here soon.</p>" +
      "</div>";
  }

  function showError() {
    widget.innerHTML =
      '<div class="recommendation-error">' +
      "<p>We couldn't load your recommendations right now. This page will keep trying automatically.</p>" +
      "</div>";
  }

  function applyUpdate(data) {
    widget.classList.add("fade-transition");
    widget.classList.add("fade-out");
    setTimeout(function () {
      widget.innerHTML = renderRecommendationHtml(data);
      widget.classList.remove("fade-out");
    }, 200);
  }

  function fetchRecommendation(isInitial) {
    fetch("/api/recommendations/me", { credentials: "same-origin" })
      .then(function (res) {
        if (res.status === 404) {
          if (isInitial) showEmpty();
          return null;
        }
        if (!res.ok) throw new Error("bad status");
        return res.json();
      })
      .then(function (data) {
        if (!data) return;
        if (data.updated_at !== lastUpdatedAt) {
          lastUpdatedAt = data.updated_at;
          applyUpdate(data);
        }
      })
      .catch(function () {
        if (isInitial) showError();
      });
  }

  fetchRecommendation(true);
  pollHandle = setInterval(function () {
    fetchRecommendation(false);
  }, 60000);
}

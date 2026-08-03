/* SmartReco behavioral event tracker.
 * Never blocks the UI: events are queued in memory and flushed in batches
 * via fetch(keepalive) or navigator.sendBeacon on unload.
 */
(function () {
  "use strict";

  var FLUSH_SIZE = 10;
  var FLUSH_INTERVAL_MS = 5000;
  var SCROLL_THRESHOLD = 10;
  var ENDPOINT = "/api/events/batch";

  var isAuthenticated = document.body.dataset.userAuthenticated === "true";
  if (!isAuthenticated) return;

  var queue = [];
  var lastScrollDepth = -1;
  var pageEnterTime = Date.now();
  var productId = document.body.dataset.productId ? parseInt(document.body.dataset.productId, 10) : null;
  var timeOnPageRecorded = false;

  function nowIso() {
    return new Date().toISOString();
  }

  function enqueue(eventType, opts) {
    opts = opts || {};
    queue.push({
      event_type: eventType,
      product_id: opts.product_id !== undefined ? opts.product_id : null,
      search_query: opts.search_query !== undefined ? opts.search_query : null,
      timestamp: nowIso(),
      metadata: opts.metadata || null,
    });
    if (queue.length >= FLUSH_SIZE) flush(false);
  }

  function flush(useBeacon) {
    if (queue.length === 0) return;
    var toSend = queue;
    queue = [];
    var payload = JSON.stringify(toSend);

    if (useBeacon && navigator.sendBeacon) {
      var blob = new Blob([payload], { type: "application/json" });
      var accepted = navigator.sendBeacon(ENDPOINT, blob);
      if (!accepted) {
        queue = toSend.concat(queue);
      }
      return;
    }

    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true,
      credentials: "same-origin",
    })
      .then(function (res) {
        if (!res.ok) {
          queue = toSend.concat(queue);
        }
      })
      .catch(function () {
        queue = toSend.concat(queue);
      });
  }

  // ---- page_view ----
  enqueue("page_view", { metadata: { path: window.location.pathname } });

  // ---- product_view ----
  if (productId) {
    enqueue("product_view", { product_id: productId });
  }

  // ---- scroll_depth (throttled, product pages only) ----
  if (productId) {
    window.addEventListener(
      "scroll",
      function () {
        var scrollTop = window.scrollY || document.documentElement.scrollTop;
        var docHeight = document.documentElement.scrollHeight - window.innerHeight;
        var depth = docHeight > 0 ? Math.round((scrollTop / docHeight) * 100) : 100;
        depth = Math.max(0, Math.min(100, depth));
        if (Math.abs(depth - lastScrollDepth) > SCROLL_THRESHOLD) {
          lastScrollDepth = depth;
          enqueue("scroll_depth", { product_id: productId, metadata: { scroll_depth_percent: depth } });
        }
      },
      { passive: true }
    );
  }

  // ---- search (form submit) ----
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.tagName === "FORM") {
      var qInput = form.querySelector('input[name="q"]');
      if (qInput && qInput.value.trim()) {
        enqueue("search", { search_query: qInput.value.trim() });
        flush(false);
      }
    }
  });

  // ---- search_result_click ----
  document.addEventListener("click", function (e) {
    var card = e.target.closest && e.target.closest(".product-card");
    if (card && card.dataset.searchQuery) {
      enqueue("search_result_click", {
        product_id: parseInt(card.dataset.productId, 10),
        search_query: card.dataset.searchQuery,
      });
      flush(false);
    }
  });

  // ---- time_on_page + unload flush ----
  function recordTimeOnPageAndFlush(useBeacon) {
    if (productId && !timeOnPageRecorded) {
      timeOnPageRecorded = true;
      var seconds = Math.round((Date.now() - pageEnterTime) / 1000);
      enqueue("time_on_page", { product_id: productId, metadata: { time_spent_seconds: seconds } });
    }
    flush(useBeacon);
  }

  window.addEventListener("beforeunload", function () {
    recordTimeOnPageAndFlush(true);
  });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      recordTimeOnPageAndFlush(true);
      timeOnPageRecorded = false; // allow re-recording if user comes back and leaves again
    }
  });

  setInterval(function () {
    flush(false);
  }, FLUSH_INTERVAL_MS);

  // Exposed for one-off manual events (e.g. add_to_cart button)
  window.trackEvent = function (eventType, opts) {
    enqueue(eventType, opts);
    flush(false);
  };
})();

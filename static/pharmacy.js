/* =====================================================================
   Sanjeevani Pharmacy - front-end glue.

   Everything is event delegation on data attributes, so the templates
   stay readable:

     <button data-ph="add" data-id="12" data-qty="1">Add to cart</button>

   Every call goes to the same JSON API the no-JavaScript form posts use,
   so the app also works if JS is blocked (the buttons just reload).
   ===================================================================== */

(function () {
  "use strict";

  /* ---------------- tiny helpers ---------------- */

  function toast(message, kind) {
    var box = document.getElementById("ph-toast");

    if (!box) {
      box = document.createElement("div");
      box.id = "ph-toast";
      document.body.appendChild(box);
    }

    box.textContent = message;
    box.className = "show" + (kind ? " " + kind : "");

    clearTimeout(box._timer);
    box._timer = setTimeout(function () {
      box.className = "";
    }, 3400);
  }

  function body(data) {
    var params = new URLSearchParams();

    Object.keys(data || {}).forEach(function (key) {
      if (data[key] !== undefined && data[key] !== null && data[key] !== "") {
        params.append(key, data[key]);
      }
    });

    return params;
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "fetch",
      },
      body: body(data).toString(),
      credentials: "same-origin",
    })
      .then(function (response) {
        return response
          .json()
          .catch(function () {
            return { success: false, message: "Unexpected server response (" + response.status + ")" };
          })
          .then(function (payload) {
            if (response.status === 401 && payload && payload.login_url) {
              window.location.href = payload.login_url + "?next=" + encodeURIComponent(location.pathname);
              throw new Error("redirecting");
            }
            if (!response.ok || payload.success === false) {
              throw new Error((payload && payload.message) || "Request failed");
            }
            return payload;
          });
      });
  }

  function del(url, data) {
    var query = body(data).toString();
    if (query) url = url + (url.indexOf("?") === -1 ? "?" : "&") + query;

    return fetch(url, {
      method: "DELETE",
      credentials: "same-origin",
    }).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok || payload.success === false) {
          throw new Error(payload.message || "Delete failed");
        }
        return payload;
      });
    });
  }

  function get(url) {
    return fetch(url, { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      });
  }

  function fail(error) {
    if (String(error && error.message) === "redirecting") return;
    toast((error && error.message) || "Something went wrong", "bad");
  }

  function busy(button, on) {
    if (!button) return;
    if (on) {
      button.dataset.label = button.innerHTML;
      button.innerHTML = "Working\u2026";
      button.disabled = true;
    } else {
      if (button.dataset.label) button.innerHTML = button.dataset.label;
      button.disabled = false;
    }
  }

  /* ---------------- cart count in the navbar ---------------- */

  function refreshBadge(cart) {
    var total = 0;

    if (cart && cart.lines) {
      cart.lines.forEach(function (line) {
        total += line.quantity;
      });
    }

    document.querySelectorAll("[data-ph-badge]").forEach(function (node) {
      node.textContent = total;
      node.style.display = total > 0 ? "inline-flex" : "none";
    });

    if (cart && typeof window.phCartChanged === "function") {
      window.phCartChanged(cart);
    }
  }

  /* ---------------- actions ---------------- */

  var actions = {
    add: function (node) {
      var id = node.dataset.id;
      var qty = parseInt(node.dataset.qty, 10) || qtyNear(node, id) || 1;

      return post("/pharmacy/api/cart/add", { medicine_id: id, quantity: qty }).then(function (data) {
        toast(data.name + " added to cart", "good");
        refreshBadge(data.cart);
      });
    },

    addrx: function (node) {
      return post("/pharmacy/api/cart/add-prescription", {
        prescription_medicine_id: node.dataset.id,
        quantity: node.dataset.qty || 1,
      }).then(function (data) {
        toast(data.name + " added from your prescription", "good");
        refreshBadge(data.cart);
      });
    },

    addrxall: function (node) {
      return post("/pharmacy/api/prescriptions/add-all", {
        prescription_id: node.dataset.id,
      }).then(function (data) {
        var message =
          (data.added && data.added.length
            ? "Added " + data.added.length + " item(s) to the cart"
            : "Nothing to add");

        if (data.skipped && data.skipped.length) {
          message +=
            " \u00b7 " +
            data.skipped.length +
            " not available (" +
            data.skipped
              .map(function (row) {
                return row.name + ": " + row.reason;
              })
              .join(", ") +
            ")";
        }

        toast(message, data.added && data.added.length ? "good" : "");
        refreshBadge(data.cart);
      });
    },

    buynow: function (node) {
      return post("/pharmacy/api/buy-now", {
        medicine_id: node.dataset.id,
        quantity: node.dataset.qty || 1,
        payment_method: node.dataset.pay || "CASH",
      }).then(function (data) {
        window.location.href = data.redirect;
      });
    },

    qty: function (node) {
      var row = node.closest("[data-line]");
      var input = row.querySelector("input[data-qty]");
      var next = Math.max(0, (parseInt(input.value, 10) || 1) + parseInt(node.dataset.step, 10));

      return post("/pharmacy/api/cart/quantity", {
        item_id: row.dataset.line,
        quantity: next,
      }).then(function (data) {
        if (data.removed) {
          row.remove();
          toast("Item removed", "good");
        } else {
          input.value = data.cart.lines.find(function (l) {
            return l.item_id === parseInt(row.dataset.line, 10);
          }).quantity;
        }
        refreshBadge(data.cart);
        if (typeof window.phRecalc === "function") window.phRecalc(data.cart);
      });
    },

    remove: function (node) {
      return post("/pharmacy/api/cart/remove", { item_id: node.dataset.id }).then(function (data) {
        node.closest("[data-line]").remove();
        toast("Removed from cart", "good");
        refreshBadge(data.cart);
        if (typeof window.phRecalc === "function") window.phRecalc(data.cart);
      });
    },

    clear: function () {
      if (!confirm("Remove everything from the cart?")) return;
      return post("/pharmacy/api/cart/clear", {}).then(function (data) {
        document.querySelectorAll("[data-line]").forEach(function (row) {
          row.remove();
        });
        toast("Cart emptied", "good");
        refreshBadge(data.cart);
        if (typeof window.phRecalc === "function") window.phRecalc(data.cart);
      });
    },

    checkout: function (node) {
      var form = document.getElementById("ph-checkout-form");

      if (!form) {
        toast("Checkout form not found", "bad");
        return Promise.resolve();
      }

      var data = {};
      new FormData(form).forEach(function (value, key) {
        data[key] = value;
      });

      busy(node, true);

      return post("/pharmacy/api/checkout", data)
        .then(function (result) {
          window.location.href = result.redirect;
        })
        .catch(function (error) {
          busy(node, false);
          fail(error);
        });
    },

    pay: function (node) {
      return post("/pharmacy/api/order/" + node.dataset.id + "/pay", {}).then(function (data) {
        toast("Payment confirmed - order is CONFIRMED", "good");
        window.location.href = data.redirect;
      });
    },

    cancel: function (node) {
      var reason = prompt("Why are you cancelling? (goes on the pharmacy record)", "Ordered by mistake");
      if (reason === null) return Promise.resolve();

      return post("/pharmacy/api/order/" + node.dataset.id + "/cancel", { reason: reason }).then(function (data) {
        toast(data.message || "Order cancelled");
        if (data.redirect) window.location.href = data.redirect;
      });
    },

    /* ------- admin ------- */

    "admin-toggle": function (node) {
      return post("/pharmacy/admin/api/medicines/" + node.dataset.id + "/toggle", {}).then(function () {
        node.closest("tr").style.opacity = node.closest("tr").style.opacity === "0.45" ? "1" : "0.45";
        toast("Visibility updated");
      });
    },

    "admin-stock": function (node) {
      var row = node.closest("[data-med]");
      var input = row.querySelector("[data-stock-input]");

      return post("/pharmacy/admin/api/medicines/" + node.dataset.id + "/stock", {
        change: input.value,
        mode: row.querySelector("[data-stock-mode]").value,
        reason: "counter correction",
      }).then(function (data) {
        toast(data.medicine.name + ": stock is now " + data.stock, "good");
        var cell = row.querySelector("[data-stock-now]");
        if (cell) cell.textContent = data.stock;
      });
    },

    "admin-delete": function (node) {
      if (!confirm("Delete this medicine?\n\nA pinned snapshot is taken first, so the Snapshots tab can undo it.")) {
        return Promise.resolve();
      }

      return del("/pharmacy/admin/api/medicines/" + node.dataset.id, { confirm: "DELETE" }).then(function (data) {
        toast(data.message, "good");
        node.closest("tr").remove();
      });
    },

    "admin-fulfil": function (node) {
      return post("/pharmacy/admin/api/orders/" + node.dataset.id + "/fulfil", {
        action: node.dataset.action,
        reason: node.dataset.reason || "",
      }).then(function (data) {
        toast("Order " + data.order.order_no + " is now " + data.status + " / " + data.payment_status, "good");
        node.closest("tr").querySelector("[data-badge]").innerHTML =
          '<span class="ph-badge ' + (data.status === "CONFIRMED" ? "success" : "muted") + '">' +
          data.status + " \u00b7 " + data.payment_status + "</span>";
      });
    },

    "admin-snapshot": function (node) {
      var labelInput = document.querySelector(node.dataset.labelFrom || "#ph-snapshot-label");
      var scopeInput = document.querySelector(node.dataset.scopeFrom || "#ph-snapshot-scope");

      return post("/pharmacy/admin/api/snapshots", {
        label: labelInput ? labelInput.value : "",
        scope: scopeInput ? scopeInput.value : "PHARMACY",
      }).then(function (data) {
        toast("Snapshot #" + data.snapshot.id + " saved", "good");
        setTimeout(function () {
          location.reload();
        }, 700);
      });
    },

    "admin-preview": function (node) {
      var target = document.getElementById("ph-preview-box");

      get("/pharmacy/admin/api/snapshots/" + node.dataset.id + "/preview").then(function (data) {
        var preview = data.preview;
        var html =
          "<strong>" +
          preview.label +
          "</strong> (" +
          preview.created_at_display +
          ") - " +
          preview.total_changes +
          " row(s) would change.<br/>";

        preview.tables.forEach(function (table) {
          html +=
            "<div class='ph-small'>" +
            table.table +
            ": +" +
            table.would_add +
            " new, -" +
            table.would_remove +
            " removed, ~" +
            table.would_modify +
            " modified</div>";
        });

        html +=
          "<div style='margin-top:10px'><button class='ph-btn' data-ph='admin-restore' data-id='" +
          preview.snapshot_id +
          "' data-checksum='" +
          preview.checksum +
          "'>Yes, restore snapshot #" +
          preview.snapshot_id +
          "</button></div>";

        target.innerHTML = html;
        target.style.display = "block";
      });

      return Promise.resolve();
    },

    "admin-restore": function (node) {
      if (
        !confirm(
          "Restore will REPLACE the current pharmacy data for those tables.\n\n" +
            "An automatic 'undo point' snapshot is taken first.\nContinue?"
        )
      ) {
        return Promise.resolve();
      }

      return post("/pharmacy/admin/api/snapshots/" + node.dataset.id + "/restore", {
        checksum: node.dataset.checksum,
      }).then(function (data) {
        toast(data.message, "good");
        setTimeout(function () {
          location.reload();
        }, 900);
      });
    },

    "admin-pin": function (node) {
      return post("/pharmacy/admin/api/snapshots/" + node.dataset.id + "/pin", {}).then(function () {
        toast("Pin flag changed");
        node.closest("tr").style.opacity = "0.6";
      });
    },

    "admin-permission": function (node) {
      var allowed = node.classList.contains("off") ? "on" : "";

      return post("/pharmacy/admin/api/roles/permission", {
        role: node.dataset.role,
        permission: node.dataset.perm,
        allowed: allowed,
        note: "changed from the Access tab",
      }).then(function () {
        node.classList.toggle("off");
        toast(
          node.dataset.role + ": " + node.dataset.perm + " = " + (allowed ? "ALLOWED" : "DENIED"),
          allowed ? "good" : ""
        );
      });
    },

    "admin-role": function (node) {
      var row = node.closest("[data-user]");
      var select = row.querySelector("[data-role-select]");
      var active = row.querySelector("[data-active-select]");

      return post("/pharmacy/admin/api/users/" + node.dataset.id + "/role", {
        role: select.value,
        is_active: active.value === "active" ? "on" : "",
      }).then(function (data) {
        toast("User now has role " + data.role, "good");
      });
    },

    "admin-shop": function (node) {
      var form = document.getElementById("ph-shop-form");
      var data = {};
      new FormData(form).forEach(function (value, key) {
        data[key] = value;
      });

      return post("/pharmacy/admin/api/nearby/shops", data).then(function () {
        toast("Shop saved to SQL", "good");
        setTimeout(function () {
          location.reload();
        }, 700);
      });
    },

    "admin-sync": function (node) {
      busy(node, true);

      return post("/pharmacy/admin/api/nearby/sync-google", { q: node.dataset.q || "" })
        .then(function (data) {
          toast("Found " + data.found + ", saved " + data.saved + " (" + data.google_status + ")", "good");
          setTimeout(function () {
            location.reload();
          }, 900);
        })
        .catch(function (error) {
          busy(node, false);
          fail(error);
        });
    },

    "admin-bulk-price": function (node) {
      var form = document.getElementById("ph-bulk-price");
      var data = {};
      new FormData(form).forEach(function (value, key) {
        data[key] = value;
      });

      return post("/pharmacy/admin/api/catalog/bulk-price", data).then(function (data2) {
        toast(
          data2.changed + " price(s) changed. Undo snapshot #" + data2.snapshot_id,
          "good"
        );
      });
    },

    "admin-import": function (node) {
      var textarea = document.getElementById("ph-import-text");

      return post("/pharmacy/admin/api/catalog/stock-import", {
        csv_text: textarea.value,
        mode: document.getElementById("ph-import-mode").value,
      }).then(function (data) {
        toast(data.message, "good");
        setTimeout(function () {
          location.reload();
        }, 900);
      });
    },

    "admin-image": function (node) {
      var picker = document.getElementById("ph-image-medicine");
      var input = document.getElementById("ph-image-file");

      if (!picker || !picker.value) {
        toast("Pick the medicine first", "bad");
        return Promise.resolve();
      }

      if (!input.files || !input.files[0]) {
        toast("Choose an image file first", "bad");
        return Promise.resolve();
      }

      var form = new FormData();
      form.append("file", input.files[0]);

      return fetch("/pharmacy/admin/api/medicines/" + picker.value + "/image", {
        method: "POST",
        body: form,
        credentials: "same-origin",
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data.success) throw new Error(data.message);
          toast("Photo saved: " + data.image, "good");
        });
    },
  };

  function qtyNear(node, id) {
    var input = document.querySelector('[data-qty-for="' + id + '"]');
    return input ? parseInt(input.value, 10) || 1 : 1;
  }

  /* ---------------- wiring ---------------- */

  document.addEventListener("click", function (event) {
    var node = event.target.closest("[data-ph]");

    if (!node) return;

    var handler = actions[node.dataset.ph];

    if (!handler) return;

    event.preventDefault();

    Promise.resolve()
      .then(function () {
        return handler(node);
      })
      .catch(fail);
  });

  document.addEventListener("change", function (event) {
    var input = event.target;

    if (input.matches("[data-qty]")) {
      var row = input.closest("[data-line]");
      post("/pharmacy/api/cart/quantity", {
        item_id: row.dataset.line,
        quantity: parseInt(input.value, 10) || 1,
      })
        .then(function (data) {
          refreshBadge(data.cart);
          if (typeof window.phRecalc === "function") window.phRecalc(data.cart);
        })
        .catch(fail);
    }
  });

  window.pharmacy = {
    post: post,
    get: get,
    del: del,
    toast: toast,
    body: body,
  };
})();

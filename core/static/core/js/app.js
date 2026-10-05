// Applique le thème mémorisé le plus tôt possible (évite un flash clair)
(function () {
  var savedTheme = localStorage.getItem("facturier_theme");
  document.documentElement.setAttribute("data-bs-theme", savedTheme === "dark" ? "dark" : "light");
})();

document.addEventListener("DOMContentLoaded", function () {
  var DISCOUNT_TYPE_KEY = "facturier_discount_type";
  var DISCOUNT_VALUE_KEY = "facturier_discount_value";

  // -------------------------------------------------------------------
  // Bascule mode sombre / clair (natif Bootstrap)
  // -------------------------------------------------------------------
  var themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) {
    var refreshThemeIcon = function () {
      var isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
      themeToggle.innerHTML = isDark ? '<i class="bi bi-sun"></i>' : '<i class="bi bi-moon-stars"></i>';
    };
    refreshThemeIcon();
    themeToggle.addEventListener("click", function () {
      var isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
      var next = isDark ? "light" : "dark";
      document.documentElement.setAttribute("data-bs-theme", next);
      localStorage.setItem("facturier_theme", next);
      refreshThemeIcon();
    });
  }

  // -------------------------------------------------------------------
  // Réduction globale : calcul et affichage en direct (sans rechargement)
  // -------------------------------------------------------------------
  var discountTypeSelect = document.getElementById("discount-type-select");
  var discountValueField = document.getElementById("discount-value-field");
  var calcDataEl = document.getElementById("caisse-calc-data");

  function formatFCFA(amount) {
    return Math.round(amount).toLocaleString("fr-FR") + " F CFA";
  }

  function computeTotals() {
    if (!calcDataEl || !discountTypeSelect) return null;
    var subTotal = parseFloat(calcDataEl.getAttribute("data-subtotal")) || 0;
    var tvaRate = parseFloat(calcDataEl.getAttribute("data-tvarate")) || 0;
    var discountType = discountTypeSelect.value;
    var discountValueRaw = parseFloat(discountValueField ? discountValueField.value : 0) || 0;

    var discountAmount = 0;
    if (discountType === "PERCENTAGE") discountAmount = subTotal * (discountValueRaw / 100);
    else if (discountType === "AMOUNT") discountAmount = discountValueRaw;
    discountAmount = Math.max(0, Math.min(discountAmount, subTotal));

    var taxable = subTotal - discountAmount;
    var tvaAmount = taxable * (tvaRate / 100);
    var total = taxable + tvaAmount;

    return { subTotal: subTotal, discountAmount: discountAmount, tvaAmount: tvaAmount, total: total };
  }

  function updateTotalsDisplay() {
    var totals = computeTotals();
    if (!totals) return totals;

    var discountRow = document.getElementById("display-discount-row");
    var discountAmountEl = document.getElementById("display-discount-amount");
    if (discountRow && discountAmountEl) {
      discountRow.style.display = totals.discountAmount > 0 ? "flex" : "none";
      discountAmountEl.textContent = "- " + formatFCFA(totals.discountAmount);
    }
    var tvaAmountEl = document.getElementById("display-tva-amount");
    if (tvaAmountEl) tvaAmountEl.textContent = formatFCFA(totals.tvaAmount);
    var totalEl = document.getElementById("display-total-amount");
    if (totalEl) totalEl.textContent = formatFCFA(totals.total);

    return totals;
  }

  if (discountTypeSelect) {
    var savedType = sessionStorage.getItem(DISCOUNT_TYPE_KEY);
    if (savedType) {
      discountTypeSelect.value = savedType;
      if (discountValueField) discountValueField.style.display = savedType === "NONE" ? "none" : "block";
    }
    if (discountValueField) {
      var savedValue = sessionStorage.getItem(DISCOUNT_VALUE_KEY);
      if (savedValue) discountValueField.value = savedValue;
    }

    discountTypeSelect.addEventListener("change", function () {
      if (discountValueField) {
        discountValueField.style.display = discountTypeSelect.value === "NONE" ? "none" : "block";
      }
      sessionStorage.setItem(DISCOUNT_TYPE_KEY, discountTypeSelect.value);
      updateTotalsDisplay();
    });
  }
  if (discountValueField) {
    discountValueField.addEventListener("input", function () {
      sessionStorage.setItem(DISCOUNT_VALUE_KEY, discountValueField.value);
      updateTotalsDisplay();
    });
  }

  updateTotalsDisplay();

  // -------------------------------------------------------------------
  // Paiements : montant pré-rempli au Total Net restant, déduit au fur
  // et à mesure que d'autres modes de paiement sont cochés
  // -------------------------------------------------------------------
  document.querySelectorAll(".payment-method-checkbox").forEach(function (checkbox) {
    checkbox.addEventListener("change", function () {
      var amountInput = document.querySelector('.payment-amount-input[data-method="' + checkbox.value + '"]');
      if (!amountInput) return;

      if (checkbox.checked) {
        amountInput.style.display = "block";
        var totals = updateTotalsDisplay() || computeTotals();
        var allocated = 0;
        document.querySelectorAll(".payment-amount-input").forEach(function (input) {
          if (input !== amountInput && input.style.display !== "none") {
            allocated += parseFloat(input.value) || 0;
          }
        });
        var remaining = totals ? Math.max(0, Math.round(totals.total - allocated)) : 0;
        amountInput.value = remaining;
      } else {
        amountInput.style.display = "none";
        amountInput.value = "";
      }
    });
  });

  ["validate-sale-form", "clear-cart-form"].forEach(function (formId) {
    var form = document.getElementById(formId);
    if (form) {
      form.addEventListener("submit", function () {
        sessionStorage.removeItem(DISCOUNT_TYPE_KEY);
        sessionStorage.removeItem(DISCOUNT_VALUE_KEY);
      });
    }
  });

  // -------------------------------------------------------------------
  // Déconnexion automatique à l'échéance de la session de caisse
  // -------------------------------------------------------------------
  var sessionEl = document.getElementById("cash-session-data");
  if (sessionEl) {
    var plannedClosedAt = new Date(sessionEl.getAttribute("data-planned-closed-at"));
    setInterval(function () {
      if (new Date() >= plannedClosedAt) {
        document.getElementById("auto-close-form").submit();
      }
    }, 15000);
  }
});
// Facturier Automatique - JavaScript minimal (vanilla, sans dépendance).
// - Recherche produit "en direct" à la Caisse, persistée jusqu'à réinitialisation
// - Réduction globale appliquée automatiquement au Total Net (calcul en direct)
// - Montant pré-rempli au Total Net dès qu'un mode de paiement est coché,
//   modifiable, avec déduction progressive pour chaque mode supplémentaire
// - Déconnexion automatique à l'échéance de la session de caisse

document.addEventListener("DOMContentLoaded", function () {
  var SEARCH_KEY = "facturier_product_search";
  var DISCOUNT_TYPE_KEY = "facturier_discount_type";
  var DISCOUNT_VALUE_KEY = "facturier_discount_value";

  // -------------------------------------------------------------------
  // 1) Recherche produit en direct, persistée jusqu'à réinitialisation
  // -------------------------------------------------------------------
  var searchInput = document.getElementById("product-search-input");
  var productRows = document.querySelectorAll("[data-product-row]");

  function applySearchFilter(query) {
    productRows.forEach(function (row) {
      var name = (row.getAttribute("data-product-name") || "").toLowerCase();
      row.style.display = name.indexOf(query) !== -1 ? "" : "none";
    });
  }

  if (searchInput) {
    var savedQuery = sessionStorage.getItem(SEARCH_KEY) || "";
    if (savedQuery) {
      searchInput.value = savedQuery;
      applySearchFilter(savedQuery.toLowerCase());
    }
    searchInput.addEventListener("input", function () {
      var query = searchInput.value.trim();
      sessionStorage.setItem(SEARCH_KEY, query);
      applySearchFilter(query.toLowerCase());
    });
  }

  var resetSearchBtn = document.getElementById("reset-search-btn");
  if (resetSearchBtn) {
    resetSearchBtn.addEventListener("click", function () {
      sessionStorage.removeItem(SEARCH_KEY);
      if (searchInput) {
        searchInput.value = "";
        applySearchFilter("");
      }
    });
  }

  // -------------------------------------------------------------------
  // 2) Réduction globale : calcul et affichage en direct (sans rechargement)
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
    // Restauration après un rechargement (ex : ajout d'un produit au panier)
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

  updateTotalsDisplay(); // calcule l'affichage initial (y compris après restauration)

  // -------------------------------------------------------------------
  // 3) Paiements : montant pré-rempli au Total Net restant, déduit au fur
  //    et à mesure que d'autres modes de paiement sont cochés
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

  // Nettoyage de la recherche/réduction mémorisées une fois la vente
  // validée ou le panier vidé (pour repartir sur une base propre)
  ["validate-sale-form", "clear-cart-form"].forEach(function (formId) {
    var form = document.getElementById(formId);
    if (form) {
      form.addEventListener("submit", function () {
        sessionStorage.removeItem(SEARCH_KEY);
        sessionStorage.removeItem(DISCOUNT_TYPE_KEY);
        sessionStorage.removeItem(DISCOUNT_VALUE_KEY);
      });
    }
  });

  // -------------------------------------------------------------------
  // 4) Déconnexion automatique à l'échéance de la session de caisse
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
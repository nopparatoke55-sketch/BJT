/*
 * Lab 04 progressive enhancement.
 *
 * The server always renders every field, so the form works without JavaScript.
 * When JS is available, hide fields that do not apply to the selected analysis
 * and keep the run-button label in sync.
 */
(function () {
  "use strict";

  var select = document.getElementById("analysis");
  if (!select) {
    return;
  }

  var labels = {
    dc: "Run DC (.op)",
    ac: "Run AC (.ac)",
    tran: "Run Transient (.tran)"
  };

  function update() {
    var mode = select.value;

    document.querySelectorAll("[data-analysis]").forEach(function (element) {
      var modes = element.getAttribute("data-analysis").split(/\s+/);
      element.hidden = modes.indexOf(mode) === -1;
    });

    var button = document.getElementById("run-sim");
    if (button && labels[mode]) {
      button.textContent = labels[mode];
    }
  }

  select.addEventListener("change", update);
  update();
})();

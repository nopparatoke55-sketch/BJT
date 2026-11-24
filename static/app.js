/*
 * Lab 04 progressive enhancement.
 *
 * The server always renders every field, so the form works without JavaScript.
 * When JS is available, hide fields that do not apply to the selected analysis
 * and keep the run-button label in sync.
 */
(function () {
  "use strict";

  var radios = document.querySelectorAll('input[name="analysis"]');
  if (!radios.length) {
    return;
  }

  var labels = {
    dc: "Run DC (.op)",
    ac: "Run AC (.ac)",
    tran: "Run Transient (.tran)"
  };

  function selectedMode() {
    for (var i = 0; i < radios.length; i += 1) {
      if (radios[i].checked) {
        return radios[i].value;
      }
    }
    return "dc";
  }

  function update() {
    var mode = selectedMode();

    document.querySelectorAll("[data-analysis]").forEach(function (element) {
      var modes = element.getAttribute("data-analysis").split(/\s+/);
      element.hidden = modes.indexOf(mode) === -1;
    });

    var button = document.getElementById("run-sim");
    if (button && labels[mode]) {
      button.textContent = labels[mode];
    }

    document.querySelectorAll(".analysis-strip span").forEach(function (badge) {
      badge.classList.toggle("active", badge.textContent.trim() === labels[mode].split(" ")[0]);
    });
  }

  radios.forEach(function (radio) {
    radio.addEventListener("change", update);
  });
  update();
})();

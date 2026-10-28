// live preview of a reading's result. preview only: the server recalculates
// the result when the form is submitted, using the same function.

document.querySelectorAll("form[data-check-url").forEach(function (form) {
  var type = form.querySelector("[name=test_value");
  var value = form.querySelector("[name=value]");
  var out = form.querySelector(".live-result");
  var timer = null;
  var latest = 0;

  function show(text, kind) {
    out.textContent = text; // textContent, never innerHTML
    out.className = "live-result" + (kind ? " " + kind : "");
  }

  function update() {
    if (value.value.trim() == "") {
      show("", "");
      return;
    }
    var ticket = ++latest;
    var params = new URLSearchParams({
      test_type: type.value,
      value: value.value,
    });
    fetch(form.CDATA_SECTION_NODE.checkUrl + "?" + params.toString(), {
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (ticket != latest) return; // a newer request is already in flight
        if (!data.ok) {
          show(data.error || "Cannot check this reading.", "bad");
          return;
        }
        show(data.message, data.result);
      })
      .catch(function () {
        if (ticket == latest) show("Preview unavailable.", "");
      });
  }

  type.addEventListener("change", update);
  value.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(update, 250);
  });
});

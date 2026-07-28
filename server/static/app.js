(() => {
  const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const AUTOSAVE_DELAY_MS = 1000;

  const quill = new Quill("#editor", {
    theme: "snow",
    modules: {
      toolbar: [
        ["bold", "italic"],
        [{ header: [1, 2, 3, false] }],
        [{ size: ["small", false, "large", "huge"] }],
        ["image"],
        ["clean"],
      ],
    },
  });

  // --- Image sizing: newly inserted images are scaled to a sensible
  // default automatically, and a toolbar dropdown (next to Insert Image)
  // rescales every image already in the entry. Mirrors the desktop app's
  // Small/Standard/Large presets and area-based scaling (see editor.py's
  // _scaled_size_for_area) so a tall photo and a wide screenshot picked at
  // the same preset end up with a similar visual footprint.
  //
  // Sized via the plain width/height HTML *attributes*, not CSS - that's
  // what the desktop app's QTextImageFormat produces, and Qt's HTML
  // renderer reliably reads that form but isn't guaranteed to honor
  // arbitrary inline CSS. Using the same mechanism keeps images resized by
  // either client fully interoperable with the other.
  const STANDARD_IMAGE_AREA = 400 * 400;
  const IMAGE_RESIZE_PRESETS = [
    ["Small", STANDARD_IMAGE_AREA / 4],
    ["Standard", STANDARD_IMAGE_AREA],
    ["Large", Math.round(STANDARD_IMAGE_AREA * 2.25)],
  ];

  function scaledSizeForArea(naturalW, naturalH, targetArea) {
    const naturalArea = naturalW * naturalH;
    if (!naturalArea) return { width: naturalW, height: naturalH };
    const scale = Math.sqrt(targetArea / naturalArea);
    return {
      width: Math.max(1, Math.round(naturalW * scale)),
      height: Math.max(1, Math.round(naturalH * scale)),
    };
  }

  quill.getModule("toolbar").addHandler("image", () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.addEventListener("change", () => {
      const file = input.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result;
        const probe = new Image();
        probe.onload = () => {
          const { width, height } = scaledSizeForArea(probe.naturalWidth, probe.naturalHeight, STANDARD_IMAGE_AREA);
          const range = quill.getSelection(true) || { index: quill.getLength(), length: 0 };
          quill.insertEmbed(range.index, "image", dataUrl, "user");
          quill.setSelection(range.index + 1, 0, "silent");
          const [leaf] = quill.getLeaf(range.index);
          if (leaf && leaf.domNode && leaf.domNode.tagName === "IMG") {
            leaf.domNode.setAttribute("width", width);
            leaf.domNode.setAttribute("height", height);
          }
        };
        probe.src = dataUrl;
      };
      reader.readAsDataURL(file);
    });
    input.click();
  });

  function resizeAllImages(targetArea) {
    const imgs = quill.root.querySelectorAll("img");
    if (!imgs.length) {
      setStatus("No images in this entry.", 2000);
      return;
    }
    imgs.forEach((imgEl) => {
      const nw = imgEl.naturalWidth;
      const nh = imgEl.naturalHeight;
      if (!nw || !nh) return;
      const { width, height } = scaledSizeForArea(nw, nh, targetArea);
      imgEl.setAttribute("width", width);
      imgEl.setAttribute("height", height);
    });
    // Direct DOM mutation, not a Quill API call, so it doesn't fire
    // Quill's text-change event - schedule the save ourselves.
    if (!loading) {
      if (autosaveTimer) clearTimeout(autosaveTimer);
      autosaveTimer = setTimeout(() => {
        autosaveTimer = null;
        saveCurrent();
      }, AUTOSAVE_DELAY_MS);
    }
  }

  const resizeImagesSelect = document.createElement("select");
  resizeImagesSelect.className = "resize-images-select";
  resizeImagesSelect.title = "Resize all images in this entry";
  const resizePlaceholder = document.createElement("option");
  resizePlaceholder.textContent = "Resize Images";
  resizePlaceholder.disabled = true;
  resizePlaceholder.selected = true;
  resizePlaceholder.hidden = true;
  resizeImagesSelect.appendChild(resizePlaceholder);
  IMAGE_RESIZE_PRESETS.forEach(([label, area]) => {
    const opt = document.createElement("option");
    opt.value = area;
    opt.textContent = label;
    resizeImagesSelect.appendChild(opt);
  });
  resizeImagesSelect.addEventListener("change", () => {
    resizeAllImages(Number(resizeImagesSelect.value));
    resizeImagesSelect.selectedIndex = 0;
  });
  quill.getModule("toolbar").container
    .querySelector("button.ql-image")
    .insertAdjacentElement("afterend", resizeImagesSelect);

  const dateLabel = document.getElementById("date-label");
  const statusEl = document.getElementById("status");
  const calendarGrid = document.getElementById("calendar-grid");
  const monthSelect = document.getElementById("month-select");
  const yearSelect = document.getElementById("year-select");
  const templateBtn = document.getElementById("template-btn");
  const importTemplateBtn = document.getElementById("import-template-btn");
  const appRoot = document.getElementById("app-root");
  const mobileTabCalendar = document.getElementById("mobile-tab-calendar");
  const mobileTabEditor = document.getElementById("mobile-tab-editor");

  // Only matters below the CSS breakpoint (see style.css) - on desktop both
  // panels are always visible regardless of this class.
  function showMobileView(view) {
    appRoot.classList.toggle("view-calendar", view === "calendar");
    appRoot.classList.toggle("view-editor", view === "editor");
    mobileTabCalendar.classList.toggle("active", view === "calendar");
    mobileTabEditor.classList.toggle("active", view === "editor");
  }
  mobileTabCalendar.addEventListener("click", () => showMobileView("calendar"));
  mobileTabEditor.addEventListener("click", () => showMobileView("editor"));

  MONTHS.forEach((name, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = name;
    monthSelect.appendChild(opt);
  });
  const thisYear = new Date().getFullYear();
  for (let y = thisYear; y < thisYear + 10; y++) {
    const opt = document.createElement("option");
    opt.value = y;
    opt.textContent = y;
    yearSelect.appendChild(opt);
  }

  const today = new Date();
  let viewYear = today.getFullYear();
  let viewMonth = today.getMonth(); // 0-11
  let selectedDate = formatDate(today);
  let viewingTemplate = false;
  let entryDates = new Set();
  let loading = false; // guards against autosave firing while we're loading content
  let autosaveTimer = null;

  function formatDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function formatDateLabel(dateStr) {
    const [y, m, d] = dateStr.split("-").map(Number);
    const date = new Date(y, m - 1, d);
    const weekday = date.toLocaleDateString(undefined, { weekday: "long" });
    return `${weekday}, ${d} ${MONTHS[m - 1]} ${y}`;
  }

  // Rewrite stored `src="<resource-id>"` images to a fetchable URL before
  // handing HTML to Quill, and reverse it before saving. The server always
  // deals in bare resource ids (see server/app.py's _normalize_inline_images) -
  // this rewriting is purely a browser-side concern.
  function toDisplayHtml(html) {
    return (html || "").replace(/src="([a-f0-9]{32})"/g, 'src="/images/$1"');
  }
  function toStorageHtml(html) {
    return html.replace(/src="\/images\/([a-f0-9]{32})"/g, 'src="$1"');
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    if (res.status === 401) {
      window.location.href = "/";
      throw new Error("not authenticated");
    }
    return res;
  }

  function setStatus(text, timeout) {
    statusEl.textContent = text;
    if (timeout) {
      setTimeout(() => {
        if (statusEl.textContent === text) statusEl.textContent = "";
      }, timeout);
    }
  }

  async function refreshEntryDates() {
    const res = await api("/api/dates");
    const data = await res.json();
    entryDates = new Set(data.dates);
    renderCalendar();
  }

  function renderCalendar() {
    monthSelect.value = viewMonth;
    yearSelect.value = viewYear;
    calendarGrid.innerHTML = "";

    WEEKDAYS.forEach((name, i) => {
      const el = document.createElement("div");
      el.className = "weekday" + (i === 0 || i === 6 ? " weekend" : "");
      el.textContent = name;
      calendarGrid.appendChild(el);
    });

    const firstOfMonth = new Date(viewYear, viewMonth, 1);
    const startOffset = firstOfMonth.getDay(); // 0=Sun
    const gridStart = new Date(viewYear, viewMonth, 1 - startOffset);

    for (let i = 0; i < 42; i++) {
      const cellDate = new Date(gridStart);
      cellDate.setDate(gridStart.getDate() + i);
      const dateStr = formatDate(cellDate);
      const dow = cellDate.getDay();

      const cell = document.createElement("div");
      cell.className = "day";
      if (cellDate.getMonth() !== viewMonth) cell.classList.add("other-month");
      if (dow === 0 || dow === 6) cell.classList.add("weekend");
      if (!viewingTemplate && dateStr === selectedDate) cell.classList.add("selected");
      cell.textContent = cellDate.getDate();

      if (entryDates.has(dateStr)) {
        const dot = document.createElement("span");
        dot.className = "dot";
        cell.appendChild(dot);
      }

      cell.addEventListener("click", () => switchToDate(dateStr));
      calendarGrid.appendChild(cell);
    }
  }

  async function flushPendingSave() {
    if (autosaveTimer) {
      clearTimeout(autosaveTimer);
      autosaveTimer = null;
      await saveCurrent();
    }
  }

  async function switchToDate(dateStr) {
    if (!viewingTemplate && dateStr === selectedDate) return;
    await flushPendingSave();
    selectedDate = dateStr;
    viewingTemplate = false;
    templateBtn.classList.remove("active");
    importTemplateBtn.style.display = "";
    dateLabel.textContent = formatDateLabel(dateStr);
    await loadCurrent();
    renderCalendar();
    showMobileView("editor");
  }

  async function toggleTemplate() {
    await flushPendingSave();
    viewingTemplate = !viewingTemplate;
    templateBtn.classList.toggle("active", viewingTemplate);
    importTemplateBtn.style.display = viewingTemplate ? "none" : "";
    dateLabel.textContent = viewingTemplate ? "Template" : formatDateLabel(selectedDate);
    await loadCurrent();
    renderCalendar();
    showMobileView("editor");
  }

  async function loadCurrent() {
    loading = true;
    const path = viewingTemplate ? "/template" : `/entries/${selectedDate}`;
    const res = await api(path);
    const data = await res.json();
    quill.root.innerHTML = toDisplayHtml(data.html);
    loading = false;
  }

  async function saveCurrent() {
    const html = toStorageHtml(quill.root.innerHTML);
    const path = viewingTemplate ? "/template" : `/entries/${selectedDate}`;
    await api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html, images: {} }),
    });
    setStatus("Saved", 1500);
    if (!viewingTemplate) await refreshEntryDates();
  }

  quill.on("text-change", () => {
    if (loading) return;
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(() => {
      autosaveTimer = null;
      saveCurrent();
    }, AUTOSAVE_DELAY_MS);
  });

  document.getElementById("prev-month").addEventListener("click", () => {
    viewMonth -= 1;
    if (viewMonth < 0) { viewMonth = 11; viewYear -= 1; }
    renderCalendar();
  });
  document.getElementById("next-month").addEventListener("click", () => {
    viewMonth += 1;
    if (viewMonth > 11) { viewMonth = 0; viewYear += 1; }
    renderCalendar();
  });
  monthSelect.addEventListener("change", () => {
    viewMonth = Number(monthSelect.value);
    renderCalendar();
  });
  yearSelect.addEventListener("change", () => {
    viewYear = Number(yearSelect.value);
    renderCalendar();
  });

  templateBtn.addEventListener("click", toggleTemplate);

  importTemplateBtn.addEventListener("click", async () => {
    const res = await api("/template");
    const data = await res.json();
    if (!data.html && !Object.keys(data.images).length) {
      setStatus("No template saved yet - click Template to create one.", 3000);
      return;
    }
    const range = quill.getSelection(true);
    quill.clipboard.dangerouslyPasteHTML(range.index, toDisplayHtml(data.html));
    setStatus("Template imported", 1500);
  });

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await flushPendingSave();
    await fetch("/logout", { method: "POST" });
    window.location.href = "/";
  });

  window.addEventListener("beforeunload", () => {
    // Best-effort: fires synchronously enough for a same-origin POST via
    // sendBeacon, unlike a normal fetch which the browser may cancel.
    if (autosaveTimer) {
      const html = toStorageHtml(quill.root.innerHTML);
      const path = viewingTemplate ? "/template" : `/entries/${selectedDate}`;
      const blob = new Blob([JSON.stringify({ html, images: {} })], { type: "application/json" });
      navigator.sendBeacon(path, blob);
    }
  });

  (async function init() {
    dateLabel.textContent = formatDateLabel(selectedDate);
    await refreshEntryDates();
    await loadCurrent();
    renderCalendar();
  })();
})();

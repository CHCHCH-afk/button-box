"use strict";

// Personal Audio Book UI. Shared with setup; imports become available in runtime.
(() => {
  const status = document.getElementById("books-status");
  const list = document.getElementById("books-list");
  const picker = document.getElementById("books-files");
  const browse = document.getElementById("books-browse");
  const drop = document.getElementById("books-drop");
  const progress = document.getElementById("books-progress");
  let timer;
  let uploading = false;
  let fingerprint = "";

  async function api(path, payload) {
    const response = await fetch(path, payload === undefined ? { cache: "no-store" } : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Audio Book will be available once Button Box setup is complete.");
    return data;
  }

  function size(bytes) {
    return `${(bytes / 1e6).toLocaleString("en", { maximumFractionDigits: 2 })} MB`;
  }

  function storageSize(bytes) {
    return `${(bytes / 1e9).toLocaleString("en", { minimumFractionDigits: 1, maximumFractionDigits: 2 })} GB`;
  }

  async function action(payload) {
    try {
      await api("/api/audio-books", payload);
      status.textContent = payload.action === "pair" ? "Remove any card, then scan the card you want to pair within two minutes." : "Changes saved.";
      await load();
    } catch (error) {
      status.textContent = error.message;
    }
  }

  function button(label, callback) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "secondary compact";
    element.textContent = label;
    element.addEventListener("click", callback);
    return element;
  }

  function render(books) {
    const next = JSON.stringify(books);
    if (next === fingerprint) return;
    fingerprint = next;
    list.replaceChildren();
    if (!books.length) {
      const empty = document.createElement("p");
      empty.textContent = "Your library is empty. Add your first book above.";
      list.append(empty);
    }
    for (const book of books) {
      const row = document.createElement("article");
      row.className = "book-entry";
      const heading = document.createElement("h2");
      heading.textContent = book.title;
      const details = document.createElement("p");
      details.textContent = `${Math.ceil(book.seconds / 60)} min · ${size(book.bytes)} · ${book.paired ? "Card paired" : "No NFC card"}`;
      const name = document.createElement("input");
      name.value = book.title;
      name.maxLength = 120;
      name.setAttribute("aria-label", `Title of ${book.title}`);
      const controls = document.createElement("div");
      controls.className = "button-row";
      controls.append(
        button("Rename", () => action({ action: "rename", id: book.id, title: name.value })),
        button(book.paired ? "Change NFC card" : "Pair NFC card", () => action({ action: "pair", id: book.id })),
      );
      if (book.paired) controls.append(button("Unpair card", () => action({ action: "unpair", id: book.id })));
      controls.append(button("Delete", () => {
        if (window.confirm(`Delete “${book.title}” from the microSD and remove its NFC association?`)) {
          action({ action: "delete", id: book.id });
        }
      }));
      row.append(heading, details, name, controls);
      list.append(row);
    }
  }

  async function load() {
    window.clearTimeout(timer);
    if (location.hash !== "#audio-book") return;
    try {
      const data = await api("/api/audio-books");
      document.getElementById("books-storage").textContent = `${storageSize(data.free_bytes)} free of ${storageSize(data.total_bytes)} · microSD storage`;
      const pairing = data.pairing;
      const messages = {
        waiting: "Waiting for an NFC card… Remove the card, then scan it.",
        paired: "NFC card paired. Remove it, then scan it to play the book.",
        expired: "Pairing timed out. Select Pair NFC card to try again.",
        error: pairing?.error || "Pairing failed. Please try again.",
      };
      document.getElementById("books-pairing").textContent = pairing ? messages[pairing.status] || "" : data.reader_ready ? "NFC reader ready." : "NFC reader unavailable. You can still upload books.";
      document.getElementById("books-cancel-pair").hidden = pairing?.status !== "waiting";
      const playing = data.player;
      const book = data.books.find((entry) => entry.id === playing.book);
      document.getElementById("books-playing").textContent = playing.error || (book ? `${playing.paused ? "Paused" : "Playing"} : ${book.title}. WhatsApp notifications wait until the book ends.` : "");
      render(data.books);
    } catch (error) {
      if (!uploading) status.textContent = error.message;
    } finally {
      if (location.hash === "#audio-book") timer = window.setTimeout(load, 2000);
    }
  }

  function upload(file, uploadId) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/audio-books/upload");
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.setRequestHeader("X-Audio-Filename", encodeURIComponent(file.name));
      xhr.setRequestHeader("X-Audio-Upload-ID", uploadId);
      xhr.timeout = 15 * 60 * 1000;
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) progress.value = event.loaded / event.total;
        status.textContent = event.loaded === event.total ? `Checking and preparing “${file.name}”…` : `Uploading “${file.name}”…`;
      });
      xhr.addEventListener("load", () => {
        let data;
        try { data = JSON.parse(xhr.responseText); } catch { data = {}; }
        if (xhr.status >= 200 && xhr.status < 300 && data.ok && data.id) resolve(data);
        else reject(Object.assign(new Error(data.error || "Import failed. Please try again."), {
          retryable: xhr.status === 0 || xhr.status === 408 || xhr.status === 429 || xhr.status >= 500,
        }));
      });
      xhr.addEventListener("error", () => reject(Object.assign(new Error("Connection interrupted. Check the library before trying again."), { retryable: true })));
      xhr.addEventListener("timeout", () => reject(Object.assign(new Error("Upload timed out. Check the library before trying again."), { retryable: true })));
      xhr.send(file);
    });
  }

  async function uploadWithRetry(file) {
    const uploadId = Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        return await upload(file, uploadId);
      } catch (error) {
        if (!error.retryable || attempt === 3) throw error;
        status.textContent = `Connection problem. Retrying “${file.name}” (${attempt + 1}/3)…`;
        await new Promise((resolve) => window.setTimeout(resolve, attempt * 2000));
        progress.value = 0;
      }
    }
  }

  async function uploadFiles(files) {
    if (uploading || !files.length) return;
    uploading = true;
    picker.disabled = true;
    browse.disabled = true;
    progress.hidden = false;
    let imported = 0;
    const errors = [];
    for (const file of files) {
      progress.value = 0;
      try {
        if (!/\.(mp3|wav|ogg|m4a|flac|aac)$/i.test(file.name)) throw new Error("Unsupported format.");
        if (!file.size || file.size > 256 * 1024 * 1024) throw new Error("The file is empty or larger than 256 MB.");
        status.textContent = `Uploading “${file.name}”…`;
        await uploadWithRetry(file);
        imported++;
      } catch (error) {
        errors.push(`${file.name} : ${error.message}`);
      }
    }
    uploading = false;
    picker.disabled = false;
    browse.disabled = false;
    picker.value = "";
    progress.hidden = true;
    status.textContent = `${imported} book(s) saved to the microSD.${errors.length ? ` ${errors.join(" ")}` : ""}`;
    await load();
  }

  picker.addEventListener("change", () => uploadFiles(Array.from(picker.files)));
  browse.addEventListener("click", () => picker.click());
  for (const event of ["dragenter", "dragover"]) drop.addEventListener(event, (e) => {
    e.preventDefault();
    drop.classList.add("book-dragging");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("book-dragging"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("book-dragging");
    uploadFiles(Array.from(event.dataTransfer.files));
  });
  document.getElementById("books-cancel-pair").addEventListener("click", () => action({ action: "cancel_pair" }));
  window.addEventListener("hashchange", load);
  load();
})();

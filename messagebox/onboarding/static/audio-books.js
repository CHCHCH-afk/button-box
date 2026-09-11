"use strict";

// Personal Audio Book UI. Shared with setup; imports become available in runtime.
(() => {
  const status = document.getElementById("books-status");
  const list = document.getElementById("books-list");
  const picker = document.getElementById("books-files");
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
    if (!response.ok) throw new Error(data.error || "Audio Book sera disponible une fois la configuration de la box terminée.");
    return data;
  }

  function size(bytes) {
    return `${(bytes / 1024 / 1024).toLocaleString("fr", { maximumFractionDigits: 0 })} Mo`;
  }

  async function action(payload) {
    try {
      await api("/api/audio-books", payload);
      status.textContent = payload.action === "pair" ? "Retirez toute carte, puis présentez celle à associer dans les deux minutes." : "Modification enregistrée.";
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
      empty.textContent = "Votre bibliothèque est vide. Ajoutez votre premier livre ci-dessus.";
      list.append(empty);
    }
    for (const book of books) {
      const row = document.createElement("article");
      row.className = "book-entry";
      const heading = document.createElement("h2");
      heading.textContent = book.title;
      const details = document.createElement("p");
      details.textContent = `${Math.ceil(book.seconds / 60)} min · ${size(book.bytes)} · ${book.paired ? "Carte associée" : "Sans carte NFC"}`;
      const name = document.createElement("input");
      name.value = book.title;
      name.maxLength = 120;
      name.setAttribute("aria-label", `Titre de ${book.title}`);
      const controls = document.createElement("div");
      controls.className = "button-row";
      controls.append(
        button("Renommer", () => action({ action: "rename", id: book.id, title: name.value })),
        button(book.paired ? "Changer la carte NFC" : "Associer une carte NFC", () => action({ action: "pair", id: book.id })),
      );
      if (book.paired) controls.append(button("Dissocier la carte", () => action({ action: "unpair", id: book.id })));
      controls.append(button("Supprimer", () => {
        if (window.confirm(`Supprimer « ${book.title} » de la microSD et retirer son association NFC ?`)) {
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
      document.getElementById("books-storage").textContent = `${size(data.free_bytes)} libres sur ${size(data.total_bytes)} · stockage sur la microSD`;
      const pairing = data.pairing;
      const messages = {
        waiting: "En attente de la carte NFC… Retirez puis présentez la carte.",
        paired: "Carte NFC associée. Retirez-la puis présentez-la pour écouter le livre.",
        expired: "Le délai d’appariage est écoulé. Cliquez à nouveau sur Associer.",
        error: pairing?.error || "L’association a échoué. Réessayez.",
      };
      document.getElementById("books-pairing").textContent = pairing ? messages[pairing.status] || "" : data.reader_ready ? "Lecteur NFC prêt." : "Lecteur NFC indisponible : l’import reste possible.";
      document.getElementById("books-cancel-pair").hidden = pairing?.status !== "waiting";
      const playing = data.player;
      const book = data.books.find((entry) => entry.id === playing.book);
      document.getElementById("books-playing").textContent = playing.error || (book ? `${playing.paused ? "En pause" : "En lecture"} : ${book.title}. Les notifications WhatsApp attendent la fin du livre.` : "");
      render(data.books);
    } catch (error) {
      if (!uploading) status.textContent = error.message;
    } finally {
      if (location.hash === "#audio-book") timer = window.setTimeout(load, 2000);
    }
  }

  function upload(file) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/audio-books/upload");
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.setRequestHeader("X-Audio-Filename", encodeURIComponent(file.name));
      xhr.timeout = 15 * 60 * 1000;
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) progress.value = event.loaded / event.total;
        status.textContent = event.loaded === event.total ? `Vérification et préparation de « ${file.name} »…` : `Transfert de « ${file.name} »…`;
      });
      xhr.addEventListener("load", () => {
        let data;
        try { data = JSON.parse(xhr.responseText); } catch { data = {}; }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error(data.error || "L’import a échoué. Réessayez."));
      });
      xhr.addEventListener("error", () => reject(new Error("Connexion interrompue. Vérifiez la bibliothèque avant de réessayer.")));
      xhr.addEventListener("timeout", () => reject(new Error("Le transfert a expiré. Vérifiez la bibliothèque avant de réessayer.")));
      xhr.send(file);
    });
  }

  async function uploadFiles(files) {
    if (uploading || !files.length) return;
    uploading = true;
    picker.disabled = true;
    progress.hidden = false;
    let imported = 0;
    const errors = [];
    for (const file of files) {
      progress.value = 0;
      try {
        if (!/\.(mp3|wav|ogg|m4a|flac|aac)$/i.test(file.name)) throw new Error("Format incompatible.");
        if (!file.size || file.size > 256 * 1024 * 1024) throw new Error("Fichier vide ou supérieur à 256 Mo.");
        status.textContent = `Transfert de « ${file.name} »…`;
        await upload(file);
        imported++;
      } catch (error) {
        errors.push(`${file.name} : ${error.message}`);
      }
    }
    uploading = false;
    picker.disabled = false;
    picker.value = "";
    progress.hidden = true;
    status.textContent = `${imported} livre(s) enregistré(s) sur la microSD.${errors.length ? ` ${errors.join(" ")}` : ""}`;
    await load();
  }

  picker.addEventListener("change", () => uploadFiles(Array.from(picker.files)));
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

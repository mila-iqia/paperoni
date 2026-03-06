let dictionary = [];
let currentLang = "en";

export async function initTranslation() {
  // Determine initial language first so components know what to target right away
  currentLang = localStorage.getItem("paperoni-lang");
  if (!currentLang) {
    const browserLang = navigator.language || navigator.userLanguage || "en";
    currentLang = browserLang.startsWith("fr") ? "fr" : "en";
  }
  document.cookie = `paperoni-lang=${encodeURIComponent(currentLang)}; path=/; max-age=31536000; samesite=lax`;
  document.documentElement.lang = currentLang;
  updateMarkdownVisibility(currentLang);

  try {
    const response = await fetch("/assets/translate.json");
    if (response.ok) {
      dictionary = await response.json();
    }
  } catch (e) {
    console.error("Failed to load translation dictionary", e);
  }

  const langBtns = document.querySelectorAll(".lang-stacked-btn");
  if (langBtns.length > 0) {
    updateLabels(currentLang);
    langBtns.forEach(btn => {
        btn.addEventListener("click", (e) => {
            const newLang = e.target.getAttribute("data-lang");
            setLanguage(newLang);
            updateLabels(newLang);
        });
    });
  }

  // Initial translation for standard <loc> tags and page title
  setLanguage(currentLang);

}

function updateLabels(lang) {
  const langBtns = document.querySelectorAll(".lang-stacked-btn");
  langBtns.forEach(btn => {
      if (btn.getAttribute("data-lang") === lang) {
          btn.classList.add("active");
      } else {
          btn.classList.remove("active");
      }
  });
}

function updatePageTitle(lang) {
  const titleEl = document.getElementById("docTitle");
  const h1El = document.querySelector("h1.page-title");
  const key = titleEl?.getAttribute("data-title-key") || h1El?.getAttribute("data-title-key");
  if (!key) return;
  const entry = dictionary.find((e) => e.en === key);
  const translated = (entry && entry[lang]) ? entry[lang] : key;
  if (titleEl) document.title = translated;
  if (h1El) h1El.textContent = translated;
}

function updateMarkdownVisibility(lang) {
  const contents = document.querySelectorAll(".markdown-content[data-lang]");
  const hasMatch = Array.from(contents).some((el) => el.getAttribute("data-lang") === lang);
  const showLang = hasMatch ? lang : "en";
  contents.forEach((el) => {
    el.style.display = el.getAttribute("data-lang") === showLang ? "block" : "none";
  });
}

export function setLanguage(lang) {
  localStorage.setItem("paperoni-lang", lang);
  currentLang = lang;
  document.cookie = `paperoni-lang=${encodeURIComponent(lang)}; path=/; max-age=31536000; samesite=lax`;

  document.documentElement.lang = lang; // Update html lang attribute

  setLanguageNode(document, lang);
  updatePageTitle(lang);
  updateMarkdownVisibility(lang);
}

export function getTranslation(key) {
  const entry = dictionary.find((e) => e.en === key);
  return (entry && entry[currentLang]) ? entry[currentLang] : key;
}

export function setLanguageNode(rootNode, lang) {
  const targetLang = lang || currentLang;
  const locTags = rootNode.querySelectorAll("loc");
  locTags.forEach((loc) => translateNode(loc, targetLang, dictionary));
  rootNode.querySelectorAll("[data-loc-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-loc-placeholder");
    if (!key) return;
    const entry = dictionary.find((e) => e.en === key);
    const translated = (entry && entry[targetLang]) ? entry[targetLang] : (targetLang === "en" ? key : key);
    if (el.placeholder !== undefined) {
      el.placeholder = translated;
    } else {
      el.setAttribute("data-placeholder", translated);
    }
  });
  rootNode.querySelectorAll("[data-loc-title]").forEach((el) => {
    const key = el.getAttribute("data-loc-title");
    if (!key) return;
    const entry = dictionary.find((e) => e.en === key);
    if (entry && entry[targetLang]) el.setAttribute("title", entry[targetLang]);
    else if (targetLang === "en") el.setAttribute("title", key);
  });
}

function translateNode(loc, targetLang, dictionary) {
  const nodeLang = loc.getAttribute("lang") || "en";
  if (nodeLang === targetLang) {
      return; 
  }

  let patternParts = [];
  let childrenNodes = [];
  let childIndex = 1;

  // Store original untranslated state on the element if not already stored
  if (!loc._originalNodes) {
      loc._originalNodes = Array.from(loc.childNodes).map(n => n.cloneNode(true));
      loc._originalLang = nodeLang;
  }

  // Always translate FROM the original English (or original language) mapping
  // because translating from FR -> EN using the DOM nodes is messy if the template structure changed
  const sourceNodes = loc._originalNodes;
  const sourceLang = loc._originalLang;

  sourceNodes.forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      patternParts.push(node.textContent);
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      patternParts.push(`{${childIndex}}`);
      childrenNodes.push({ index: childIndex, node: node.cloneNode(true) });
      childIndex++;
    }
  });

  let patternString = patternParts.join("").trim().replace(/\s+/g, " ");

  if (!patternString) {
      return; 
  }

  // Find in dictionary using the ORIGINAL language pattern
  const entry = dictionary.find((e) => {
    const text = e[sourceLang];
    if (!text) return false;
    return text.trim().replace(/\s+/g, " ") === patternString;
  });

  if (entry && entry[targetLang]) {
    const targetPattern = entry[targetLang];
    loc.innerHTML = "";
    
    const parts = targetPattern.split(/(\{.*?\})/);
    parts.forEach((part) => {
      const match = part.match(/\{(\d+)\}/);
      if (match) {
        const idx = parseInt(match[1], 10);
        const savedInfo = childrenNodes.find((c) => c.index === idx);
        if (savedInfo) {
          loc.appendChild(savedInfo.node);
        }
      } else if (part) {
        loc.appendChild(document.createTextNode(part));
      }
    });

    loc.setAttribute("lang", targetLang);
  } else if (targetLang === sourceLang) {
     // Revert to original
     loc.innerHTML = "";
     sourceNodes.forEach(n => loc.appendChild(n.cloneNode(true)));
     loc.setAttribute("lang", targetLang);
  }
}

initTranslation();
document.addEventListener("DOMContentLoaded", () => {
    // If initTranslation is already called, we might just need to ensure toggle bindings are attached
    // since the DOM wasn't ready during the first synchronous call for the toggle elements.
    const langBtns = document.querySelectorAll(".lang-stacked-btn");
    if (langBtns.length > 0 && !langBtns[0].dataset.bound) {
        updateLabels(currentLang);
        langBtns.forEach(btn => {
            btn.dataset.bound = "true";
            btn.addEventListener("click", (e) => {
                const newLang = e.target.getAttribute("data-lang");
                setLanguage(newLang);
                updateLabels(newLang);
            });
        });
    }
});

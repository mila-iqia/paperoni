
export function clip(container) {
    container.onclick = () => {
        var here = window.location.href.split(/[?#]/)[0];
        var element = container.querySelector(".copiable");
        navigator.clipboard.writeText(here + element.textContent);
    }
}

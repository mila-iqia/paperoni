/**
 * Convert an HTML tagged template literal to a DOM node.
 * Supports interpolating strings, DOM nodes, and arrays in both content and attributes.
 *
 * @example
 * const node = html`<div class="container">Hello ${name}</div>`;
 * const nested = html`<div>${someNode}</div>`;
 * const link = html`<a href="/path/${id}">Link</a>`;
 * const list = html`<ul>${items.map(i => html`<li>${i}</li>`)}</ul>`;
 * const optional = html`<div>${maybeNull}</div>`; // null/undefined renders nothing
 */
export function html(strings, ...values) {
    // Create unique markers for each value
    // Use HTML comments for content (allowed everywhere) and text for attributes
    const commentMarkers = values.map((_, i) => `<!--__HTML_PLACEHOLDER_${i}__-->`);

    // Build the HTML string with comment markers
    let htmlString = '';
    for (let i = 0; i < strings.length; i++) {
        htmlString += strings[i];
        if (i < values.length) {
            // Use comment markers for element content (they work everywhere including tables)
            htmlString += commentMarkers[i];
        }
    }

    // Parse the HTML
    const template = document.createElement('template');
    template.innerHTML = htmlString.trim();
    const fragment = template.content;

    // Walk the DOM and replace markers
    function walkAndReplace(node) {
        // Replace markers in attributes
        if (node.nodeType === Node.ELEMENT_NODE) {
            Array.from(node.attributes).forEach(attr => {
                values.forEach((value, index) => {
                    if (attr.value.includes(commentMarkers[index])) {
                        let replacement;
                        if (value == null) {
                            replacement = '';
                        } else if (Array.isArray(value)) {
                            replacement = value.map(v => v == null ? '' : String(v)).join('');
                        } else {
                            replacement = String(value);
                        }
                        attr.value = attr.value.replace(commentMarkers[index], replacement);
                    }
                });
            });

            // Recursively process child nodes
            Array.from(node.childNodes).forEach(child => walkAndReplace(child));
        }

        // Replace markers in comment nodes (used for content interpolation)
        if (node.nodeType === Node.COMMENT_NODE && node.parentNode) {
            const commentText = node.textContent;

            // Check if this comment is one of our markers
            values.forEach((value, index) => {
                if (commentText === `__HTML_PLACEHOLDER_${index}__`) {
                    const parent = node.parentNode;
                    const nodesToInsert = [];

                    // Add the value (node, array of nodes, or text)
                    if (value == null) {
                        // null or undefined - insert nothing
                    } else if (Array.isArray(value)) {
                        // Array of nodes - insert all children
                        value.forEach(item => {
                            if (item instanceof Node) {
                                nodesToInsert.push(item);
                            } else if (item != null) {
                                nodesToInsert.push(document.createTextNode(String(item)));
                            }
                        });
                    } else if (value instanceof Node) {
                        nodesToInsert.push(value);
                    } else {
                        nodesToInsert.push(document.createTextNode(String(value)));
                    }

                    // Replace the comment node with all the new nodes
                    nodesToInsert.forEach(newNode => {
                        parent.insertBefore(newNode, node);
                    });
                    parent.removeChild(node);
                }
            });
        }
    }

    // Walk all children of the fragment
    Array.from(fragment.childNodes).forEach(child => walkAndReplace(child));

    // Return the first child if there's only one, otherwise return the fragment
    return fragment.childNodes.length === 1 ? fragment.firstChild : fragment;
}

/**
 * Create a toggleable pair of elements. Mark elements with `toggler` and `toggled` attributes
 * to indicate which element is clickable and which is toggled. These attributes are removed
 * after the toggle behavior is set up.
 *
 * @example
 * const pair = toggle`
 *   <div class="header" toggler>
 *     <span class="item-toggle">▶</span>
 *     Title
 *   </div>
 *   <div class="content" toggled>Hidden content</div>
 * `;
 */
export function toggle(strings, ...values) {
    // Use html to create the structure
    const fragment = html(strings, ...values);

    // Find elements with toggler and toggled attributes
    const togglerElement = fragment.querySelector('[toggler]');
    const toggledElement = fragment.querySelector('[toggled]');

    if (!togglerElement) {
        throw new Error('toggle`` requires an element with the "toggler" attribute');
    }
    if (!toggledElement) {
        throw new Error('toggle`` requires an element with the "toggled" attribute');
    }

    // Add click handler to the toggler element
    togglerElement.addEventListener('click', () => {
        toggledElement.classList.toggle('expanded');
        togglerElement.classList.toggle('expanded');
    });

    // Remove the temporary attributes
    togglerElement.removeAttribute('toggler');
    toggledElement.removeAttribute('toggled');

    // Return fragment containing all elements
    return fragment;
}

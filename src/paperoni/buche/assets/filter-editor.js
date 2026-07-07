import { basicSetup, EditorView } from 'https://esm.sh/codemirror';
import { EditorState, Prec } from 'https://esm.sh/@codemirror/state';
import { keymap } from 'https://esm.sh/@codemirror/view';
import { indentWithTab } from 'https://esm.sh/@codemirror/commands';
import { python } from 'https://esm.sh/@codemirror/lang-python';
import { oneDark } from 'https://esm.sh/@codemirror/theme-one-dark';

export function install() {
    const runKeymap = Prec.highest(keymap.of([
        { key: 'Ctrl-Enter', run: () => { window.runFilter().then(ok => ok && window.commitFilterEditor()); return true; } },
        { key: 'Mod-Enter', run: () => { window.runFilter().then(ok => ok && window.commitFilterEditor()); return true; } },
        { key: 'Escape', run: () => { window.closeFilterEditor(); return true; } },
    ]));
    
    const view = new EditorView({
        state: EditorState.create({
            doc: 'return True',
            extensions: [basicSetup, oneDark, keymap.of([indentWithTab]), runKeymap, python()],
        }),
        parent: document.getElementById('filter-editor-host'),
    });
    
    window.FILTER_EDITOR = view;
    if (window._pendingFilterCode != null) {
        const pending = window._pendingFilterCode;
        window._pendingFilterCode = null;
        view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: pending } });
    }
    view.focus();
}


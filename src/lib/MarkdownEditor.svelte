<script lang="ts">
  import { onMount } from 'svelte';
  import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
  import { markdown } from '@codemirror/lang-markdown';
  import { EditorState, type Range } from '@codemirror/state';
  import { Decoration, EditorView, keymap, ViewPlugin, type DecorationSet, type ViewUpdate } from '@codemirror/view';

  let { value = $bindable() }: { value: string } = $props();
  let host: HTMLDivElement;
  let editor: EditorView | undefined;

  function livePreview(view: EditorView): DecorationSet {
    const decorations: Range<Decoration>[] = [];
    const touches = (from: number, to: number) => view.state.selection.ranges.some((range) => range.from <= to + 1 && range.to >= from - 1);

    for (let lineNumber = 1; lineNumber <= view.state.doc.lines; lineNumber += 1) {
      const line = view.state.doc.line(lineNumber);
      const heading = /^(#{1,6})([\t ]+)/.exec(line.text);
      if (heading) {
        const level = heading[1].length;
        decorations.push(Decoration.line({ attributes: { class: `cm-live-heading cm-live-heading-${level}` } }).range(line.from));
        if (!touches(line.from, line.to)) {
          decorations.push(Decoration.replace({}).range(line.from, line.from + heading[0].length));
        }
      }

      const links = /\[([^\]]+)]\(([^)]+)\)/g;
      const linkRanges: Array<{ from: number; to: number }> = [];
      for (const match of line.text.matchAll(links)) {
        const start = line.from + (match.index ?? 0);
        const end = start + match[0].length;
        const labelStart = start + 1;
        const labelEnd = labelStart + match[1].length;
        linkRanges.push({ from: start, to: end });
        decorations.push(Decoration.mark({ class: 'cm-live-link' }).range(labelStart, labelEnd));
        if (!touches(start, end)) {
          decorations.push(Decoration.replace({}).range(start, labelStart));
          decorations.push(Decoration.replace({}).range(labelEnd, end));
        }
      }

      const emphasis = /([*_])(?=\S)(.+?\S)\1/g;
      for (const match of line.text.matchAll(emphasis)) {
        const start = line.from + (match.index ?? 0);
        const end = start + match[0].length;
        if (linkRanges.some((link) => start < link.to && end > link.from)) continue;
        const contentStart = start + 1;
        const contentEnd = end - 1;
        decorations.push(Decoration.mark({ class: 'cm-live-emphasis' }).range(contentStart, contentEnd));
        if (!touches(start, end)) {
          decorations.push(Decoration.replace({}).range(start, contentStart));
          decorations.push(Decoration.replace({}).range(contentEnd, end));
        }
      }
    }
    return Decoration.set(decorations, true);
  }

  const livePreviewPlugin = ViewPlugin.fromClass(class {
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = livePreview(view);
    }

    update(update: ViewUpdate) {
      if (update.docChanged || update.selectionSet || update.viewportChanged) {
        this.decorations = livePreview(update.view);
      }
    }
  }, { decorations: (plugin) => plugin.decorations });

  onMount(() => {
    editor = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: value,
        extensions: [
          history(),
          markdown(),
          keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
          EditorView.lineWrapping,
          EditorView.contentAttributes.of({ 'aria-label': 'Song list Markdown editor', spellcheck: 'false' }),
          livePreviewPlugin,
          EditorView.updateListener.of((update) => {
            if (update.docChanged) value = update.state.doc.toString();
          }),
          EditorView.theme({
            '&': {
              minHeight: '520px',
              border: '1px solid rgba(var(--line), .45)',
              borderRadius: '2px',
              color: 'rgb(var(--foreground))',
              backgroundColor: 'rgba(var(--surface-strong), .95)'
            },
            '&.cm-focused': {
              outline: 'none',
              borderColor: 'rgb(var(--accent))',
              boxShadow: '0 0 0 3px rgba(var(--accent), .18)'
            },
            '.cm-scroller': {
              minHeight: '520px',
              fontFamily: "'Montserrat', Arial, sans-serif",
              lineHeight: '1.55'
            },
            '.cm-line': { padding: '0 0 .12rem' },
            '.cm-gutters': { display: 'none' },
            '.cm-content': { padding: '1rem .9rem 3rem' },
            '&.cm-focused .cm-cursor, .cm-dropCursor': { borderLeftColor: 'rgb(var(--foreground)) !important' },
            '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': {
              backgroundColor: 'rgba(var(--accent), .25)'
            },
            '.cm-live-heading': { fontWeight: '700', paddingTop: '.85rem', paddingBottom: '.25rem' },
            '.cm-live-heading-1': { fontSize: '1.7rem', lineHeight: '1.3' },
            '.cm-live-heading-2': { fontSize: '1.35rem', lineHeight: '1.35' },
            '.cm-live-heading-3': { fontSize: '1.15rem' },
            '.cm-live-heading-4, .cm-live-heading-5, .cm-live-heading-6': { fontSize: '1rem' },
            '.cm-live-emphasis': { fontStyle: 'italic' },
            '.cm-live-link': { color: 'rgb(var(--green))', textDecoration: 'underline', textUnderlineOffset: '2px' }
          })
        ]
      })
    });
    return () => editor?.destroy();
  });

  $effect(() => {
    if (!editor) return;
    const current = editor.state.doc.toString();
    if (value !== current) {
      editor.dispatch({ changes: { from: 0, to: current.length, insert: value } });
    }
  });
</script>

<div class="markdown-editor" bind:this={host}></div>

<style>
  .markdown-editor {
    width: 100%;
    min-width: 0;
  }
</style>

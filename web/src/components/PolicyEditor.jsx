import { useEffect } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import { Table, TableCell, TableHeader, TableRow } from '@tiptap/extension-table'
import {
  Bold, Italic, Link2, List, ListOrdered, Redo2, Table as TableIcon, Undo2,
} from 'lucide-react'

// The editor a company rewrites its own policies in.
//
// Tiptap rather than TinyMCE, which is GPL and cannot ship in a commercial product without a
// licence. Core and every extension used here are MIT, checked against the installed packages
// rather than against the documentation.
//
// What the editor has to protect is the merge fields. {company}, {derline} and {safetyline} fill
// from live data every time the policy is rendered, and an editor that mangled the braces would
// leave a document that silently stopped filling itself in. They are offered from a menu rather
// than typed, and nothing here transforms text, so the braces pass through untouched.

const HEADINGS = [
  ['Body text', 0],
  ['Heading', 2],
  ['Sub-heading', 3],
]

export default function PolicyEditor({ value, onChange, fields = [] }) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ link: false }),
      Link.configure({ openOnClick: false }),
      // `resizable` off on purpose: a policy prints, and a column somebody dragged on screen is
      // not a column anybody meant to set.
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content: value || '',
    onUpdate: ({ editor: e }) => onChange(e.getHTML()),
  })

  // Reverting to the published wording replaces the words under the editor, which it has no way of
  // noticing on its own.
  useEffect(() => {
    if (editor && value != null && value !== editor.getHTML()) {
      editor.commands.setContent(value, { emitUpdate: false })
    }
  }, [editor, value])

  if (!editor) return null
  const level = editor.getAttributes('heading').level || 0
  const chain = () => editor.chain().focus()

  return (
    <div className="policyeditor">
      <div className="policytools">
        <button type="button" title="Undo" disabled={!editor.can().undo()}
          onClick={() => chain().undo().run()}><Undo2 size={14} /></button>
        <button type="button" title="Redo" disabled={!editor.can().redo()}
          onClick={() => chain().redo().run()}><Redo2 size={14} /></button>
        <select value={level} onChange={(e) => {
          const want = Number(e.target.value)
          if (want) chain().setHeading({ level: want }).run()
          else chain().setParagraph().run()
        }}>
          {HEADINGS.map(([label, l]) => <option key={l} value={l}>{label}</option>)}
        </select>
        <button type="button" title="Bold" className={editor.isActive('bold') ? 'on' : ''}
          onClick={() => chain().toggleBold().run()}><Bold size={14} /></button>
        <button type="button" title="Italic" className={editor.isActive('italic') ? 'on' : ''}
          onClick={() => chain().toggleItalic().run()}><Italic size={14} /></button>
        <button type="button" title="Bulleted list"
          className={editor.isActive('bulletList') ? 'on' : ''}
          onClick={() => chain().toggleBulletList().run()}><List size={14} /></button>
        <button type="button" title="Numbered list"
          className={editor.isActive('orderedList') ? 'on' : ''}
          onClick={() => chain().toggleOrderedList().run()}><ListOrdered size={14} /></button>
        <button type="button" title="Link" onClick={() => {
          const href = window.prompt('Address', editor.getAttributes('link').href || '')
          if (href === null) return
          if (href) chain().extendMarkRange('link').setLink({ href }).run()
          else chain().extendMarkRange('link').unsetLink().run()
        }}><Link2 size={14} /></button>
        <button type="button" title="Insert a table"
          onClick={() => chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}>
          <TableIcon size={14} />
        </button>
        {editor.isActive('table') && (
          <>
            <button type="button" onClick={() => chain().addRowAfter().run()}>+ Row</button>
            <button type="button" onClick={() => chain().addColumnAfter().run()}>+ Column</button>
            <button type="button" onClick={() => chain().deleteRow().run()}>- Row</button>
            <button type="button" onClick={() => chain().deleteColumn().run()}>- Column</button>
            <button type="button" onClick={() => chain().deleteTable().run()}>Remove table</button>
          </>
        )}
        {/* The blanks, offered rather than typed. One mistyped brace is a policy that prints
            {compny} to a driver for ever. */}
        {fields.length > 0 && (
          <select value="" onChange={(e) => {
            if (e.target.value) chain().insertContent(e.target.value).run()
          }}>
            <option value="">Insert field</option>
            {fields.map(([token, label]) => (
              <option key={token} value={token}>{label}</option>
            ))}
          </select>
        )}
      </div>
      <EditorContent editor={editor} className="policypaper" />
    </div>
  )
}

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Modal } from '../admin/common.jsx'

// Filing one drug or alcohol test. One form, wherever a test is filed from.
//
// There were two of these and they drifted: the testing history asked for a reason, and the
// requirement dialog asked for a reason AND quietly defaulted it to the requirement's own. A
// return-to-duty test filed from the step that asks for it has nothing to choose - the reason
// is the step - so the field is shown as a sentence rather than as a dropdown with one entry.
export default function TestDialog({ title, reason, locked, reasons, results, offer, busy, err, onSave, onClose }) {
  const today = new Date().toISOString().slice(0, 10)
  const [f, setF] = useState({ reason: reason || (offer || [])[0] || '',
                               collectedon: today, result: 'negative', note: '', file: null,
                               // 49 CFR 382.403: the MIS report is two halves, controlled
                               // substances and alcohol, and nothing on the record used to say
                               // which half a test belonged on.
                               testtype: 'drug', substance: '', bac: '' })
  return (
    <Modal title={title} onClose={onClose} width={620}
      footer={<>
        <button type="button" className="primary" disabled={busy || !f.reason}
          onClick={() => onSave(f)}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          {locked ? (
            <label className="field span-3">Reason
              <input value={reasons?.[f.reason] || f.reason} readOnly />
            </label>
          ) : (
            // Only the reasons that can honestly be filed today. A return-to-duty test on a
            // driver with nothing to return from answers no question.
            <label className="field span-3">Reason *
              <select value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })}>
                {(offer || []).map((r) => (
                  <option key={r} value={r}>{reasons?.[r] || r}</option>
                ))}
              </select>
            </label>
          )}
          <label className="field span-3">Collected *
            <input type="date" value={f.collectedon} max={today}
              onChange={(e) => setF({ ...f, collectedon: e.target.value })} />
          </label>
          <label className="field span-3">Tested For *
            <select value={f.testtype}
              onChange={(e) => setF({ ...f, testtype: e.target.value })}>
              <option value="drug">Controlled substances</option>
              <option value="alcohol">Alcohol</option>
            </select>
          </label>
          <label className="field span-3">Result *
            <select value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })}>
              {Object.entries(results || {}).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
          {/* Only where the answer is one. The MIS form counts each drug a specimen was
              positive for, so a test positive for two is two lines on it. */}
          {f.testtype === 'drug' && f.result === 'positive' && (
            <label className="field span-3">Positive For *
              <input value={f.substance} className="upper"
                placeholder="MARIJUANA, COCAINE"
                onChange={(e) => setF({ ...f, substance: e.target.value.toUpperCase() })} />
            </label>
          )}
          {/* The number, not the band. 382.505 is 0.02 and 382.507 is 0.04, and a band cannot
              be re-banded if the form ever asks differently. */}
          {f.testtype === 'alcohol' && (
            <label className="field span-3">Alcohol Concentration
              <input type="number" step="0.001" min="0" max="0.999" value={f.bac}
                onChange={(e) => setF({ ...f, bac: e.target.value })} />
            </label>
          )}
          <label className="field span-3">Laboratory Report
            <input type="file"
              onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
          </label>
          <label className="field span-6">Note
            <textarea value={f.note}
              onChange={(e) => setF({ ...f, note: e.target.value.toUpperCase() })} />
          </label>
        </div>
      </div>
    </Modal>
  )
}

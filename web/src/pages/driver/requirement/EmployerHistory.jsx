// Requirement dialogs - EmployerHistory. Moved out of
// Requirements.jsx, which had grown too large to work in safely.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Ban, Car, Check, ChevronLeft, Download, FlaskConical, LayoutDashboard, ChevronRight, Clock, ExternalLink, Eye, FileSignature, FileText, FileUp, FolderOpen, History, IdCard, ListChecks, Loader2, MoreHorizontal, Plus, X, Send, UserCheck, UserX } from 'lucide-react'
import { STATE_NAMES } from '../../../lib/states.js'
import { api } from '../../../lib/api.js'
import { useRefreshOnFocus, useWatch } from '../../../lib/live.js'
import { date } from '../../../lib/format.js'
import { Bubble, Loading, useLoad } from '../../../components/ui.jsx'
import { Modal } from '../../../admin/common.jsx'
import Pager, { PAGE_SIZES } from '../../../components/Pager.jsx'
import { useUser } from '../../../App.jsx'
import SignatureBlock from '../../../components/UserSignature.jsx'
import { ItemPanel, PanelsDialog, ReadingViewer, SingleDocumentDialog, docStanding } from '../../../components/RequirementDialogs.jsx'
import DocumentViewer, { DocumentPane } from '../../../components/DocumentViewer.jsx'
import ApplicantForm from '../../../components/ApplicantForm.jsx'
import SignedDocViewer from '../../../components/SignedDocViewer.jsx'
import { PhoneInput } from '../../../components/MaskedInput.jsx'
import LicenseDialog from '../../../components/LicenseDialog.jsx'
import TestDialog from '../../../components/TestDialog.jsx'
import WithdrawDialog, { WithdrawnDialog } from '../../../components/WithdrawDialog.jsx'
import { Email, Phone } from '../../../components/Contact.jsx'
import { BLANK_CRASH, CRASH_STATE, FROM_ROW, unread, when } from '../common.jsx'
import { DriverLicenses } from '../Licenses.jsx'
import { ProhibitionPanel } from '../Testing.jsx'
import { CrashDialog } from '../Accidents.jsx'
import { DETAIL } from './common.jsx'

// Where an employer inquiry stands, in a word for the head of its panel.
const SPHI_STANDING = { notasked: 'Not Asked', waiting: 'Waiting', toreview: 'Not Reviewed',
  answered: 'Answered', effort: 'Good Faith Effort' }

const SPHI_CHANNELS = { email: 'Email', fax: 'Fax', mail: 'Mail', phone: 'Telephone',
  inperson: 'In person' }

// Where a request goes, by channel - and what the employer record already holds for it. The
// office picks the channel; the address is offered, not imposed, because the one on an application
// is the one the driver remembered.
const SEND_TO = {
  email: (x) => x.email || '',
  fax: (x) => x.fax || '',
  mail: (x) => [x.address1, x.city, x.state, x.zip].filter(Boolean).join(', '),
  phone: (x) => x.phone || '',
  inperson: (x) => x.contactname || '',
}

// RequirementDetail, when source.kind === 'employerhistory'.
export function EmployerHistoryDialog({ att, busy, closeEffort, code, confirmed, err, filing, gfe, gfesig, inq, me, onClose, r, reviewReply, sendRequest, setAtt, setFiling, setGfe, setGfesig, setInq, setSphiHistory, setViewing, signed, sphi, sphiHistory, today, uploadReply, viewing }) {
    if (filing === 'upload' && inq) {
      return (
        <Modal title="Upload The Reply" onClose={() => setFiling('send')} width={680}
          footer={<>
            <button type="button" className="primary" disabled={busy || !att.file}
              onClick={uploadReply}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setFiling('send')}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="muted small">{inq.employer}</div>
            <div className="profileform">
              <label className="field span-3">Who Answered
                <input value={att.sentto} className="upper"
                  onChange={(e) => setAtt({ ...att, sentto: e.target.value.toUpperCase() })} /></label>
              <label className="field span-6">The Reply *
                <input type="file"
                  onChange={(e) => setAtt({ ...att, file: e.target.files[0] || null })} /></label>
              <label className="field span-6">Note
                <textarea value={att.note}
                  onChange={(e) => setAtt({ ...att, note: e.target.value })} /></label>
            </div>
          </div>
        </Modal>
      )
    }

    if (filing === 'sent' && confirmed) {
      const emailed = confirmed.channel === 'email'
      return (
        <Modal title={emailed ? 'Request Sent' : 'Attempt Recorded'} width={520}
          onClose={() => setFiling('send')}
          footer={<button type="button" className="primary"
            onClick={() => setFiling('send')}>Done</button>}>
          <div className="askorder">
            <span className="askmark"><Check size={28} strokeWidth={3} /></span>
            <p>
              {emailed
                ? <>The request went to <b>{confirmed.to}</b> for {confirmed.employer}.</>
                : <>Recorded against {confirmed.employer}: {(sphi?.channels?.[confirmed.channel]
                    || confirmed.channel).toLowerCase()}{confirmed.to ? <> to <b>{confirmed.to}</b></> : null}.</>}
            </p>
          </div>
        </Modal>
      )
    }

    // Every attempt made on this employer. It is the record 391.23(i) asks to see, so it is kept
    // whole rather than summarised into the one line the table shows.
    // What came back, and what this office makes of it. A reply arrives from outside: it may say
    // the driver was dismissed, or that there are accidents on their record, and none of that has
    // been seen by anybody here until somebody reads it. So the requirement waits on the reading,
    // not on the answer - SPHI section 9.
    if (filing === 'reply' && inq) {
      return (
        <>
        <Modal title={inq.employer} onClose={() => setFiling(false)} width={900} tall flush
          footer={<>
            {!inq.reviewedon && (
              <button type="button" className="primary" disabled={busy} onClick={reviewReply}>
                {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
              </button>
            )}
            <button type="button" onClick={() => setFiling(false)}>Close</button>
          </>}>
          <div className="stack docstack">
            {err && <div className="notice bad readstamp">{err}</div>}
            {/* The form they filled in and signed, read here rather than from behind a button.
                Every answer is on it, so listing a handful of them above it said the same things
                twice and left the rest invisible. */}
            {inq.documentid
              ? <DocumentPane id={inq.documentid} name={`SPHI - ${inq.employer}`}
                  className="docview docfill" />
              : <div className="muted">The reply is on file but carries no document.</div>}
            {inq.reviewedon && (
              <div className="muted small readstamp">Read {date(inq.reviewedon)}.</div>
            )}
          </div>
        </Modal>
        {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
          onClose={() => setViewing(null)} />}
        </>
      )
    }

    if (filing === 'history' && inq) {
      return (
        <Modal title={`${inq.employer} - History`} onClose={() => setFiling('send')} width={820}
          footer={<button type="button" onClick={() => setFiling('send')}>Close</button>}>
          <div className="stack">
            {inq.attempts.length === 0
              ? <div className="muted">Nothing has been tried yet.</div>
              : (
                <table className="residencetable attempttable">
                  <thead><tr><th>When</th><th>How</th><th>To</th><th>Outcome</th></tr></thead>
                  <tbody>
                    {inq.attempts.map((a) => (
                      <tr key={a.recordid}>
                        <td>{date(a.senton)}</td>
                        <td>{sphi?.channels?.[a.channel] || a.channel}</td>
                        <td>{a.sentto || '-'}</td>
                        <td>{[a.outcome, a.note].filter(Boolean).join(' - ') || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
          </div>
        </Modal>
      )
    }

    // The good faith effort as the document 391.23(i) asks for: who was asked, everything that was
    // tried, how it ended, and somebody's signature saying that is what happened.
    if (filing === 'gfe') {
      const tried = inq?.attempts?.length || 0
      const closing = (sphi?.gfeclosing || []).includes(gfe.status)
      const needsAttempt = closing && gfe.status !== 'received' && tried === 0
      return (
        <Modal title="Good Faith Effort Documentation" width={820}
          onClose={() => setFiling('send')}
          footer={<>
            {/* An ending that is certified is filed by the signing itself. "Still pending" is not
                certified by anybody - it is a note about where things stand - so it is the one
                that still has something to press. */}
            {!closing && (
              <button type="button" className="primary" disabled={busy} onClick={closeEffort}>
                {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
              </button>
            )}
            <button type="button" onClick={() => setFiling('send')}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            {/* Whose document this is and what it is. A page pulled out of this file months from
                now is anonymous without it - and an auditor is reading the document, not the
                dialog that happened to be around it. */}
            <div className="dialoghead">
              <span className="co">{me?.accountname}</span>
              <h2>Safety Performance History Investigation</h2>
              <span className="sub">Good Faith Effort Documentation · 49 CFR 391.23(i)</span>
            </div>

            <h3 className="formsection">Driver</h3>
            <dl className="askfacts">
              <div><dt>Driver</dt><dd>{sphi?.driver?.name || '-'}</dd></div>
              <div><dt>Driver ID</dt><dd>{sphi?.driver?.drivernumber || '-'}</dd></div>
              <div><dt>Date of hire</dt>
                <dd>{sphi?.driver?.hiredon ? date(sphi.driver.hiredon) : 'Not hired yet'}</dd></div>
            </dl>

            <h3 className="formsection">Previous Employer</h3>
            <dl className="askfacts">
              <div><dt>Employer</dt><dd>{inq?.employer || '-'}</dd></div>
              <div><dt>Contact</dt><dd>{inq?.contactname || '-'}</dd></div>
              <div><dt>Phone</dt><dd><Phone number={inq?.phone} /></dd></div>
              <div><dt>Email</dt><dd><Email address={inq?.email} /></dd></div>
              <div><dt>Fax</dt><dd>{inq?.fax || '-'}</dd></div>
              <div><dt>Employed</dt>
                <dd>{[inq?.employedfrom && date(inq.employedfrom),
                      inq?.employedthrough && date(inq.employedthrough)]
                  .filter(Boolean).join(' to ') || '-'}</dd></div>
            </dl>

            {/* Every attempt, which is what the effort IS. Added from the dialog behind this one,
                because an attempt is a thing that happened rather than a line on a form. */}
            <h3 className="formsection">Attempts ({tried})</h3>
            {tried === 0 ? (
              <div className="notice bad">
                Nothing has been tried yet. A good faith effort is filed over attempts that were
                actually made, so there is nothing to certify here.
              </div>
            ) : (
              <table className="residencetable recordtable">
                <thead><tr><th>Date</th><th>Method</th><th>Sent to</th><th>Result</th></tr></thead>
                <tbody>
                  {inq.attempts.map((a) => (
                    <tr key={a.recordid}>
                      <td>{date(a.senton)}</td>
                      <td>{sphi?.channels?.[a.channel] || a.channel}</td>
                      <td>{a.sentto || '-'}</td>
                      <td>{[a.outcome, a.note].filter(Boolean).join(' - ') || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <h3 className="formsection">Determination</h3>
            <div className="asklist">
              {Object.entries(sphi?.gfestatus || {}).map(([v, l]) => (
                <label key={v} className="askrow">
                  <span className="askwhat">{l}</span>
                  <span className="askpick">
                    <input type="radio" name="gfestatus" checked={gfe.status === v}
                      onChange={() => setGfe({ ...gfe, status: v })} />
                  </span>
                </label>
              ))}
            </div>
            <div className="profileform">
              <label className="field span-6">Notes
                <textarea rows={3} value={gfe.note} className="upper"
                  onChange={(e) => setGfe({ ...gfe, note: e.target.value.toUpperCase() })} />
              </label>
            </div>

            {/* The certification. Signed with the signer's own signature already on file - the one
                adopted behind a date of birth and a Social Security number - exactly as the
                request itself is signed. Nobody types their name here. */}
            {closing && (
              <div className="signhereblock">
                <p className="muted small">
                  I certify that the employer made a good faith effort to obtain the driver's
                  required safety performance history from the previous employer identified above.
                  The attempts documented in this record represent the actions taken to obtain the
                  required information.
                </p>
                <dl className="askfacts">
                  <div><dt>Completed by</dt><dd>{sphi?.certifier?.name || '-'}</dd></div>
                  <div><dt>Title</dt><dd>{sphi?.certifier?.title || '-'}</dd></div>
                </dl>
                {/* The signing act every document in this software uses: Sign Document, then the
                    date of birth and Social Security number, then the signature on file is looked
                    up and applied. Nothing is drawn on the line until that has happened. */}
                <SignatureBlock
                  signature={gfesig || (inq?.effortsignedon
                    ? { typedname: inq.effortsignature, fontkey: inq.effortfontkey || 'modern' }
                    : null)}
                  onSigned={(sig) => { setGfesig(sig); closeEffort() }}
                  label="Signature" action="Sign Document" />
              </div>
            )}
          </div>
        </Modal>
      )
    }

    // One dialog per employer: what has been tried, how to try again, and the signature that lets
    // it go. The history is here rather than in a screen of its own because the next attempt is
    // decided by reading the last one - a third letter to an address that bounced twice is not a
    // good faith effort, it is a habit.
    if (filing === 'send' && inq) {
      const signed = Boolean(inq.requestsignedon)
      const sending = att.channel === 'email'
      return (
        <Modal title={inq.employer} onClose={() => setFiling(false)} width={860}
          footer={<>
            <button type="button" className="primary"
              disabled={busy || !att.sentto.trim() || (!signed && !sphi?.signature)}
              onClick={sendRequest}>
              {busy ? <Loader2 size={15} className="spin" />
                : sending ? <><Send size={13} /> Send it</> : <><Plus size={13} /> Record it</>}
            </button>
            <button type="button" disabled={!inq.attempts.length}
              onClick={() => setFiling('history')}>
              <History size={13} /> History{inq.attempts.length ? ` (${inq.attempts.length})` : ''}
            </button>
            {/* A reply that came back on paper or by fax. The same answer; the only difference is
                that nobody typed it in, so what is kept is the page they sent. */}
            {!inq.respondedon && (
              <button type="button"
                onClick={() => { setAtt({ ...att, sentto: inq.contactname || '', note: '',
                  file: null }); setFiling('upload') }}>
                <Plus size={13} /> Upload
              </button>
            )}
            {/* Offered whenever the employer has not answered: the dialog says what is being
                filed over, and refuses when there is nothing behind it. */}
            {!inq.effortclosedon && !inq.respondedon && (
              <button type="button" onClick={() => { setAtt({ ...att, note: '' }); setFiling('gfe') }}>
                <FileSignature size={13} /> File GFE
              </button>
            )}
            <button type="button" onClick={() => setFiling(false)}>Close</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}

            <section>
              <h3 className="formsection">Send It</h3>
              <div className="profileform">
                <label className="field span-2">How
                  <select value={att.channel}
                    onChange={(e) => setAtt({ ...att, channel: e.target.value,
                      sentto: (SEND_TO[e.target.value] || (() => ''))(inq) })}>
                    {Object.entries(sphi?.channels || {}).map(([v, l]) =>
                      <option key={v} value={v}>{l}</option>)}
                  </select>
                </label>
                <label className="field span-4">
                  {att.channel === 'email' ? 'Email address'
                    : att.channel === 'fax' ? 'Fax number'
                      : att.channel === 'phone' ? 'Telephone' : 'Address'}
                  <input value={att.sentto}
                    onChange={(e) => setAtt({ ...att, sentto: e.target.value })} />
                </label>
                {/* The link the employer answers on. On the form because a fax or a letter has to
                    carry it, and somebody on the telephone has to be able to read it out. */}
                {!inq.respondedon && (
                  <label className="field span-6">Link they answer on
                    <code className="linkline">{inq.link}</code>
                  </label>
                )}
                {!sending && (
                  <>
                    <label className="field span-2">On
                      <input type="date" value={att.senton}
                        onChange={(e) => setAtt({ ...att, senton: e.target.value })} /></label>
                    <label className="field span-2">Outcome
                      <select value={att.outcome}
                        onChange={(e) => setAtt({ ...att, outcome: e.target.value })}>
                        <option value="">Not stated</option>
                        <option value="sent">Sent</option>
                        <option value="failed">Failed to send</option>
                        <option value="noanswer">No answer</option>
                        <option value="refused">Refused</option>
                      </select>
                    </label>
                    <label className="field span-6">Note
                      <textarea value={att.note}
                        onChange={(e) => setAtt({ ...att, note: e.target.value })} /></label>
                  </>
                )}
              </div>
              {!sending && (
                <p className="muted small">
                  TripProof does not send by {(sphi?.channels?.[att.channel] || att.channel).toLowerCase()}.
                  Send it yourself and record it here.
                </p>
              )}
            </section>

            {/* A previous employer is being asked to release somebody's history to a stranger. A
                named person putting their name to it is what makes that a request. */}
            <section>
              <h3 className="formsection">Signed By</h3>
              {/* The hand itself, as it will appear on the request - a statement of what is
                  about to be signed, not a step to repeat per employer. */}
              {(signed || sphi?.signature) ? (
                <div className="signfields">
                  <div className="signbox">
                    <span className="signlabel">Signature Of Requestor</span>
                    <div className="signline">
                      <span className={`sigink font-${signed ? inq.requestfontkey || 'modern'
                        : sphi.signature.fontkey}`}>
                        {signed ? inq.requestsignature : sphi.signature.typedname}
                      </span>
                    </div>
                  </div>
                  <div className="signbox datebox">
                    <span className="signlabel">Signature Date</span>
                    <div className="signline">
                      {date(signed ? inq.requestsignedon : today)}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="notice warn">
                  A request goes out over somebody&rsquo;s name. Set up your signature in your
                  profile, and it will be used for this and every request afterwards.
                </div>
              )}
            </section>
          </div>
        </Modal>
      )
    }

    const found = sphi?.inquiries || []
    return (
      <>
      {/* One panel per employer, laid out as the driving records are: who and when in the head,
          where the inquiry stands beneath, and what can be done about it below. */}
      <PanelsDialog title={r.name} brief={r?.description} err={err} width={DETAIL} onClose={onClose}
        empty={<div className="muted">
          No DOT-regulated employers in the last three years are on this driver&rsquo;s
          application, so there is nobody to ask.
        </div>}>
        {found.map((x) => {
          const last = (x.attempts || [])[0]
          const unreadReply = x.respondedon && !x.reviewedon
          const tone = x.state === 'answered' ? 'st-active' : x.state === 'effort' ? 'st-inactive'
            : x.state === 'toreview' || x.state === 'waiting' ? 'st-ordered' : 'st-expired'
          const send = () => {
            const channel = x.email ? 'email' : x.fax ? 'fax' : 'mail'
            setInq(x)
            setAtt({ channel, sentto: SEND_TO[channel](x), senton: '', outcome: '',
              note: '', signature: '' })
            setFiling('send')
          }
          return (
            <ItemPanel key={x.recordid} title={x.employer}
              status={[SPHI_STANDING[x.state] || x.state, tone]}
              facts={[
                { label: 'Employed',
                  value: [date(x.employedfrom), date(x.employedthrough)].filter(Boolean).join(' - ') || '-' },
                { label: 'Last asked', tone: last ? undefined : 'st-expired',
                  value: last ? `${SPHI_CHANNELS[last.channel] || last.channel} ${date(last.senton)}` : 'Not asked' },
                { label: 'Reply', tone: x.respondedon ? undefined : last ? 'st-ordered' : undefined,
                  value: x.respondedon ? date(x.respondedon) : last ? 'None yet' : '-' },
                { label: 'Review',
                  tone: unreadReply ? 'st-ordered' : x.reviewedon ? 'st-active' : undefined,
                  value: unreadReply ? 'Not reviewed' : x.reviewedon ? date(x.reviewedon)
                    : x.effortclosedon ? `Good faith effort ${date(x.effortclosedon)}` : '-' },
              ]}
              actions={<>
                      {unreadReply ? (
                        <button type="button" className="primary" onClick={() => {
                          setInq(x); setAtt({ ...att, outcome: '', note: '' }); setFiling('reply')
                        }}><Eye size={14} /> Review</button>
                      ) : x.respondedon ? (
                        <button type="button" onClick={() => {
                          setInq(x)
                          if (x.documentid) {
                            setViewing({ documentid: x.documentid, filename: `SPHI - ${x.employer}` })
                          } else {
                            setAtt({ ...att, outcome: '', note: '' }); setFiling('reply')
                          }
                        }}><Eye size={14} /> View</button>
                      ) : x.effortclosedon && x.effortdocumentid ? (
                        <button type="button" onClick={() => setViewing({
                          documentid: x.effortdocumentid, filename: `Good faith effort - ${x.employer}` })}>
                          <Eye size={14} /> View
                        </button>
                      ) : null}
                      {/* Asking again is always open until somebody has answered. */}
                      {!x.respondedon && (
                        <button type="button" className={last ? undefined : 'primary'} onClick={send}>
                          <Send size={13} /> {last ? 'Ask Again' : 'Send Inquiry'}
                        </button>
                      )}
                      <button type="button" disabled={!(x.attempts || []).length}
                        onClick={() => setSphiHistory(x)}>
                        <History size={13} /> History
                      </button>
                    </>} />
          )
        })}
      </PanelsDialog>
      {/* Every time this employer was asked, how, and what came of it. */}
      {sphiHistory && (
        <Modal title={`${sphiHistory.employer} - History`} onClose={() => setSphiHistory(null)}
          width={DETAIL}
          footer={<button type="button" onClick={() => setSphiHistory(null)}>Close</button>}>
          <table className="residencetable recordtable">
            <thead><tr><th>Date</th><th>How</th><th className="growcol">Sent To</th><th>Outcome</th></tr></thead>
            <tbody>
              {(sphiHistory.attempts || []).map((a) => (
                <tr key={a.recordid}>
                  <td>{date(a.senton)}</td>
                  <td>{SPHI_CHANNELS[a.channel] || a.channel}</td>
                  <td className="growcol">{a.sentto || '-'}</td>
                  <td>{a.outcome || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Modal>
      )}
      {/* The form they sent back, opened straight from the row. */}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)} />}
      </>
    )
  
}

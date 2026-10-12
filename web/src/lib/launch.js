import { api } from './api.js'

// Open a customer's portal in a new tab as the signed-in staff member. The tab is opened before
// the API call (so pop-up blockers see a direct click), then pointed at /launch with the short
// session token in the URL fragment - fragments never reach the server or its logs.
export async function launchAccount(accountid) {
  const tab = window.open('', '_blank')
  try {
    const { token } = await api.post(`/admin/accounts/${accountid}/launch`)
    if (tab) {
      tab.opener = null
      tab.location = `/launch#token=${encodeURIComponent(token)}`
    } else {
      window.location.assign(`/launch#token=${encodeURIComponent(token)}`)
    }
  } catch (e) {
    tab?.close()
    alert(e.message)
  }
}
